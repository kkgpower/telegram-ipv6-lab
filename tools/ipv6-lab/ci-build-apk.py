#!/usr/bin/env python3
"""Build a signed lab APK in GitHub Actions without publishing raw secret-bearing output.

Only explicit build tags or a build-apk dispatch from the reviewed CI branch are
accepted. The final APK necessarily contains the Telegram client API parameters.
No private key, Gradle cache, generated BuildConfig or raw log is an artifact.
"""

import argparse
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile


REPOSITORY = "kkgpower/telegram-ipv6-lab"
CI_REF = "refs/heads/ci/ipv6-lab-apk-infrastructure"
BASE_COMMIT = "e3bde6d2a7a2835ac2a36754c662dbc89715b160"
APK_NAME = "telegram-ipv6-lab-unofficial-arm64.apk"
REQUIRED = (
    "TELEGRAM_API_ID", "TELEGRAM_API_HASH", "LAB_KEYSTORE_BASE64",
    "LAB_STORE_PASSWORD", "LAB_KEY_PASSWORD", "LAB_KEY_ALIAS",
)
GENERATED = (
    ".gradle", "build", "buildSrc/.gradle", "buildSrc/build",
    "TMessagesProj/.cxx", "TMessagesProj/build",
    "TMessagesProj_App/.cxx", "TMessagesProj_App/build",
)


class BuildError(Exception):
    """A fixed diagnostic that never includes credential values or raw output."""


def git(repo, *args):
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=False, capture_output=True,
        text=True, timeout=30,
    )
    if result.returncode:
        raise BuildError("Cannot verify the checked-out source; no APK was published.")
    return result.stdout.strip()


def locations():
    repo = Path(__file__).resolve().parents[2]
    value = os.environ.get("RUNNER_TEMP", "")
    if not value:
        raise BuildError("RUNNER_TEMP is required for private signing files.")
    root = Path(value).resolve(strict=True)
    if not root.is_dir() or root == repo or repo in root.parents or root in repo.parents:
        raise BuildError("RUNNER_TEMP must be a directory outside the source checkout.")
    workspace = os.environ.get("GITHUB_WORKSPACE", "")
    if not workspace or Path(workspace).resolve(strict=True) != repo:
        raise BuildError("GITHUB_WORKSPACE must match the source checkout before cleanup or signing.")
    return repo, root


def require_actions():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise BuildError("This helper is restricted to the intended GitHub Actions repository.")


def remove(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def cleanup(repo, root, *, include_public):
    paths = list(root.glob("ipv6-lab-secret-*"))
    paths.append(root / "ipv6-lab-gradle")
    if include_public:
        paths.append(root / "ipv6-lab-public")
    failed = False
    for name in GENERATED:
        path = repo / name
        # Never follow a symlinked project directory to delete an outside build.
        parent = path.parent.resolve()
        if parent != repo and repo not in parent.parents:
            failed = True
        else:
            paths.append(path)
    for path in paths:
        try:
            remove(path)
        except OSError:
            failed = True
    if failed:
        raise BuildError("Private-file cleanup did not complete; refusing to publish an APK.")


def verify_event():
    require_actions()
    event, ref = os.environ.get("GITHUB_EVENT_NAME"), os.environ.get("GITHUB_REF", "")
    allowed = event == "push" and re.fullmatch(r"refs/tags/ipv6-lab-build-[A-Za-z0-9][A-Za-z0-9._-]*", ref)
    if event == "workflow_dispatch" and ref == CI_REF:
        try:
            payload = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
            allowed = payload.get("inputs", {}).get("mode") == "build-apk"
        except (KeyError, OSError, ValueError):
            allowed = False
    if not allowed:
        raise BuildError("Use an explicit lab build tag or build-apk dispatch from the CI branch.")
    expected_workflow = REPOSITORY + "/.github/workflows/ipv6-lab.yml@" + ref
    if os.environ.get("GITHUB_WORKFLOW_REF") != expected_workflow:
        raise BuildError("The triggering workflow path and ref are not the reviewed lab workflow.")


def verify_context(repo):
    verify_event()
    commit = git(repo, "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or commit != os.environ.get("GITHUB_SHA"):
        raise BuildError("The checkout does not match the triggering commit.")
    git(repo, "merge-base", "--is-ancestor", BASE_COMMIT, commit)
    git(repo, "merge-base", "--is-ancestor", commit,
        "refs/remotes/origin/ci/ipv6-lab-apk-infrastructure")
    if git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise BuildError("The source checkout has tracked changes; refusing the signed build.")
    return commit


def stop_process(process):
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


def build(repo, root):
    commit = verify_context(repo)
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        raise BuildError("Lab APK not built: missing GitHub Secrets: " + ", ".join(missing))
    encoded = os.environ["LAB_KEYSTORE_BASE64"].strip()
    try:
        if len(encoded.encode("utf-8")) > 48 * 1024:
            raise ValueError()
        key_bytes = base64.b64decode(encoded, validate=True)
        if not key_bytes:
            raise ValueError()
    except (ValueError, binascii.Error):
        raise BuildError("LAB_KEYSTORE_BASE64 must contain the real keystore as single-line base64 within the GitHub secret size limit.") from None

    public = root / "ipv6-lab-public"
    if public.exists() or public.is_symlink():
        raise BuildError("The public output directory already exists; refusing stale artifacts.")
    gradle_home = root / "ipv6-lab-gradle"
    private = Path(tempfile.mkdtemp(prefix="ipv6-lab-secret-", dir=root))
    private.chmod(0o700)
    succeeded = False
    try:
        keystore = private / "signing-key.p12"
        with keystore.open("xb") as stream:
            stream.write(key_bytes)
        keystore.chmod(0o600)
        result = private / "results"
        env = dict(os.environ, LAB_KEYSTORE=str(keystore), LAB_RESULT_DIR=str(result),
                   GRADLE_USER_HOME=str(gradle_home))
        env.pop("LAB_KEYSTORE_BASE64", None)
        # The original build helper uses tee. Redirect its entire output here;
        # neither exact GitHub masking nor transformed-secret masking is relied on.
        with (private / "build-output.log").open("wb") as output:
            process = subprocess.Popen(
                ["bash", str(repo / "tools/ipv6-lab/build-apk.sh")], cwd=repo,
                env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True,
            )
            try:
                status = process.wait(timeout=270 * 60)
            except BaseException:
                stop_process(process)
                raise
        if status:
            raise BuildError("The signed lab build failed. Raw build output was not published.")

        names = (APK_NAME, "signing-certificate.der", "source-commit.txt", "submodules.txt")
        if any((result / name).is_symlink() or not (result / name).is_file() for name in names):
            raise BuildError("The verified build outputs are incomplete; no artifact was published.")
        if (result / "source-commit.txt").read_text().strip() != commit:
            raise BuildError("The result source commit changed during the build.")
        public.mkdir(mode=0o700)
        for name in names:
            shutil.copyfile(result / name, public / name)
        apk_digest = hashlib.file_digest((public / APK_NAME).open("rb"), "sha256").hexdigest()
        cert_digest = hashlib.sha256((public / "signing-certificate.der").read_bytes()).hexdigest()
        (public / "apk.sha256").write_text(apk_digest + "  " + APK_NAME + "\n")
        provenance = {
            "repository": REPOSITORY, "source_commit": commit,
            "ref": os.environ["GITHUB_REF"],
            "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "application_id": "org.kkgpower.telegram.ipv6lab.beta", "abi": "arm64-v8a",
            "unofficial_test_build": True,
            "apk_sha256": apk_digest, "certificate_sha256": cert_digest,
            "api_parameters_are_embedded_in_apk": True,
        }
        (public / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
        succeeded = True
    finally:
        cleanup(repo, root, include_public=not succeeded)
    print("Verified unofficial APK and public provenance are ready for the explicit artifact allowlist.")


def interrupted(_signum, _frame):
    raise BuildError("The signed build was interrupted; no raw output was published.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleanup", action="store_true", help="Remove known temporary signing and generated output paths")
    args = parser.parse_args()
    os.umask(0o077)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        require_actions()
        repo, root = locations()
        if args.cleanup:
            verify_event()
            cleanup(repo, root, include_public=True)
        else:
            build(repo, root)
        return 0
    except BuildError as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception:
        print("The lab CI helper failed; credentials and raw build output were not published.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
