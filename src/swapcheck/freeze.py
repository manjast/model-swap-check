"""Freeze guard (spec §9.5): `cert`/`aa` runs start only on the code and inputs frozen under the contract tag."""

from __future__ import annotations

import subprocess
from pathlib import Path

CONTRACT_TAG = "contract-v1"
FROZEN_PATHS = ("src", "prompts", "config", "contracts", "analysis")
GUARDED_SPLITS = frozenset({"cert", "aa"})


class FreezeError(RuntimeError):
    """A guarded run may not start or continue."""


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise FreezeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def head_commit(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").strip()


def tag_commit(repo: Path, tag: str = CONTRACT_TAG) -> str | None:
    """The commit a tag points to (annotated or lightweight), or None when the tag does not exist."""
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def check_freeze(repo: Path, tag: str = CONTRACT_TAG) -> str:
    """Return the tag's commit if every frozen path is byte-identical to it, else raise `FreezeError`.

    Compares the working tree (tracked changes, staged or not, and deletions) and lists untracked,
    non-ignored files under the frozen paths. Anything outside them, such as `runs/`, may change.
    """
    commit = tag_commit(repo, tag)
    if commit is None:
        raise FreezeError(f"tag {tag} does not exist; freeze the contract before any cert or aa run")
    changed = _git(repo, "diff", "--name-only", "-z", "--no-renames", commit, "--", *FROZEN_PATHS).split("\0")
    untracked = _git(repo, "ls-files", "-z", "--others", "--exclude-standard", "--", *FROZEN_PATHS).split("\0")
    problems = sorted((set(changed) | set(untracked)) - {""})
    if problems:
        listed = ", ".join(problems[:10]) + (" …" if len(problems) > 10 else "")
        raise FreezeError(f"{len(problems)} file(s) differ from {tag} ({commit[:12]}): {listed}")
    return commit
