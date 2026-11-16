#!/usr/bin/env python3
"""Read-only inventory for a lab APK build; never print credential values.

This checks prerequisites, not the final Android manifest or lab build profile.
See docs/ipv6-lab-apk.md for the additional application isolation requirements.
"""

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from submodule_state import inspect_submodules


def command(*args):
    result = subprocess.run(args, text=True, capture_output=True, timeout=30)
    return result.returncode, (result.stdout + result.stderr).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", help="Android SDK root; defaults to SDK environment variables")
    parser.add_argument("--gradle", help="Path to a Gradle executable")
    parser.add_argument("--output", type=Path, help="Write the JSON report to this file")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    _, commit = command("git", "-C", str(repo), "rev-parse", "HEAD")
    _, branch = command("git", "-C", str(repo), "branch", "--show-current")
    _, tracked_changes = command("git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no")
    modules_state = inspect_submodules(repo)
    missing_submodules = modules_state["blocking"]
    fixed_path = "TMessagesProj/jni/tgnet/ConnectionSocket.cpp"
    _, fixed_blob = command("git", "-C", str(repo), "rev-parse", "7f67b8a:" + fixed_path)
    _, current_blob = command("git", "-C", str(repo), "hash-object", fixed_path)
    configured_java = Path(os.environ["JAVA_HOME"]) / "bin/java" if os.environ.get("JAVA_HOME") else None
    java = str(configured_java) if configured_java and configured_java.is_file() else shutil.which("java")
    java_status, java_version = command(java, "-version") if java else (1, "unavailable")
    _, modules = command(java, "--list-modules") if java else (1, "")
    java_root = Path(java).resolve().parents[1] if java else None
    gradle = args.gradle or shutil.which("gradle")
    sdk_arg = args.sdk or os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    sdk = Path(sdk_arg).expanduser() if sdk_arg else None
    required_sdk_files = {
        "platforms;android-36": "platforms/android-36/android.jar",
        "build-tools;36.0.0": "build-tools/36.0.0/apksigner",
        "ndk;27.2.12479018": "ndk/27.2.12479018/source.properties",
        "cmake;3.22.1": "cmake/3.22.1/bin/cmake",
    }
    sdk_checks = {name: bool(sdk and (sdk / path).is_file())
                  for name, path in required_sdk_files.items()}
    _, paths = command("git", "-C", str(repo), "ls-tree", "-r", "--name-only", "HEAD",
                       "TMessagesProj/jni/prebuild/lib/arm64-v8a")
    missing_prebuilts = [path for path in paths.splitlines()
                         if path.endswith(".a") and not (repo / path).is_file()]
    api_id = os.environ.get("TELEGRAM_API_ID", "").strip()
    api_hash = os.environ.get("TELEGRAM_API_HASH", "").strip()
    api_format = bool(re.fullmatch(r"[1-9][0-9]{0,9}", api_id)
                      and int(api_id) <= 2147483647
                      and re.fullmatch(r"[0-9a-fA-F]{32}", api_hash))
    build_vars = (repo / "TMessagesProj/src/main/java/org/telegram/messenger/BuildVars.java").read_text()
    shipped_id = re.search(r'public static int APP_ID\s*=\s*[^;\n]*?(\d+)\s*;', build_vars)
    shipped_hash = re.search(r'public static String APP_HASH\s*=\s*[^;\n]*?"([0-9a-fA-F]+)"\s*;', build_vars)
    shipped_pair = bool(api_format and shipped_id and shipped_hash
                        and (api_id == shipped_id.group(1)
                             or api_hash.lower() == shipped_hash.group(1).lower()))
    if not shipped_id or not shipped_hash:
        api_format = False
    blockers = []
    if current_blob != fixed_blob:
        blockers.append("ConnectionSocket.cpp differs from the reviewed 7f67b8a fix")
    if java_status or "jdk.compiler@" not in modules:
        blockers.append("A working Java runtime with the compiler module is required")
    if not gradle or not Path(gradle).is_file():
        blockers.append("Gradle 8.13 distribution is unavailable; the wrapper alone is not a distribution")
    blockers.extend("Missing SDK package: " + name for name, found in sdk_checks.items() if not found)
    if missing_submodules:
        blockers.append("Pinned submodules are not initialized")
    if missing_prebuilts:
        blockers.append("Tracked arm64 native archives are outside the sparse checkout")
    if not api_format or shipped_pair:
        blockers.append("Supply your own TELEGRAM_API_ID and TELEGRAM_API_HASH; shipped values are not accepted")
    report = {
        "checked_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "commit": commit, "branch": branch,
        "working_tree_has_tracked_changes": bool(tracked_changes),
        "ipv6_source_matches_7f67b8a": current_blob == fixed_blob,
        "java_version": next((line for line in java_version.splitlines()
                              if line.startswith(('openjdk version ', 'java version '))),
                             "version not detected"),
        "java_compiler_module": "jdk.compiler@" in modules,
        "standard_javac_binary": bool(java_root and (java_root / "bin/javac").is_file()),
        "standard_jlink_binary": bool(java_root and (java_root / "bin/jlink").is_file()),
        "gradle_executable": gradle,
        "sdk_root": str(sdk) if sdk else None,
        "sdk_packages_present": sdk_checks,
        "uninitialized_submodules": missing_submodules,
        "intentionally_skipped_submodules": modules_state["intentionally_skipped"],
        "missing_arm64_native_archives": len(missing_prebuilts),
        "own_api_parameters_present_and_format_valid": api_format and not shipped_pair,
        "free_disk_bytes": shutil.disk_usage(repo).free,
        "blocking_prerequisites": blockers,
        "scope": "Environment inventory only; the opt-in lab profile exists, but Android assembly and device tests remain unverified",
        "apk_produced": False,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
