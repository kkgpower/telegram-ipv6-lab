#!/usr/bin/env bash
set -euo pipefail

TEST_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(git -C "$TEST_DIR" rev-parse --show-toplevel)"
TGNET_DIR="$REPO_DIR/TMessagesProj/jni/tgnet"
BUILD_DIR="${NATIVE_TEST_BUILD_DIR:-${TMPDIR:-/tmp}/telegram-ipv6-native-test-run}"
TEST_CXX="${CXX:-g++}"
BASELINE_COMMIT=21f7d109da6ab3506c9e9577f98c6a38771ab335
mkdir -p -- "$BUILD_DIR"

if [[ "${1:-}" == --baseline ]]; then
    if (( $# != 1 )); then
        echo 'Usage: build.sh [--baseline | SOURCE.cpp [OUTPUT_BINARY]]' >&2
        exit 2
    fi
    SOCKET_SOURCE="$BUILD_DIR/ConnectionSocket.baseline.cpp"
    git -C "$REPO_DIR" show "$BASELINE_COMMIT:TMessagesProj/jni/tgnet/ConnectionSocket.cpp" > "$SOCKET_SOURCE"
    TEST_BINARY="$BUILD_DIR/baseline-test"
else
    if (( $# > 2 )); then
        echo 'Usage: build.sh [--baseline | SOURCE.cpp [OUTPUT_BINARY]]' >&2
        exit 2
    fi
    SOCKET_SOURCE="${1:-$TGNET_DIR/ConnectionSocket.cpp}"
    TEST_BINARY="${2:-$BUILD_DIR/fixed-test}"
fi
mkdir -p -- "$(dirname -- "$TEST_BINARY")"

"$TEST_CXX" -std=c++17 -O1 -g -Wall -Wextra -Wno-unused-parameter \
    -ffunction-sections -fdata-sections -I"$TGNET_DIR" -I"$TEST_DIR" \
    -include "$TEST_DIR/host_shim.h" \
    "$SOCKET_SOURCE" "$TEST_DIR/main.cpp" \
    "$TGNET_DIR/ByteArray.cpp" "$TGNET_DIR/ByteStream.cpp" \
    "$TGNET_DIR/NativeByteBuffer.cpp" "$TGNET_DIR/BuffersStorage.cpp" \
    "$TGNET_DIR/TLSHello.cpp" \
    -Wl,--gc-sections -pthread -lcrypto -o "$TEST_BINARY"
echo "Built $TEST_BINARY"
