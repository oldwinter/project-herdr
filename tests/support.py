from __future__ import annotations

import os
import subprocess
from pathlib import Path

from project_herdr.store import ControlRoot

REGISTRY = """
version = 1

[[workspaces]]
id = "project-herdr"
name = "Project Herdr"
kind = "control-plane"
remote = "git@github.com:oldwinter/project-herdr.git"
default_harness = "grok"
entry = "just start"
notes = "Coordinator lives here."

[[workspaces]]
id = "novel"
name = "Novel"
kind = "product"
remote = "git@github.com:example/novel.git"
default_harness = "codex"
entry = "just test"
forbid_product_edits_from_coordinator = true
"""


def make_root(tmp: Path) -> ControlRoot:
    root = ControlRoot(tmp)
    root.ensure_layout()
    root.workspaces_file.write_text(REGISTRY.strip() + "\n", encoding="utf-8")
    return root


def init_git(path: Path, remote: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "dev",
        "GIT_AUTHOR_EMAIL": "dev@example.com",
        "GIT_COMMITTER_NAME": "dev",
        "GIT_COMMITTER_EMAIL": "dev@example.com",
    }
    subprocess.run(
        ["git", "init", "-q"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    subprocess.run(
        ["git", "config", "user.email", "dev@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "dev"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    (path / "README.md").write_text("example\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "init"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", remote],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )


def write_overlay(root: ControlRoot, device: str, paths: dict[str, str]) -> None:
    path = root.overlay_file(device)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f'device = "{device}"', "", "[paths]"]
    for key, value in paths.items():
        lines.append(f'"{key}" = "{value}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
