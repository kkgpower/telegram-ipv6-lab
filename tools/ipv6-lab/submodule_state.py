"""Check pinned submodules while honoring committed upstream update=none policy."""

from pathlib import Path
import re
import subprocess


def declared_update_none(repo, path):
    """Consult the owning repository's committed .gitmodules, not local config."""
    repo = Path(repo).resolve()
    candidate = repo / path
    if repo not in candidate.resolve().parents:
        return False
    for owner in candidate.parents:
        if owner != repo and repo not in owner.parents:
            break
        if not (owner / ".gitmodules").is_file():
            continue
        root = subprocess.run(["git", "-C", str(owner), "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, timeout=30)
        if root.returncode or Path(root.stdout.strip()).resolve() != owner.resolve():
            continue
        result = subprocess.run([
            "git", "-C", str(owner), "config", "--blob", "HEAD:.gitmodules", "--null",
            "--get-regexp", r"^submodule\..*\.(path|update)$",
        ], capture_output=True, text=True, timeout=30)
        if result.returncode:
            continue
        settings = {}
        for entry in result.stdout.split("\0"):
            key, separator, value = entry.partition("\n")
            if separator:
                name, option = key.rsplit(".", 1)
                settings.setdefault(name, {})[option] = value
        relative = candidate.relative_to(owner).as_posix()
        for options in settings.values():
            if options.get("path") == relative:
                return options.get("update") == "none"
    return False


def inspect_submodules(repo, output=None):
    repo = Path(repo)
    if output is None:
        result = subprocess.run(["git", "-C", str(repo), "submodule", "status", "--recursive"],
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError("Cannot read pinned submodule state")
        output = result.stdout
    blocking, skipped, pinned = [], [], []
    for line in output.splitlines():
        if not line:
            continue
        match = re.fullmatch(r"([ +U-])([0-9a-f]{40}) (.*?)(?: \([^\n]*\))?", line)
        if not match:
            raise RuntimeError("Unexpected submodule status output")
        state, _sha, path = match.groups()
        if state == " ":
            pinned.append(path)
        elif state == "-" and declared_update_none(repo, path):
            skipped.append(path)
        else:
            blocking.append(path)
    return {"output": output.rstrip() + "\n", "pinned": pinned,
            "blocking": blocking, "intentionally_skipped": skipped}
