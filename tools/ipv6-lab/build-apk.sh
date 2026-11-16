#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
cd -- "$REPO_DIR"

missing=()
for name in TELEGRAM_API_ID TELEGRAM_API_HASH LAB_KEYSTORE LAB_STORE_PASSWORD LAB_KEY_PASSWORD LAB_KEY_ALIAS; do
    if [[ -z "${!name:-}" ]]; then missing+=("$name"); fi
done
if (( ${#missing[@]} )); then
    printf 'Lab APK not built: required environment variables are missing: %s\n' "${missing[*]}" >&2
    exit 2
fi
if [[ -z "${JAVA_HOME:-}" || ! -x "$JAVA_HOME/bin/javac" || ! -x "$JAVA_HOME/bin/jlink" ]]; then
    echo 'Lab APK not built: set JAVA_HOME to a full JDK 17 or newer, including javac and jlink.' >&2
    exit 2
fi
SDK_DIR="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
if [[ -z "$SDK_DIR" ]]; then
    echo 'Lab APK not built: set ANDROID_HOME to the prepared Android SDK.' >&2
    exit 2
fi
GRADLE_COMMAND="${GRADLE_BIN:-$REPO_DIR/gradlew}"
RESULT_DIR="${LAB_RESULT_DIR:-${TMPDIR:-/tmp}/telegram-ipv6-lab-apk-results}"
mkdir -p -- "$RESULT_DIR"
python3 "$SCRIPT_DIR/check-environment.py" --sdk "$SDK_DIR" --gradle "$GRADLE_COMMAND" \
    --output "$RESULT_DIR/environment.json"

export PATH="$JAVA_HOME/bin:$PATH"
export ANDROID_HOME="$SDK_DIR"
export ANDROID_SDK_ROOT="$SDK_DIR"
export GRADLE_USER_HOME="${GRADLE_USER_HOME:-${TMPDIR:-/tmp}/telegram-ipv6-lab-gradle}"
set +e
"$GRADLE_COMMAND" --console=plain --no-daemon --no-parallel --max-workers=1 \
    '-Dorg.gradle.jvmargs=-Xmx3g -XX:MaxMetaspaceSize=768m' \
    -PIPV6_LAB=true :TMessagesProj_App:assembleAfatDebug \
    2>&1 | tee "$RESULT_DIR/assemble.log"
build_status=${PIPESTATUS[0]}
set -e
if (( build_status != 0 )); then exit "$build_status"; fi

APK_PATH="$REPO_DIR/TMessagesProj_App/build/outputs/apk/afat/debug/app.apk"
BUILD_TOOLS="$SDK_DIR/build-tools/36.0.0"
EXPECTED_PACKAGE=org.kkgpower.telegram.ipv6lab.beta
if [[ ! -f "$APK_PATH" ]]; then
    echo 'Gradle returned success, but the expected APK is absent.' >&2
    exit 1
fi
"$BUILD_TOOLS/aapt" dump badging "$APK_PATH" > "$RESULT_DIR/apk-badging.txt"
"$BUILD_TOOLS/apksigner" verify --verbose --print-certs "$APK_PATH" > "$RESULT_DIR/apk-signature.txt"
"$JAVA_HOME/bin/keytool" -exportcert -keystore "$LAB_KEYSTORE" -alias "$LAB_KEY_ALIAS" \
    -storepass:env LAB_STORE_PASSWORD -file "$RESULT_DIR/signing-certificate.der"
python3 - "$RESULT_DIR" "$EXPECTED_PACKAGE" <<'PY'
import hashlib, re, sys
from pathlib import Path
result = Path(sys.argv[1])
badging = (result / "apk-badging.txt").read_text()
package = re.search(r"^package: name='([^']+)'", badging, re.MULTILINE)
if not package or package.group(1) != sys.argv[2]:
    raise SystemExit("Refusing APK: unexpected application ID")
if "application-label:'IPv6 Lab (unofficial)'" not in badging:
    raise SystemExit("Refusing APK: expected unofficial application label is absent")
native = re.search(r"^native-code: (.*)$", badging, re.MULTILINE)
if not native or set(re.findall(r"'([^']+)'", native.group(1))) != {"arm64-v8a"}:
    raise SystemExit("Refusing APK: expected an arm64-only native build")
digest = hashlib.sha256((result / "signing-certificate.der").read_bytes()).hexdigest()
signatures = (result / "apk-signature.txt").read_text().lower()
if "certificate sha-256 digest: " + digest not in signatures:
    raise SystemExit("Refusing APK: signing certificate does not match the supplied local key")
PY
OUTPUT_APK="$RESULT_DIR/telegram-ipv6-lab-unofficial-arm64.apk"
cp -- "$APK_PATH" "$OUTPUT_APK"
sha256sum "$OUTPUT_APK" > "$RESULT_DIR/apk.sha256"
git rev-parse HEAD > "$RESULT_DIR/source-commit.txt"
git submodule status --recursive > "$RESULT_DIR/submodules.txt"
git diff --binary > "$RESULT_DIR/working-tree.patch"
echo "Verified unofficial lab APK: $OUTPUT_APK"
echo "Keep build logs private until reviewed: $RESULT_DIR"
