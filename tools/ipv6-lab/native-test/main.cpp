#include "host_shim.h"
#include <array>
#include <algorithm>
#include <vector>
#include <stdexcept>
#include <iostream>
#include <cerrno>
#include <cstring>
#include <arpa/inet.h>
#include <fcntl.h>
#include <poll.h>
#include <netinet/tcp.h>
// Access only to assertions; production TU compiles without this macro.
#define private public
#include "ConnectionSocket.h"
#undef private

static void require(bool condition, const std::string &msg) {
    if (!condition) throw std::runtime_error(msg + "; errno=" + std::to_string(errno));
}
struct TestSocket: ConnectionSocket {
    int connected = 0, disconnected = 0, error = 0;
    std::vector<uint8_t> received;
    TestSocket(): ConnectionSocket(0) {}
    ~TestSocket() { if (!isDisconnected()) dropConnection(); }
    using ConnectionSocket::onEvent;
    void onConnected() override { ++connected; }
    void onDisconnected(int32_t, int32_t e) override { ++disconnected; error = e; }
    void onReceivedData(NativeByteBuffer *buf) override {
        received.insert(received.end(), buf->bytes()+buf->position(), buf->bytes()+buf->limit());
    }
    bool hasPendingRequests() override { return false; }
};
struct Listener {
    int fd = -1, peer = -1;
    uint16_t port = 0;
    explicit Listener(int family) {
        fd = socket(family, SOCK_STREAM | SOCK_NONBLOCK, 0);
        require(fd >= 0, "listener socket");
        int yes = 1;
        setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
        if (family == AF_INET6) setsockopt(fd, IPPROTO_IPV6, IPV6_V6ONLY, &yes, sizeof(yes));
        sockaddr_storage address{};
        socklen_t length;
        if (family == AF_INET6) {
            auto *a = (sockaddr_in6 *)&address;
            a->sin6_family = AF_INET6; a->sin6_addr = in6addr_loopback;
            length = sizeof(*a);
        } else {
            auto *a = (sockaddr_in *)&address;
            a->sin_family = AF_INET; a->sin_addr.s_addr = htonl(INADDR_LOOPBACK);
            length = sizeof(*a);
        }
        require(bind(fd, (sockaddr *)&address, length) == 0, "listener bind");
        require(getsockname(fd, (sockaddr *)&address, &length) == 0, "getsockname");
        port = family == AF_INET6 ? ntohs(((sockaddr_in6 *)&address)->sin6_port) : ntohs(((sockaddr_in *)&address)->sin_port);
        require(listen(fd, 4) == 0, "listen");
    }
    void acceptPeer() {
        pollfd p{fd, POLLIN, 0};
        require(poll(&p, 1, 500) == 1, "no TCP connection accepted");
        peer = accept4(fd, nullptr, nullptr, SOCK_NONBLOCK);
        require(peer >= 0, "accept4");
    }
    ~Listener() { if (peer >= 0) close(peer); if (fd >= 0) close(fd); }
};
static void pump(TestSocket &socket, int rounds = 1) {
    auto &manager = ConnectionsManager::getInstance(0);
    for (int i = 0; i < rounds; ++i) {
        epoll_event events[8];
        int n = epoll_wait(manager.epolFd, events, 8, 100);
        require(n >= 0, "epoll_wait");
        for (int a = 0; a < n; ++a) {
            auto *object = (EventObject *)events[a].data.ptr;
            require(object->eventObject == &socket, "wrong event target");
            socket.onEvent(events[a].events);
        }
    }
}
static void inspect(TestSocket &s, int expectedFamily, uint16_t expectedPort, bool dcIpv6) {
    require(!s.isDisconnected(), "socket was closed synchronously");
    int family = 0, noDelay = 0; socklen_t len = sizeof(family);
    require(getsockopt(s.socketFd, SOL_SOCKET, SO_DOMAIN, &family, &len) == 0, "SO_DOMAIN");
    require(family == expectedFamily, "wrong actual socket family");
    require((fcntl(s.socketFd, F_GETFL) & O_NONBLOCK) != 0, "missing O_NONBLOCK");
    require(getsockopt(s.socketFd, IPPROTO_TCP, TCP_NODELAY, &noDelay, &len) == 0 && noDelay == 1, "missing TCP_NODELAY");
    require((s.eventMask.events & (EPOLLIN|EPOLLOUT|EPOLLET|EPOLLERR|EPOLLRDHUP)) == (EPOLLIN|EPOLLOUT|EPOLLET|EPOLLERR|EPOLLRDHUP), "missing epoll flags");
    require(s.isIpv6 == dcIpv6, "DC family changed to proxy family");
    if (expectedFamily == AF_INET6) {
        require(s.socketAddress6.sin6_family == AF_INET6, "wrong sin6_family");
        require(ntohs(s.socketAddress6.sin6_port) == expectedPort, "wrong sin6_port");
    } else {
        require(s.socketAddress.sin_family == AF_INET, "wrong sin_family");
        require(ntohs(s.socketAddress.sin_port) == expectedPort, "wrong sin_port");
    }
}
static const char *loopback(int family) { return family == AF_INET6 ? "::1" : "127.0.0.1"; }
static void resetManager() {
    auto &m = ConnectionsManager::getInstance(0);
    require(m.attached == 0, "connection not detached");
    m.proxyAddress.clear(); m.proxySecret.clear(); m.proxyUser.clear(); m.proxyPassword.clear();
}
static void connectedCase(int family, bool proxy, bool globalProxy, bool dcIpv6) {
    resetManager();
    Listener l(family);
    TestSocket s;
    const std::string secret(16, 'a');
    if (proxy) {
        if (globalProxy) {
            auto &m = ConnectionsManager::getInstance(0);
            m.proxyAddress = loopback(family); m.proxyPort = l.port; m.proxySecret = secret;
        } else s.setOverrideProxy(loopback(family), l.port, "", "", secret);
    }
    s.openConnection(proxy ? (dcIpv6 ? "2001:db8::1" : "192.0.2.1") : loopback(family),
        proxy ? 443 : l.port, "", proxy ? dcIpv6 : family == AF_INET6, 1);
    inspect(s, family, l.port, proxy ? dcIpv6 : family == AF_INET6);
    l.acceptPeer(); pump(s);
    require(s.connected == 1 && s.disconnected == 0, "onConnected callback missing");
    uint8_t ping[] = {1,2,3,4};
    auto *payload = new NativeByteBuffer((uint32_t)sizeof(ping));
    payload->writeBytes(ping, sizeof(ping)); payload->rewind();
    s.writeBuffer(payload); pump(s);
    std::array<uint8_t, 16> bytes{};
    require(recv(l.peer, bytes.data(), bytes.size(), 0) == 4 && std::equal(bytes.begin(), bytes.begin()+4, ping), "TCP payload mismatch");
    require(send(l.peer, ping, sizeof(ping), 0) == 4, "server send"); pump(s);
    require(s.received == std::vector<uint8_t>(ping, ping+4), "onReceivedData mismatch");
    s.dropConnection();
}
static std::vector<uint8_t> readPeer(int fd, size_t expected) {
    pollfd p{fd, POLLIN, 0}; require(poll(&p, 1, 500) == 1, "server read timeout");
    std::vector<uint8_t> bytes(256); ssize_t n = recv(fd, bytes.data(), bytes.size(), 0);
    require(n == (ssize_t)expected, "SOCKS5 unexpected message length"); bytes.resize(n); return bytes;
}
static void socksCase(int proxyFamily, bool dcIpv6) {
    resetManager(); Listener l(proxyFamily); TestSocket s;
    s.setOverrideProxy(loopback(proxyFamily), l.port, "", "", "");
    const char *destination = dcIpv6 ? "2001:db8::1234" : "192.0.2.13";
    s.openConnection(destination, 443, "", dcIpv6, 1);
    inspect(s, proxyFamily, l.port, dcIpv6); l.acceptPeer(); pump(s);
    require(readPeer(l.peer, 4) == std::vector<uint8_t>({5,2,0,2}), "SOCKS5 greeting mismatch");
    const uint8_t accepted[] = {5,0}; require(send(l.peer, accepted, 2, 0) == 2, "SOCKS5 accept send");
    pump(s, 2);
    auto request = readPeer(l.peer, dcIpv6 ? 22 : 10);
    require(request[0] == 5 && request[1] == 1 && request[2] == 0 && request[3] == (dcIpv6 ? 4 : 1), "wrong SOCKS5 ATYP");
    std::array<uint8_t, 16> address{}; inet_pton(dcIpv6 ? AF_INET6 : AF_INET, destination, address.data());
    size_t addressLen = dcIpv6 ? 16 : 4;
    require(std::equal(address.begin(), address.begin()+addressLen, request.begin()+4), "wrong SOCKS5 DC address");
    require(request[4+addressLen] == 1 && request[5+addressLen] == 187, "wrong SOCKS5 DC port");
    const uint8_t success[] = {5,0,0,1,0,0,0,0,0,0};
    require(send(l.peer, success, sizeof(success), 0) == (ssize_t)sizeof(success), "SOCKS5 success send"); pump(s, 2);
    require(s.connected == 1 && s.disconnected == 0, "SOCKS5 connected callback missing"); s.dropConnection();
}
static void refusedCase(int family) {
    resetManager(); uint16_t port;
    { Listener l(family); port = l.port; }
    TestSocket s; s.setOverrideProxy(loopback(family), port, "", "", std::string(16, 'a'));
    s.openConnection("192.0.2.1", 443, "", false, 1);
    require(!s.isDisconnected(), "expected asynchronous connect refusal");
    pump(s);
    require(s.disconnected == 1 && s.connected == 0 && s.error == ECONNREFUSED, "connect refusal not propagated");
    require(s.isDisconnected(), "failed FD not closed");
    epoll_event event; require(epoll_wait(ConnectionsManager::getInstance(0).epolFd, &event, 1, 0) == 0, "failed FD remained in epoll");
}
int main(int argc, char **argv) {
    int failures = 0, tests = 0;
    auto test = [&](const std::string &name, auto body) {
        if (argc > 1 && name != argv[1]) return;
        ++tests;
        try { body(); std::cout << "PASS " << name << '\n'; }
        catch (const std::exception &e) { ++failures; std::cout << "FAIL " << name << ": " << e.what() << '\n'; }
    };
    test("MTProto IPv6 override", [] { connectedCase(AF_INET6, true, false, false); });
    test("MTProto IPv4 override", [] { connectedCase(AF_INET, true, false, true); });
    test("MTProto IPv6 global", [] { connectedCase(AF_INET6, true, true, false); });
    test("MTProto IPv4 global", [] { connectedCase(AF_INET, true, true, true); });
    test("direct IPv6", [] { connectedCase(AF_INET6, false, false, false); });
    test("direct IPv4", [] { connectedCase(AF_INET, false, false, false); });
    test("SOCKS5 IPv6 proxy IPv4 DC", [] { socksCase(AF_INET6, false); });
    test("SOCKS5 IPv4 proxy IPv6 DC", [] { socksCase(AF_INET, true); });
    test("SOCKS5 IPv6 proxy IPv6 DC", [] { socksCase(AF_INET6, true); });
    test("SOCKS5 IPv4 proxy IPv4 DC", [] { socksCase(AF_INET, false); });
    test("async refusal IPv6", [] { refusedCase(AF_INET6); });
    test("async refusal IPv4", [] { refusedCase(AF_INET); });
    std::cout << tests-failures << '/' << tests << " passed\n";
    return failures ? 1 : 0;
}
