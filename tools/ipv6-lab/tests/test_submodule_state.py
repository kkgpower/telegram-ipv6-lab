import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "submodule_state.py"
SPEC = importlib.util.spec_from_file_location("submodule_state", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
SHA = "1" * 40


class SubmoduleReadiness(unittest.TestCase):
    def test_upstream_disabled_suite_does_not_block_required_modules(self):
        text = " " + SHA + " required (head)\n-" + SHA + " quickjs/test262\n"
        with patch.object(MODULE, "declared_update_none", return_value=True):
            result = MODULE.inspect_submodules(Path("/tmp"), text)
        self.assertEqual(result["pinned"], ["required"])
        self.assertEqual(result["intentionally_skipped"], ["quickjs/test262"])
        self.assertFalse(result["blocking"])

    def test_missing_required_module_blocks(self):
        with patch.object(MODULE, "declared_update_none", return_value=False):
            result = MODULE.inspect_submodules(Path("/tmp"), "-" + SHA + " required\n")
        self.assertEqual(result["blocking"], ["required"])

    def test_wrong_commit_is_not_excused_by_update_none(self):
        with patch.object(MODULE, "declared_update_none", return_value=True):
            result = MODULE.inspect_submodules(Path("/tmp"), "+" + SHA + " required\n")
        self.assertEqual(result["blocking"], ["required"])

    def test_unknown_output_is_not_silently_accepted(self):
        with self.assertRaises(RuntimeError):
            MODULE.inspect_submodules(Path("/tmp"), "unexpected diagnostic\n")

    def test_policy_is_read_from_committed_gitmodules(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            source = repo / ".gitmodules"
            source.write_text('[submodule "test262"]\n path = test262\n update = none\n')
            subprocess.run(["git", "-C", str(repo), "add", ".gitmodules"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Infrastructure test",
                            "-c", "user.email=test@example.invalid", "-c", "commit.gpgSign=false",
                            "commit", "-qm", "Committed module policy"], check=True)
            source.write_text('[submodule "test262"]\n path = other\n update = checkout\n')
            self.assertTrue(MODULE.declared_update_none(repo, "test262"))
            self.assertFalse(MODULE.declared_update_none(repo, "other"))


if __name__ == "__main__":
    unittest.main()
