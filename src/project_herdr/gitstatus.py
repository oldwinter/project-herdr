from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Literal

from project_herdr.errors import GitError

GitState = Literal["ok", "missing", "not_git", "remote_mismatch", "skipped"]


def inspect_git(path: Path | None, expected_remote: str) -> dict[str, str | bool]:
    if path is None:
        return {
            "git_state": "skipped",
            "branch": "",
            "head": "",
            "dirty": False,
            "observed_remote": "",
        }
    if not path.exists():
        return {
            "git_state": "missing",
            "branch": "",
            "head": "",
            "dirty": False,
            "observed_remote": "",
        }
    if not _is_git_worktree(path):
        return {
            "git_state": "not_git",
            "branch": "",
            "head": "",
            "dirty": False,
            "observed_remote": "",
        }
    branch = _git(path, ["rev-parse", "--abbrev-ref", "HEAD"])
    head = _git(path, ["rev-parse", "--short", "HEAD"])
    porcelain = _git(path, ["status", "--porcelain"])
    observed = ""
    try:
        observed = _git(path, ["remote", "get-url", "origin"])
    except GitError:
        observed = ""
    git_state: GitState = "ok"
    if observed and expected_remote and not remotes_match(expected_remote, observed):
        git_state = "remote_mismatch"
    return {
        "git_state": git_state,
        "branch": branch,
        "head": head,
        "dirty": bool(porcelain.strip()),
        "observed_remote": observed,
    }


def remotes_match(left: str, right: str) -> bool:
    return _canonical_remote(left) == _canonical_remote(right)


def _canonical_remote(url: str) -> str:
    text = url.strip().rstrip("/")
    if text.endswith(".git"):
        text = text[:-4]
    text = text.replace("ssh://git@", "git@")
    match = re.match(r"^git@([^:]+):(.+)$", text)
    if match:
        return f"{match.group(1).lower()}/{match.group(2).lower()}"
    match = re.match(r"^https?://([^/]+)/(.+)$", text)
    if match:
        return f"{match.group(1).lower()}/{match.group(2).lower()}"
    return text.lower()


def _is_git_worktree(path: Path) -> bool:
    try:
        value = _git(path, ["rev-parse", "--is-inside-work-tree"])
    except GitError:
        return False
    return value == "true"


def _git(path: Path, args: list[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(path), *args],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise GitError(f"git is unavailable: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip() or f"exit {completed.returncode}"
        raise GitError(detail)
    return completed.stdout.strip()
