from __future__ import annotations

from project_herdr.dispatch import live_dispatch_ids
from project_herdr.gitstatus import inspect_git
from project_herdr.model import Overlay, Registry, WorkspaceStatus
from project_herdr.overlay import resolve_workspace_path
from project_herdr.store import ControlRoot


def collect_status(
    root: ControlRoot,
    registry: Registry,
    overlay: Overlay,
    workspace_id: str | None = None,
) -> tuple[WorkspaceStatus, ...]:
    selected = registry.workspaces
    if workspace_id:
        match = registry.get(workspace_id)
        selected = (match,) if match else ()
    rows: list[WorkspaceStatus] = []
    for workspace in selected:
        path = resolve_workspace_path(root, workspace.id, overlay, workspace)
        if path is None:
            path_state = "unresolved"
        elif not path.exists():
            path_state = "missing"
        else:
            path_state = "resolved"
        git = inspect_git(path if path_state == "resolved" else None, workspace.remote)
        if path_state != "resolved":
            git_state = "skipped" if path_state == "unresolved" else "missing"
        else:
            git_state = str(git["git_state"])
        rows.append(
            WorkspaceStatus(
                id=workspace.id,
                name=workspace.name,
                kind=workspace.kind,
                remote=workspace.remote,
                path=None if path is None else str(path),
                path_state=path_state,  # type: ignore[arg-type]
                git_state=git_state,  # type: ignore[arg-type]
                branch=str(git["branch"]),
                head=str(git["head"]),
                dirty=bool(git["dirty"]),
                observed_remote=str(git["observed_remote"]),
                live_dispatches=live_dispatch_ids(root, workspace.id),
            )
        )
    return tuple(rows)
