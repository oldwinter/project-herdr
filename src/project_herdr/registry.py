from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from project_herdr.errors import ConfigError, NotFoundError
from project_herdr.ids import require_workspace_id
from project_herdr.model import (
    KNOWN_HARNESSES,
    WORKSPACE_KINDS,
    Registry,
    Workspace,
    WorkspaceKind,
)
from project_herdr.store import ControlRoot
from project_herdr.tomlutil import load_toml


def load_registry(root: ControlRoot) -> Registry:
    if not root.workspaces_file.is_file():
        raise ConfigError(f"missing workspace registry: {root.workspaces_file}")
    tracked = _parse_registry_file(root.workspaces_file)
    if root.workspaces_local_file.is_file():
        local = _parse_registry_file(root.workspaces_local_file)
        return _merge(tracked, local)
    return tracked


def require_workspace(root: ControlRoot, workspace_id: str) -> Workspace:
    registry = load_registry(root)
    workspace = registry.get(workspace_id)
    if workspace is None:
        known = ", ".join(registry.ids()) or "(none)"
        raise NotFoundError(f"unknown workspace {workspace_id!r}; known: {known}")
    return workspace


def _parse_registry_file(path: Path) -> Registry:
    try:
        payload = load_toml(path)
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    version = payload.get("version", 1)
    if version != 1:
        raise ConfigError(f"{path} has unsupported version {version!r}; expected 1")
    rows = payload.get("workspaces")
    if rows is None:
        raise ConfigError(f"{path} is missing [[workspaces]]")
    if not isinstance(rows, list) or not rows:
        raise ConfigError(f"{path} must declare at least one workspace")
    workspaces: list[Workspace] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ConfigError(f"{path} workspace #{index} must be a table")
        workspace = _parse_workspace(path, row)
        if workspace.id in seen:
            raise ConfigError(f"{path} repeats workspace id {workspace.id!r}")
        seen.add(workspace.id)
        workspaces.append(workspace)
    return Registry(version=1, workspaces=tuple(workspaces))


def _parse_workspace(path: Path, row: dict[str, Any]) -> Workspace:
    try:
        workspace_id = require_workspace_id(str(row["id"]))
    except (KeyError, ValueError) as exc:
        raise ConfigError(f"{path} workspace is missing a valid id: {exc}") from exc
    name = str(row.get("name") or workspace_id)
    kind = str(row.get("kind") or "")
    if kind not in WORKSPACE_KINDS:
        raise ConfigError(
            f"{path} workspace {workspace_id} has invalid kind {kind!r}; "
            f"use {', '.join(sorted(WORKSPACE_KINDS))}"
        )
    remote = str(row.get("remote") or "").strip()
    if not remote:
        raise ConfigError(f"{path} workspace {workspace_id} is missing remote")
    harness = str(row.get("default_harness") or "grok")
    if harness not in KNOWN_HARNESSES:
        raise ConfigError(
            f"{path} workspace {workspace_id} has unknown default_harness {harness!r}"
        )
    return Workspace(
        id=workspace_id,
        name=name,
        kind=cast(WorkspaceKind, kind),
        remote=remote,
        default_harness=harness,
        entry=str(row.get("entry") or ""),
        forbid_product_edits_from_coordinator=bool(
            row.get("forbid_product_edits_from_coordinator", True)
        ),
        notes=str(row.get("notes") or ""),
    )


def _merge(tracked: Registry, local: Registry) -> Registry:
    by_id = {workspace.id: workspace for workspace in tracked.workspaces}
    for workspace in local.workspaces:
        by_id[workspace.id] = workspace
    return Registry(version=1, workspaces=tuple(by_id.values()))
