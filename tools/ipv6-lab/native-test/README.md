# ConnectionSocket host tests

Small Linux integration harness for the numeric IPv6 proxy fix in `7f67b8a`.
It compiles the actual checkout's `ConnectionSocket.cpp` and its real buffer/TLS
helpers. `host_shim.h` replaces application infrastructure only: Manager settings,
time and immediate task scheduling, EventObject storage, and logging. TCP sockets,
socket options, connect, and epoll are real. No Android build is run.

Requirements: Linux with IPv4 and IPv6 loopback, Bash, Git, a C++17 compiler, and
OpenSSL development headers/libcrypto. Tested with GCC 14.2.0 and OpenSSL 3 on Linux.
There are no package installation or download steps in the script. A shallow clone
must contain baseline commit `21f7d109da6ab3506c9e9577f98c6a38771ab335` to build it.

## Reproduce

From the repository root, with no `NATIVE_TEST_BUILD_DIR` or `TMPDIR` override:

```bash
bash tools/ipv6-lab/native-test/build.sh
timeout 20s /tmp/telegram-ipv6-native-test-run/fixed-test

bash tools/ipv6-lab/native-test/build.sh --baseline
timeout 10s /tmp/telegram-ipv6-native-test-run/baseline-test 'MTProto IPv6 override'
```

The second run is expected to exit **1**: the unmodified baseline uses the wrong
actual socket family for an IPv6 proxy. `--baseline` extracts the original source
verbatim from the fixed baseline commit; it does not use the current HEAD as the
baseline. The other helper sources come from the working checkout.

The script resolves source paths from its own location, so it also works when
invoked outside the repository. Build outputs default to
`${TMPDIR:-/tmp}/telegram-ipv6-native-test-run`, outside the checkout. Set
`NATIVE_TEST_BUILD_DIR` to choose another output directory or `CXX` to choose the
compiler. Optional positional arguments select a socket source and binary path:
`bash tools/ipv6-lab/native-test/build.sh SOURCE.cpp OUTPUT_BINARY`.

All TCP endpoints are `::1` or `127.0.0.1`. The `192.0.2.0/24` and `2001:db8::/32`
strings are DC destinations encoded for a local proxy, never TCP destinations.
If a sandbox blocks TCP creation, run with its local-network permission.

## Recorded result

The fixed source in `7f67b8a` passes **12/12** cases; baseline `21f7d10` fails the
selected IPv6 case with `wrong actual socket family`. Logs are stored alongside
the report in `docs/ipv6-lab-results/native-fixed.log` and `native-baseline.log`.

Cases cover numeric IPv4/IPv6 proxies via override/global settings, direct TCP for
both families, and all four combinations of SOCKS5 proxy/DC families. Assertions
check the real socket family, endpoint sockaddr family/port, O_NONBLOCK,
TCP_NODELAY, epoll registration, callbacks, bidirectional data, SOCKS5 ATYP/address/
port, and asynchronous ECONNREFUSED with descriptor cleanup for both families.

This is a **host transport test**, before MTProto encryption and proxy
authentication. It does not test Android/JNI, Java DNS, a complete MTProto service,
or fake-TLS handshakes. Linux OpenSSL satisfies the real TLS code's link
dependencies, but those cryptographic paths are not exercised. Existing warnings
in unrelated production code remain visible during compilation.
