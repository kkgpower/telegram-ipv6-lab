#!/usr/bin/env python3
"""Verify real Android native tooling and Gradle metadata without making an APK.

INFRA_VERIFY_NATIVE_ONLY=1 limits the check to the patched Android translation
unit, useful in a small local environment. The default additionally configures
the complete native project, builds tgnet, and resolves the Gradle dependency
metadata graph. No Telegram API parameters or signing keys are used.
"""

import datetime
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
import uuid


def main():
    repo = Path(__file__).resolve().parents[2]
    report = Path(os.environ.get("INFRA_REPORT_DIR", "/tmp/telegram-ipv6-lab-infra")).resolve()
    private = report / "private"
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    private.chmod(0o700)
    os.umask(0o077)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("TELEGRAM_", "LAB_"))}
    sdk = Path(env.get("ANDROID_HOME") or env.get("ANDROID_SDK_ROOT") or "/nonexistent-sdk")
    ndk = sdk / "ndk/27.2.12479018"
    compiler = ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin/clang++"
    cmake = sdk / "cmake/3.22.1/bin/cmake"
    ninja = sdk / "cmake/3.22.1/bin/ninja"
    gradle = env.get("GRADLE_BIN") or str(repo / "gradlew")
    native_only = env.get("INFRA_VERIFY_NATIVE_ONLY") == "1"
    results = {}

    def run(name, args, timeout):
        started = time.monotonic()
        log = private / (name + ".log")
        status = 127
        message = None
        with log.open("w") as output:
            try:
                process = subprocess.Popen([str(a) for a in args], cwd=repo, env=env,
                                           stdout=output, stderr=subprocess.STDOUT,
                                           start_new_session=True)
                try:
                    status = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    status, message = 124, "timeout"
            except OSError as error:
                message = type(error).__name__
                output.write("Cannot start required tool: " + message + "\n")
        results[name] = {"exit_code": status, "passed": status == 0,
                         "elapsed_seconds": round(time.monotonic() - started, 2)}
        if message:
            results[name]["diagnostic"] = message
        print(("PASS " if status == 0 else "FAIL ") + name + " (exit " + str(status) + ")", flush=True)
        if status and env.get("GITHUB_ACTIONS") == "true":
            # This verifier never receives API/signing parameters. Keep signed
            # builds separate, and disable workflow commands around tool output.
            token = uuid.uuid4().hex
            print("::stop-commands::" + token, flush=True)
            for line in log.read_text(errors="replace").splitlines()[-40:]:
                if re.search(r"password|authorization|api_hash|api_id|access_token", line, re.IGNORECASE):
                    print("<credential-related diagnostic omitted>")
                else:
                    print(line[:1000])
            print("::" + token + "::", flush=True)
        return status == 0

    compiled = run("android-connection-socket", [
        compiler, "--target=aarch64-linux-android23", "-std=c++17", "-DANDROID",
        "-DHAVE_PTHREAD", "-fPIC",
        "-I" + str(repo / "TMessagesProj/jni/third_party/boringssl/include"),
        "-I" + str(repo / "TMessagesProj/jni/openssl/include"),
        "-c", repo / "TMessagesProj/jni/tgnet/ConnectionSocket.cpp",
        "-o", private / "ConnectionSocket.android-arm64.o",
    ], 300)
    if compiled:
        header = (private / "ConnectionSocket.android-arm64.o").read_bytes()[:20]
        valid = (len(header) == 20 and header[:6] == b"\x7fELF\x02\x01"
                 and int.from_bytes(header[16:18], "little") == 1
                 and int.from_bytes(header[18:20], "little") == 183)
        results["android-connection-socket"]["aarch64_elf_relocatable"] = valid
        if not valid:
            results["android-connection-socket"]["passed"] = False
            print("FAIL android-connection-socket: expected an AArch64 ELF object", flush=True)

    if not native_only:
        free = shutil.disk_usage(report).free
        if free < 2 * 1024**3:
            results["full-infrastructure"] = {"passed": False, "diagnostic": "Less than 2 GiB free; preserving disk reserve"}
            print("FAIL full-infrastructure: less than 2 GiB free; skipped expensive checks", flush=True)
        else:
            build_dir = private / "cmake-arm64"
            configured = run("cmake-configure", [
                cmake, "-S", repo / "TMessagesProj/jni", "-B", build_dir, "-G", "Ninja",
                "-DCMAKE_MAKE_PROGRAM=" + str(ninja),
                "-DCMAKE_TOOLCHAIN_FILE=" + str(ndk / "build/cmake/android.toolchain.cmake"),
                "-DANDROID_ABI=arm64-v8a", "-DANDROID_PLATFORM=android-23",
                "-DANDROID_STL=c++_static", "-DCMAKE_BUILD_TYPE=Debug",
            ], 600)
            if configured:
                run("android-tgnet", [cmake, "--build", build_dir, "--target", "tgnet", "--parallel", "1"], 1800)
            else:
                results["android-tgnet"] = {"passed": False, "diagnostic": "Skipped because full native configuration failed"}
            resolved = run("gradle-dependency-metadata", [
                gradle, "--console=plain", "--no-daemon", "--no-parallel", "--max-workers=1",
                "-Dorg.gradle.jvmargs=-Xmx3g -XX:MaxMetaspaceSize=768m",
                "-PIPV6_LAB=false", ":TMessagesProj:dependencies", "--configuration", "debugCompileClasspath",
            ], 2400)
            if resolved:
                output = (private / "gradle-dependency-metadata.log").read_text(errors="replace")
                if re.search(r"\bFAILED\b", output):
                    results["gradle-dependency-metadata"]["passed"] = False
                    results["gradle-dependency-metadata"]["diagnostic"] = "Dependency report contains unresolved entries despite Gradle exit 0"
                    print("FAIL gradle-dependency-metadata: unresolved entries", flush=True)

    verified = all(r["passed"] for r in results.values())
    result = {
        "checked_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "mode": "android-translation-unit-only" if native_only else "full-infrastructure-without-apk",
        "checks": results, "passed": verified,
        "api_parameters_used": False, "apk_built": False,
        "limitations": "No complete application link, APK packaging, MTProto authentication or Android device test. Gradle dependency report verifies metadata, not all future artifact transforms.",
    }
    (report / "verification-report.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Infrastructure report: " + str(report / "verification-report.json"))
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
