from __future__ import annotations

import os
import re
import socket
from pathlib import Path

from project_herdr.errors import ConfigError, GitError
from project_herdr.gitstatus import inspect_git, remotes_match
from project_herdr.model import Overlay, Workspace
from project_herdr.store import ControlRoot
from project_herdr.tomlutil import load_toml

DEVICE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def detect_device(explicit: str | None = None) -> str:
    if explicit:
        return _normalize_device(explicit)
    env = os.environ.get("PROJECT_HERDR_DEVICE", "").strip()
    if env:
        return _normalize_device(env)
    return _normalize_device(socket.gethostname())


def load_overlay(root: ControlRoot, device: str | None = None) -> Overlay:
    name = detect_device(device)
    path = root.overlay_file(name)
    if not path.is_file():
        return Overlay(device=name, paths={})
    try:
        payload = load_toml(path)
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read overlay {path}: {exc}") from exc
    raw_paths = payload.get("paths", {})
    if not isinstance(raw_paths, dict):
        raise ConfigError(f"{path} paths must be a table")
    paths = {str(key): str(value) for key, value in raw_paths.items() if str(value).strip()}
    return Overlay(device=str(payload.get("device") or name), paths=paths)


def resolve_workspace_path(
    root: ControlRoot,
    workspace_id: str,
    overlay: Overlay,
    workspace: Workspace | None = None,
) -> Path | None:
    env_key = f"PROJECT_HERDR_PATH_{workspace_id.upper().replace('-', '_')}"
    env_value = os.environ.get(env_key, "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    mapped = overlay.path_for(workspace_id)
    if mapped:
        return Path(mapped).expanduser().resolve()
    if workspace is not None and _root_matches(root.root, workspace.remote):
        return root.root
    return None


def _root_matches(path: Path, expected_remote: str) -> bool:
    git_dir = path / ".git"
    if not git_dir.exists():
        return False
    try:
        observed = str(inspect_git(path, expected_remote).get("observed_remote") or "")
    except GitError:
        return False
    return bool(observed) and remotes_match(expected_remote, observed)


def _normalize_device(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug or not DEVICE_NAME.match(slug):
        raise ConfigError(f"invalid device name {value!r}")
    return slug
