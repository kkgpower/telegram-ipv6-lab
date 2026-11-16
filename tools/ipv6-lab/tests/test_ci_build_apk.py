"""CI security guard tests; subprocesses and GitHub context are mocked, no APK is built."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


HELPER = Path(__file__).resolve().parents[1] / "ci-build-apk.py"
SPEC = importlib.util.spec_from_file_location("ipv6_lab_ci", HELPER)
CI = importlib.util.module_from_spec(SPEC)
old_bytecode_setting = sys.dont_write_bytecode
try:
    sys.dont_write_bytecode = True
    SPEC.loader.exec_module(CI)
finally:
    sys.dont_write_bytecode = old_bytecode_setting


class CIBuildGuards(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ipv6-lab-ci-test-")
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.repo = self.base / "repo"
        self.root = self.base / "runner"
        self.repo.mkdir()
        self.root.mkdir()
        self.sha = "a" * 40
        self.tag = "refs/tags/ipv6-lab-build-unit-test"
        self.context = {
            "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": CI.REPOSITORY,
            "GITHUB_EVENT_NAME": "push", "GITHUB_REF": self.tag,
            "GITHUB_SHA": self.sha,
            "GITHUB_WORKFLOW_REF": self.workflow(self.tag),
            "GITHUB_WORKSPACE": str(self.repo), "RUNNER_TEMP": str(self.root),
        }

    @staticmethod
    def workflow(ref):
        return CI.REPOSITORY + "/.github/workflows/ipv6-lab.yml@" + ref

    def fake_git(self, _repo, *args):
        return self.sha if args == ("rev-parse", "HEAD") else ""

    def event(self, mode):
        path = self.base / "event.json"
        path.write_text(json.dumps({"inputs": {"mode": mode}}))
        return {
            **self.context, "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": CI.CI_REF, "GITHUB_WORKFLOW_REF": self.workflow(CI.CI_REF),
            "GITHUB_EVENT_PATH": str(path),
        }

    def test_explicit_build_tag_context(self):
        with patch.dict(os.environ, self.context, clear=True), patch.object(CI, "git", self.fake_git):
            self.assertEqual(CI.verify_context(self.repo), self.sha)

    def test_explicit_build_dispatch_context(self):
        with patch.dict(os.environ, self.event("build-apk"), clear=True), patch.object(CI, "git", self.fake_git):
            self.assertEqual(CI.verify_context(self.repo), self.sha)

    def test_validation_dispatch_does_not_sign(self):
        with patch.dict(os.environ, self.event("validate"), clear=True), self.assertRaises(CI.BuildError):
            CI.verify_context(self.repo)

    def test_ordinary_branch_push_does_not_sign(self):
        env = {**self.context, "GITHUB_REF": CI.CI_REF, "GITHUB_WORKFLOW_REF": self.workflow(CI.CI_REF)}
        with patch.dict(os.environ, env, clear=True), self.assertRaises(CI.BuildError):
            CI.verify_context(self.repo)

    def test_foreign_repository_rejected(self):
        with patch.dict(os.environ, {**self.context, "GITHUB_REPOSITORY": "other/repository"}, clear=True):
            with self.assertRaises(CI.BuildError):
                CI.require_actions()

    def test_wrong_workflow_ref_rejected(self):
        env = {**self.context, "GITHUB_WORKFLOW_REF": "other/repository/.github/workflows/build.yml@main"}
        with patch.dict(os.environ, env, clear=True), self.assertRaises(CI.BuildError):
            CI.verify_context(self.repo)

    def test_source_commit_mismatch_rejected(self):
        env = {**self.context, "GITHUB_SHA": "b" * 40}
        with patch.dict(os.environ, env, clear=True), patch.object(CI, "git", self.fake_git):
            with self.assertRaises(CI.BuildError):
                CI.verify_context(self.repo)

    def test_commit_must_belong_to_ci_branch(self):
        def not_on_ci_branch(repo, *args):
            if args[-1] == "refs/remotes/origin/ci/ipv6-lab-apk-infrastructure":
                raise CI.BuildError("Unit fixture is outside the reviewed branch")
            return self.fake_git(repo, *args)
        with patch.dict(os.environ, self.context, clear=True), patch.object(CI, "git", not_on_ci_branch):
            with self.assertRaises(CI.BuildError):
                CI.verify_context(self.repo)

    def test_tracked_source_changes_rejected(self):
        def dirty(repo, *args):
            return " M changed-source" if args[0] == "status" else self.fake_git(repo, *args)
        with patch.dict(os.environ, self.context, clear=True), patch.object(CI, "git", dirty):
            with self.assertRaises(CI.BuildError):
                CI.verify_context(self.repo)

    def test_missing_secrets_stop_before_key_creation(self):
        with patch.dict(os.environ, self.context, clear=True), patch.object(CI, "git", self.fake_git):
            with patch.object(CI.subprocess, "Popen") as process, self.assertRaises(CI.BuildError):
                CI.build(self.repo, self.root)
            process.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_invalid_base64_stops_before_key_creation(self):
        invalid = {name: "invalid" for name in CI.REQUIRED}
        invalid["LAB_KEYSTORE_BASE64"] = "not%base64"
        with patch.dict(os.environ, {**self.context, **invalid}, clear=True), patch.object(CI, "git", self.fake_git):
            with patch.object(CI.subprocess, "Popen") as process, self.assertRaises(CI.BuildError):
                CI.build(self.repo, self.root)
            process.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_local_cleanup_entry_is_rejected(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, "argv", [str(HELPER), "--cleanup"]):
            with patch.object(CI.signal, "signal"), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(CI.main(), 2)

    def test_cleanup_requires_matching_workspace(self):
        fake_helper = self.repo / "tools/ipv6-lab/ci-build-apk.py"
        env = {**self.context, "GITHUB_WORKSPACE": str(self.root)}
        with patch.dict(os.environ, env, clear=True), patch.object(CI, "__file__", str(fake_helper)):
            with self.assertRaises(CI.BuildError):
                CI.locations()

    def test_temp_must_not_contain_or_be_inside_checkout(self):
        fake_helper = self.repo / "tools/ipv6-lab/ci-build-apk.py"
        nested = self.repo / "nested"
        nested.mkdir()
        for location in (self.repo, self.base, nested):
            with self.subTest(location=location.name):
                env = {**self.context, "RUNNER_TEMP": str(location)}
                with patch.dict(os.environ, env, clear=True), patch.object(CI, "__file__", str(fake_helper)):
                    with self.assertRaises(CI.BuildError):
                        CI.locations()

    def test_cleanup_does_not_follow_symlinks_or_remove_unrelated_paths(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "sentinel").write_text("preserved")
        (self.root / "ipv6-lab-secret-link").symlink_to(outside, target_is_directory=True)
        (self.root / "unrelated").mkdir()
        (self.repo / ".gradle").mkdir()
        (self.repo / ".gradle/cache").write_text("generated")
        (self.repo / "source.txt").write_text("preserved")
        CI.cleanup(self.repo, self.root, include_public=True)
        self.assertEqual((outside / "sentinel").read_text(), "preserved")
        self.assertTrue((self.root / "unrelated").is_dir())
        self.assertEqual((self.repo / "source.txt").read_text(), "preserved")
        self.assertFalse((self.root / "ipv6-lab-secret-link").is_symlink())
        self.assertFalse((self.repo / ".gradle").exists())

    def test_cleanup_rejects_unsigned_event_before_removing_files(self):
        fake_helper = self.repo / "tools/ipv6-lab/ci-build-apk.py"
        untouched = self.root / "ipv6-lab-secret-unit-fixture"
        untouched.mkdir()
        env = {**self.context, "GITHUB_REF": CI.CI_REF, "GITHUB_WORKFLOW_REF": self.workflow(CI.CI_REF)}
        with patch.dict(os.environ, env, clear=True), patch.object(CI, "__file__", str(fake_helper)):
            with patch.object(sys, "argv", [str(HELPER), "--cleanup"]), patch.object(CI.signal, "signal"):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(CI.main(), 2)
        self.assertTrue(untouched.is_dir())

    def test_cleanup_does_not_follow_a_symlinked_project_parent(self):
        outside = self.base / "outside-project"
        (outside / "build").mkdir(parents=True)
        (outside / "build/sentinel").write_text("preserved")
        (self.repo / "TMessagesProj").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(CI.BuildError):
            CI.cleanup(self.repo, self.root, include_public=True)
        self.assertEqual((outside / "build/sentinel").read_text(), "preserved")


if __name__ == "__main__":
    unittest.main()
