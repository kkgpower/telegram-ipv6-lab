#!/usr/bin/env python3
"""Run offline configuration probes without Android SDK, AGP, or credentials.

Example:
  JAVA_HOME=/path/to/jdk-17 GRADLE_USER_HOME=/path/to/gradle-cache \
  GRADLE_BIN=/path/to/gradle-8.13/bin/gradle \
  python3 tools/ipv6-lab/test-profile.py

Gradle still uses local IPC sockets in offline mode, so a sandbox must permit
local networking for this test driver.

Only invalid inputs are supplied to enabled-profile probes. The invalid-hash
probe reads the public bundled API ID from BuildVars and fails before any
credential or keystore can be accepted. No signing files are created.
"""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


REPO = Path(__file__).resolve().parents[2]
RESULT = REPO / "docs/ipv6-lab-results/profile-probes.log"
PARAMETERS = (
    "TELEGRAM_API_ID", "TELEGRAM_API_HASH", "LAB_KEYSTORE",
    "LAB_STORE_PASSWORD", "LAB_KEY_PASSWORD", "LAB_KEY_ALIAS",
)
IGNORED_ENV = {
    "JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "GRADLE_OPTS",
    "ORG_GRADLE_PROJECT_IPV6_LAB",
}


def main():
    gradle = shutil.which(os.environ.get("GRADLE_BIN", "gradle"))
    if not gradle:
        raise RuntimeError("Set GRADLE_BIN to an installed Gradle 8.13 executable.")
    java_home = os.environ.get("JAVA_HOME")
    if not java_home or not (Path(java_home) / "bin/java").is_file():
        raise RuntimeError("Set JAVA_HOME to a complete JDK 17 installation.")
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("TELEGRAM_", "LAB_")) and key not in IGNORED_ENV
    }
    version = subprocess.run(
        [str(Path(java_home) / "bin/java"), "-version"], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True,
    ).stdout.splitlines()[0]
    if not re.search(r'version "17[.\"]', version):
        raise RuntimeError("Run these reproducibility probes with JDK 17.")
    source = REPO / "TMessagesProj/src/main/java/org/telegram/messenger/BuildVars.java"
    bundled_id = re.search(
        r"public static int APP_ID\s*=\s*[^;\n]*?(\d+)\s*;", source.read_text()
    )
    if not bundled_id:
        raise RuntimeError("Cannot locate the public bundled API ID in BuildVars.java.")

    log = [
        "Offline IPv6 Lab profile probes", version,
        "Gradle: 8.13 (required toolchain)",
        "All inherited TELEGRAM_* and LAB_* environment variables were removed.",
        "No valid API credentials, passwords, or signing files were supplied.",
        "Android SDK, AGP, APK compilation and device behavior are not tested.", "",
    ]
    passed = 0
    with tempfile.TemporaryDirectory(prefix="ipv6-lab-profile-probe-") as directory:
        project = Path(directory)
        (project / "settings.gradle").write_text(
            "rootProject.name = 'ipv6-lab-profile-probe'\n"
        )
        (project / "build.gradle").write_text(
            "apply from: System.getProperty('ipv6.lab.profile')\n"
            "tasks.register('probe') { doLast {\n"
            "    if (project.ext.ipv6LabBuild) {\n"
            "        throw new GradleException('Expected the disabled profile.')\n"
            "    }\n"
            "    println 'IPV6_LAB_PROFILE_DISABLED'\n"
            "} }\n"
        )
        invalid = {name: "invalid" for name in PARAMETERS}
        invalid["LAB_KEYSTORE"] = str(project / "unused-not-a-keystore")
        cases = [
            ("disabled", "false", {}, 0, "IPV6_LAB_PROFILE_DISABLED"),
            ("invalid-flag", "invalid", {}, 1, "IPV6_LAB must be true or false."),
            ("missing-env", "true", {}, 1, "IPv6 Lab requires environment variables: " + ", ".join(PARAMETERS) + "."),
            ("invalid-api-id", "true", invalid, 1, "TELEGRAM_API_ID must be a positive 32-bit integer"),
            ("invalid-api-hash", "true", {**invalid, "TELEGRAM_API_ID": bundled_id.group(1)}, 1, "TELEGRAM_API_HASH must be the 32 hexadecimal characters"),
        ]
        for name, flag, inputs, expected_exit, expected_message in cases:
            command = [
                gradle, "--offline", "--no-daemon", "--console=plain", "--max-workers=1",
                "-Dorg.gradle.jvmargs=-Xmx256m", "-Dorg.gradle.vfs.watch=false",
                f"-Dipv6.lab.profile={REPO / 'tools/ipv6-lab/profile.gradle'}",
                "-p", str(project), f"-PIPV6_LAB={flag}", "probe",
            ]
            try:
                result = subprocess.run(
                    command, env={**env, **inputs}, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, timeout=90,
                )
                output = "\n".join(line.rstrip() for line in result.stdout.splitlines())
                output = output.replace(str(project), "<probe>").replace(str(REPO), "<repo>")
                success = result.returncode == expected_exit and expected_message in output
                actual_exit = str(result.returncode)
            except subprocess.TimeoutExpired:
                output, success, actual_exit = "Probe timed out after 90 seconds.\n", False, "timeout"
            passed += int(success)
            status = "PASS" if success else "FAIL"
            log.extend([
                f"{status} {name}: expected exit {expected_exit}, actual exit {actual_exit}",
                f"Expected diagnostic: {expected_message}", output.rstrip(), "",
            ])
            print(f"{status} {name}: expected exit {expected_exit}, actual exit {actual_exit}", flush=True)
    log.append(f"{passed}/5 probes passed")
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text("\n".join(log) + "\n")
    print(f"{passed}/5 probes passed; log: {RESULT.relative_to(REPO)}")
    return 0 if passed == 5 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Profile probes could not run: {error}", file=sys.stderr)
        sys.exit(2)
