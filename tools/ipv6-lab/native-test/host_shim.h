#pragma once
#include <memory>
#include <functional>
#include <string>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <sys/epoll.h>
#include <unistd.h>
#include "Defines.h"
#include "NativeByteBuffer.h"

// Test seams for application infrastructure. ConnectionSocket and buffers are real.
#define CONNECTIONSMANAGER_H
class ConnectionsManager {
public:
    std::string proxyAddress, proxySecret, proxyUser, proxyPassword;
    uint16_t proxyPort = 1080;
    ConnectiosManagerDelegate *delegate = nullptr;
    int epolFd;
    NativeByteBuffer *networkBuffer;
    int attached = 0;
    ConnectionsManager(): epolFd(epoll_create1(EPOLL_CLOEXEC)),
        networkBuffer(new NativeByteBuffer((uint32_t)READ_BUFFER_SIZE)) {}
    static ConnectionsManager &getInstance(int32_t) {
        static ConnectionsManager manager;
        return manager;
    }
    int64_t getCurrentTimeMonotonicMillis() {
        return std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count();
    }
    int32_t getCurrentTime() { return (int32_t)time(nullptr); }
    void attachConnection(ConnectionSocket *) { ++attached; }
    void detachConnection(ConnectionSocket *) { --attached; }
    void scheduleTask(std::function<void()> task) { task(); }
};
#define CONNECTION_H

#define EVENTOBJECT_H
class EventObject {
public:
    int64_t time = 0;
    void *eventObject;
    EventObjectType eventType;
    EventObject(void *object, EventObjectType type): eventObject(object), eventType(type) {}
};

#define FILELOG_H
inline bool LOGS_ENABLED = false;
class FileLog {
public:
    static FileLog &getInstance() { static FileLog log; return log; }
    static void fatal(const char *, ...) { std::abort(); }
    static void e(const char *, ...) {}
    static void w(const char *, ...) {}
    static void d(const char *, ...) {}
    static void ref(const char *, ...) {}
    static void delref(const char *, ...) {}
};
#define DEBUG_FATAL FileLog::fatal
#define DEBUG_E FileLog::e
#define DEBUG_W FileLog::w
#define DEBUG_D FileLog::d
#define DEBUG_REF FileLog::ref
#define DEBUG_DELREF FileLog::delref
