#!/usr/bin/env python3
"""Prepare pinned APK build prerequisites without Telegram API parameters.

Environment:
  JAVA_HOME, ANDROID_HOME       Complete JDK 17 and Android SDK root.
  GRADLE_BIN                   Preserve a supplied, working Gradle 8.13 executable.
  INFRA_REPORT_DIR             Reports outside the repository (default /tmp/telegram-ipv6-lab-infra).
  INFRA_TOOL_DIR               Downloaded tools outside the repository (default temporary tools directory).
  INFRA_ACCEPT_ANDROID_LICENSES=1  Explicitly accept SDK licenses through sdkmanager, suitable for CI.
  INFRA_JAVA_TRUSTSTORE        Optional existing trusted CA store for sdkmanager only.
  INFRA_PREPARE_SOURCES=0      Skip full checkout and pinned submodule initialization.
  INFRA_SKIP_SDK=1             Skip SDK package installation.
  INFRA_MIN_FREE_GIB           Free-space guard before each large stage (default 4).

No API or signing credentials are read. TLS verification and inherited proxies
remain enabled. An existing sdkmanager is required; this script does not invent
license files or remove unrelated SDKs, caches, files or source changes.
"""

import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from submodule_state import inspect_submodules


GRADLE_VERSION = "8.13"
GRADLE_SHA256 = "20f1b1176237254a6fc204d8434196fa11a4cfb387567519c61556e8710aed78"
GRADLE_URL = "https://services.gradle.org/distributions/gradle-8.13-bin.zip"
PACKAGES = ("platform-tools", "platforms;android-36", "build-tools;36.0.0",
            "ndk;27.2.12479018", "cmake;3.22.1")
ARCHIVES = ("libavcodec.a", "libavformat.a", "libavutil.a", "libcrypto.a",
            "libdav1d.a", "libiwasm.a", "libopenh264.a", "libopus.a", "libssl.a",
            "libswresample.a", "libswscale.a", "libtde2e.a", "libtdutils.a",
            "libtlottie.a", "libvpx.a", "libwallet_engine.a")


class PreparationError(Exception):
    pass


def flag(name, default):
    value = os.environ.get(name, default)
    if value not in ("0", "1"):
        raise PreparationError(name + " must be 0 or 1")
    return value == "1"


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")
    path.chmod(0o600)


def available_bytes(path):
    while not path.exists() and path != path.parent:
        path = path.parent
    return shutil.disk_usage(path).free


def resources(repo, sdk, tools):
    def disk(path):
        while not path.exists() and path != path.parent:
            path = path.parent
        return shutil.disk_usage(path)

    repo_disk, sdk_disk, tool_disk = (disk(p) for p in (repo, sdk, tools))
    result = {
        "checked_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "disk_total_bytes": repo_disk.total,
        "repo_free_bytes": repo_disk.free,
        "sdk_disk_total_bytes": sdk_disk.total,
        "sdk_free_bytes": sdk_disk.free,
        "tool_directory_disk_total_bytes": tool_disk.total,
        "tool_directory_free_bytes": tool_disk.free,
        "host_logical_cpus": os.cpu_count(),
        "runner_image": {name: os.environ[name] for name in
                         ("ImageOS", "ImageVersion", "RUNNER_ARCH", "RUNNER_OS") if name in os.environ},
    }
    memory_info = Path("/proc/meminfo")
    if memory_info.is_file():
        content = memory_info.read_text()
        for name in ("MemTotal", "MemAvailable"):
            found = re.search(r"^" + name + r":\s*(\d+)\s+kB", content, re.MULTILINE)
            if found:
                result["host_" + name + "_bytes"] = int(found.group(1)) * 1024
    for name in ("memory.max", "memory.current", "cpu.max"):
        path = Path("/sys/fs/cgroup") / name
        if path.is_file():
            result["cgroup_" + name.replace(".", "_")] = path.read_text().strip()
    quota = result.get("cgroup_cpu_max", "").split()
    if len(quota) == 2 and quota[0] != "max":
        result["cgroup_cpu_quota_cores"] = int(quota[0]) / int(quota[1])
        result["effective_cpu_capacity_cores"] = min(result["host_logical_cpus"] or math.inf,
                                                    result["cgroup_cpu_quota_cores"])
    else:
        result["effective_cpu_capacity_cores"] = result["host_logical_cpus"]
    return result


def property_value(path, name):
    if not path.is_file():
        return None
    match = re.search(r"^" + re.escape(name) + r"\s*=\s*(.*?)\s*$",
                      path.read_text(errors="replace"), re.MULTILINE)
    return match.group(1) if match else None


def sdk_inventory(sdk):
    specs = {
        "platform-tools": ("platform-tools/adb", "platform-tools/source.properties", None),
        "platforms;android-36": ("platforms/android-36/android.jar", "platforms/android-36/source.properties", None),
        "build-tools;36.0.0": ("build-tools/36.0.0/apksigner", "build-tools/36.0.0/source.properties", "36.0.0"),
        "ndk;27.2.12479018": ("ndk/27.2.12479018/toolchains/llvm/prebuilt/linux-x86_64/bin/clang++", "ndk/27.2.12479018/source.properties", "27.2.12479018"),
        "cmake;3.22.1": ("cmake/3.22.1/bin/cmake", "cmake/3.22.1/source.properties", "3.22.1"),
    }
    result = {}
    for name, (binary, props, expected) in specs.items():
        revision = property_value(sdk / props, "Pkg.Revision")
        present = (sdk / binary).is_file()
        if expected:
            present = present and revision == expected
        if name == "platforms;android-36":
            present = present and property_value(sdk / props, "AndroidVersion.ApiLevel") == "36"
        if name == "build-tools;36.0.0":
            present = present and all((sdk / "build-tools/36.0.0" / n).is_file()
                                      for n in ("aapt", "aapt2", "zipalign"))
        if name == "cmake;3.22.1":
            present = present and (sdk / "cmake/3.22.1/bin/ninja").is_file()
        result[name] = {"present": present, "revision": revision}
    return result


def sdk_proxy_arguments():
    # sdkmanager supports a single proxy, so honor NO_PROXY for its primary host.
    if urllib.request.proxy_bypass("dl.google.com"):
        return []
    proxies = urllib.request.getproxies()
    value = proxies.get("https") or proxies.get("http")
    if not value:
        return []
    parsed = urllib.parse.urlsplit(value if "://" in value else "http://" + value)
    if parsed.username or parsed.password:
        raise PreparationError("sdkmanager proxy authentication needs separately configured supported tooling; proxy credentials are not copied to command arguments")
    mode = {"http": "http", "socks": "socks", "socks5": "socks"}.get(parsed.scheme)
    if not mode or not parsed.hostname:
        raise PreparationError("The inherited SDK proxy scheme is not supported by sdkmanager")
    port = parsed.port or (1080 if mode == "socks" else 80)
    return ["--proxy=" + mode, "--proxy_host=" + parsed.hostname, "--proxy_port=" + str(port)]


def download_gradle(tools, log):
    target = tools / ("gradle-" + GRADLE_VERSION)
    if target.exists():
        return target / "bin/gradle", False
    tools.mkdir(parents=True, exist_ok=True)
    archive = tools / ("gradle-" + GRADLE_VERSION + "-bin.zip.part")
    if archive.exists():
        raise PreparationError("A previous Gradle partial download exists; preserve or remove it explicitly before retrying")
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(GRADLE_URL, timeout=30) as response, archive.open("xb") as output:
            if not response.url.startswith("https://"):
                raise PreparationError("Gradle download redirected away from HTTPS")
            downloaded = 0
            while chunk := response.read(1024 * 1024):
                downloaded += len(chunk)
                if downloaded > 200 * 1024**2:
                    raise PreparationError("Gradle download exceeded the expected archive size budget")
                output.write(chunk)
                digest.update(chunk)
        if digest.hexdigest() != GRADLE_SHA256:
            raise PreparationError("Gradle archive SHA-256 does not match the pinned official checksum")
        # Extract into a temporary directory, preserving executable permissions.
        with tempfile.TemporaryDirectory(prefix="gradle-extract-", dir=tools) as directory:
            extract = Path(directory)
            with zipfile.ZipFile(archive) as bundle:
                for member in bundle.infolist():
                    destination = (extract / member.filename).resolve()
                    if extract.resolve() not in destination.parents or member.filename.split("/")[0] != "gradle-8.13":
                        raise PreparationError("Unexpected path in the verified Gradle archive")
                    bundle.extract(member, extract)
                    mode = (member.external_attr >> 16) & 0o777
                    if mode:
                        destination.chmod(mode)
            (extract / "gradle-8.13").rename(target)
        log.write("Verified official Gradle 8.13 archive SHA-256: " + GRADLE_SHA256 + "\n")
        log.flush()
        return target / "bin/gradle", True
    finally:
        archive.unlink(missing_ok=True)


def main():
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    os.umask(0o077)
    repo = Path(__file__).resolve().parents[2]
    report = Path(os.environ.get("INFRA_REPORT_DIR", "/tmp/telegram-ipv6-lab-infra")).expanduser().resolve()
    if report == repo or repo in report.parents:
        raise PreparationError("INFRA_REPORT_DIR must be outside the repository")
    report.mkdir(parents=True, exist_ok=True, mode=0o700)
    private = report / "private"
    private.mkdir(exist_ok=True, mode=0o700)
    log_path = private / "setup.log"
    log = log_path.open("a")
    log_path.chmod(0o600)
    state = {"status": "failed", "api_parameters_used": False, "apk_built": False}
    snapshots = {}
    stage = "configuration"
    sdk = tools = None

    def run(label, args, *, capture=False, input_text=None, interactive=False, env_override=None):
        nonlocal stage
        stage = label
        log.write("\nStage: " + label + "\n")
        log.flush()
        child_env = {key: value for key, value in os.environ.items()
                     if not key.startswith(("TELEGRAM_", "LAB_"))}
        if env_override:
            child_env.update(env_override)
        result = subprocess.run([str(x) for x in args], cwd=repo, env=child_env,
                                input=input_text, text=True, timeout=3600,
                                stdout=subprocess.PIPE if capture else (None if interactive else log),
                                stderr=subprocess.STDOUT if not interactive else None)
        output = result.stdout or ""
        if capture:
            log.write(output)
            log.flush()
        if result.returncode:
            raise PreparationError(label + " failed; inspect the private setup log")
        return output.rstrip()

    def disk_guard(label):
        nonlocal stage
        stage = label
        sample = resources(repo, sdk, tools)
        snapshots[label] = sample
        if min(sample["repo_free_bytes"], sample["sdk_free_bytes"], sample["tool_directory_free_bytes"]) < minimum_bytes:
            raise PreparationError("Less than the configured free-space reserve before " + label)

    try:
        skip_sdk = flag("INFRA_SKIP_SDK", "0")
        prepare_sources = flag("INFRA_PREPARE_SOURCES", "1")
        accept_licenses = flag("INFRA_ACCEPT_ANDROID_LICENSES", "0")
        try:
            minimum_gib = float(os.environ.get("INFRA_MIN_FREE_GIB", "4"))
            if not math.isfinite(minimum_gib) or minimum_gib < 0:
                raise ValueError()
            minimum_bytes = int(minimum_gib * 1024**3)
        except ValueError:
            raise PreparationError("INFRA_MIN_FREE_GIB must be a non-negative finite number")
        sdk_value = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
        java_value = os.environ.get("JAVA_HOME")
        if not sdk_value or not java_value:
            raise PreparationError("Set ANDROID_HOME and JAVA_HOME to the prepared SDK and complete JDK 17")
        sdk = Path(sdk_value).expanduser().resolve()
        java = Path(java_value).expanduser().resolve()
        tools = Path(os.environ.get("INFRA_TOOL_DIR", str(Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "telegram-ipv6-lab-infra-tools"))).expanduser().resolve()
        if tools == repo or repo in tools.parents:
            raise PreparationError("INFRA_TOOL_DIR must be outside the repository")
        for value in (str(java), str(sdk), str(tools), str(report)):
            if "\n" in value or "\r" in value:
                raise PreparationError("Tool paths must not contain line breaks")
        os.environ.update(JAVA_HOME=str(java), ANDROID_HOME=str(sdk), ANDROID_SDK_ROOT=str(sdk))
        os.environ["PATH"] = str(java / "bin") + os.pathsep + os.environ.get("PATH", "")
        os.environ.setdefault("GRADLE_USER_HOME", str(tools / "gradle-user-home"))
        os.environ.setdefault("ANDROID_USER_HOME", str(tools / "android-user-home"))
        if not all((java / "bin" / name).is_file() for name in ("java", "javac", "jlink")):
            raise PreparationError("JAVA_HOME must contain java, javac and jlink")
        java_output = run("JDK version", [java / "bin/java", "-version"], capture=True)
        java_version = next((line for line in java_output.splitlines()
                             if line.startswith(("openjdk version ", "java version "))), "")
        if not re.search(r'version "17(?:[.\"])', java_version):
            raise PreparationError("Use the tested complete JDK 17 for infrastructure preparation")
        state.update(source_commit=run("source commit", ["git", "rev-parse", "HEAD"], capture=True),
                     source_has_tracked_changes=bool(run("source state", ["git", "status", "--porcelain", "--untracked-files=no"], capture=True)),
                     java={"home": str(java), "version": java_version}, sdk_root=str(sdk),
                     prepare_sources_requested=prepare_sources, sdk_install_skipped=skip_sdk,
                     free_space_reserve_gib=minimum_gib)
        disk_guard("initial")

        print("Preparing pinned Gradle 8.13", flush=True)
        stage = "Gradle preparation"
        candidate_value = os.environ.get("GRADLE_BIN")
        candidate = shutil.which(candidate_value) if candidate_value else shutil.which("gradle")
        if candidate_value and not candidate:
            raise PreparationError("The supplied GRADLE_BIN is not an executable")
        verified_download = False
        if candidate:
            output = run("Gradle version", [candidate, "--version"], capture=True)
            if not re.search(r"^Gradle 8\.13$", output, re.MULTILINE):
                if candidate_value:
                    raise PreparationError("The supplied GRADLE_BIN does not report Gradle 8.13")
                candidate = None
        if not candidate:
            candidate, verified_download = download_gradle(tools, log)
            output = run("downloaded Gradle version", [candidate, "--version"], capture=True)
            if not re.search(r"^Gradle 8\.13$", output, re.MULTILINE):
                raise PreparationError("The downloaded Gradle executable does not report the pinned version")
        gradle = str(Path(candidate).resolve())
        state["gradle"] = {"executable": gradle, "version": GRADLE_VERSION,
                           "download_sha256_verified_this_run": verified_download,
                           "expected_archive_sha256": GRADLE_SHA256}

        if not skip_sdk:
            disk_guard("SDK installation")
            print("Preparing pinned Android SDK packages", flush=True)
            manager = next((p for p in (sdk / "cmdline-tools/22.0/bin/sdkmanager", sdk / "cmdline-tools/latest/bin/sdkmanager") if p.is_file()), None)
            manager = manager or shutil.which("sdkmanager")
            if not manager:
                raise PreparationError("Install trusted Android command-line tools first; sdkmanager was not found")
            state["sdkmanager"] = str(Path(manager).resolve())
            sdk_env = {}
            if os.environ.get("INFRA_JAVA_TRUSTSTORE"):
                truststore = Path(os.environ["INFRA_JAVA_TRUSTSTORE"]).expanduser().resolve()
                if not truststore.is_file() or not os.access(truststore, os.R_OK):
                    raise PreparationError("INFRA_JAVA_TRUSTSTORE must point to an existing readable trusted CA store")
                if "\n" in str(truststore) or "\r" in str(truststore):
                    raise PreparationError("Truststore paths must not contain line breaks")
                # sdkmanager's launcher accepts SDKMANAGER_OPTS. Keep JAVA_OPTS
                # and all system trust settings unchanged outside this child.
                sdk_env["SDKMANAGER_OPTS"] = (os.environ.get("SDKMANAGER_OPTS", "") + " "
                                              + shlex.quote("-Djavax.net.ssl.trustStore=" + str(truststore))).strip()
                state["sdk_java_truststore"] = str(truststore)
            proxy_args = sdk_proxy_arguments()
            manager_args = [manager, "--sdk_root=" + str(sdk), *proxy_args]
            state["sdk_proxy_enabled"] = bool(proxy_args)
            before = sdk_inventory(sdk)
            if not all(x["present"] for x in before.values()):
                if not accept_licenses and not sys.stdin.isatty():
                    raise PreparationError("Run SDK license acceptance interactively, or explicitly set INFRA_ACCEPT_ANDROID_LICENSES=1 for authorized CI installation")
                # Input is sent directly to sdkmanager, without a yes pipeline or
                # an ignored SIGPIPE. Its true exit status is always checked.
                consent = "y\n" * 256 if accept_licenses else None
                run("Android SDK licenses", [*manager_args, "--licenses"],
                    input_text=consent, interactive=not accept_licenses, env_override=sdk_env)
                run("Android SDK packages", [*manager_args, *PACKAGES], input_text=consent, env_override=sdk_env)
            packages = sdk_inventory(sdk)
            if not all(x["present"] for x in packages.values()):
                raise PreparationError("sdkmanager finished without all pinned SDK files and versions; inspect the private setup log")
            state["sdk_packages"] = packages
        else:
            state["sdk_packages"] = sdk_inventory(sdk)

        if prepare_sources:
            disk_guard("source checkout")
            print("Preparing the full checkout and pinned submodules", flush=True)
            sparse = subprocess.run(["git", "config", "--bool", "core.sparseCheckout"], cwd=repo,
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.strip()
            if sparse == "true":
                run("full sparse checkout", ["git", "sparse-checkout", "disable"])
            run("submodule URL sync", ["git", "submodule", "sync", "--recursive"])
            run("pinned recursive submodule checkout", ["git", "submodule", "update", "--init", "--recursive", "--depth", "1", "--jobs", "2"])

        status = run("submodule state", ["git", "submodule", "status", "--recursive"], capture=True)
        (report / "submodules.txt").write_text(status + "\n")
        module_state = inspect_submodules(repo, status)
        clean_submodules = not module_state["blocking"]
        state["submodules"] = {
            "count": len(status.splitlines()),
            "all_at_pinned_commits": clean_submodules and not module_state["intentionally_skipped"],
            "required_at_pinned_commits": clean_submodules,
            "intentionally_skipped": module_state["intentionally_skipped"],
            "blocking": module_state["blocking"],
        }
        if prepare_sources and not clean_submodules:
            raise PreparationError("Submodules are missing, modified or not at their pinned commits")
        archive_results = []
        for name in ARCHIVES:
            path = repo / "TMessagesProj/jni/prebuild/lib/arm64-v8a" / name
            valid = False
            if path.is_file():
                with path.open("rb") as stream:
                    valid = stream.read(8) == b"!<arch>\n"
            archive_results.append({"path": str(path.relative_to(repo)), "present": path.is_file(),
                                    "regular_ar_header": valid, "bytes": path.stat().st_size if path.is_file() else None})
        state["arm64_native_archives"] = archive_results
        if prepare_sources and not all(x["regular_ar_header"] for x in archive_results):
            raise PreparationError("One or more of the 16 required arm64 native archives are missing or invalid")

        exports = {"JAVA_HOME": str(java), "ANDROID_HOME": str(sdk), "ANDROID_SDK_ROOT": str(sdk),
                   "ANDROID_NDK_HOME": str(sdk / "ndk/27.2.12479018"), "GRADLE_BIN": gradle,
                   "GRADLE_USER_HOME": os.environ["GRADLE_USER_HOME"],
                   "ANDROID_USER_HOME": os.environ["ANDROID_USER_HOME"]}
        for value in exports.values():
            if "\n" in value or "\r" in value:
                raise PreparationError("Exported tool paths must not contain line breaks")
        env_file = report / "infra-env.sh"
        env_file.write_text("\n".join("export " + key + "=" + shlex.quote(value) for key, value in exports.items())
                            + '\nexport PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"\n')
        if os.environ.get("GITHUB_ENV"):
            with Path(os.environ["GITHUB_ENV"]).open("a") as env_output:
                env_output.writelines(key + "=" + value + "\n" for key, value in exports.items())
        state["status"] = "complete" if prepare_sources and not skip_sdk else "partial"
        print("Infrastructure preparation " + state["status"] + "; environment: " + str(env_file), flush=True)
        return 0
    except (PreparationError, OSError, subprocess.SubprocessError, urllib.error.URLError, ValueError, zipfile.BadZipFile) as error:
        message = str(error) if isinstance(error, PreparationError) else type(error).__name__
        state.update(status="failed", failed_stage=stage, diagnostic=message)
        print("Infrastructure preparation failed: " + message + ". Private log: " + str(log_path), file=sys.stderr)
        if os.environ.get("GITHUB_ACTIONS") == "true" and stage.startswith("Android SDK"):
            log.flush()
            with log_path.open("rb") as tail_file:
                tail_file.seek(max(0, log_path.stat().st_size - 65536))
                lines = tail_file.read().decode(errors="replace").splitlines()[-40:]
            marker = uuid.uuid4().hex
            print("::stop-commands::" + marker)
            print("SDK diagnostic tail (credentialless setup stage; at most 40 lines):")
            for line in lines:
                if re.search(r"password|passwd|token|secret|authorization|api.?hash|api.?key|https?://[^/\s@]+@", line, re.IGNORECASE):
                    print("[redacted diagnostic line]")
                else:
                    print(line[:500])
            print("::" + marker + "::")
        return 1
    finally:
        if sdk is not None and tools is not None:
            snapshots["final"] = resources(repo, sdk, tools)
            state.setdefault("sdk_packages", sdk_inventory(sdk))
        write_json(report / "resource-report.json", snapshots)
        write_json(report / "toolchain-report.json", state)
        log.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PreparationError as error:
        print("Infrastructure preparation failed: " + str(error), file=sys.stderr)
        raise SystemExit(2)
