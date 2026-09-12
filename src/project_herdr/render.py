from __future__ import annotations

from collections.abc import Sequence

from project_herdr.model import Dispatch, InboxItem, Workspace, WorkspaceStatus


def render_workspaces(workspaces: Sequence[Workspace]) -> str:
    if not workspaces:
        return "No workspaces registered."
    rows = [
        ("ID", "KIND", "HARNESS", "REMOTE"),
        *(
            (item.id, item.kind, item.default_harness, item.remote)
            for item in workspaces
        ),
    ]
    return _table(rows)


def render_status(rows: Sequence[WorkspaceStatus]) -> str:
    if not rows:
        return "No matching workspaces."
    table = [
        ("ID", "PATH", "GIT", "BRANCH", "DIRTY", "LIVE"),
        *(
            (
                item.id,
                item.path_state if item.path is None else item.path,
                item.git_state,
                item.branch or "-",
                "yes" if item.dirty else "no",
                ",".join(item.live_dispatches) or "-",
            )
            for item in rows
        ),
    ]
    return _table(table)


def render_dispatches(items: Sequence[Dispatch]) -> str:
    if not items:
        return "No dispatches."
    table = [
        ("ID", "WORKSPACE", "STATUS", "HARNESS", "OBJECTIVE"),
        *(
            (item.id, item.workspace, item.status, item.harness, _clip(item.objective))
            for item in items
        ),
    ]
    return _table(table)


def render_inbox(items: Sequence[InboxItem]) -> str:
    if not items:
        return "Inbox empty."
    table = [
        ("KIND", "DISPATCH", "WORKSPACE", "STATUS", "SUMMARY"),
        *(
            (item.kind, item.dispatch_id, item.workspace, item.status, _clip(item.summary))
            for item in items
        ),
    ]
    return _table(table)


def _clip(text: str, width: int = 56) -> str:
    compact = " ".join(text.split())
    if len(compact) <= width:
        return compact
    return compact[: width - 1] + "…"


def _table(rows: Sequence[Sequence[str]]) -> str:
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    rendered: list[str] = []
    for row_index, row in enumerate(rows):
        rendered.append("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)))
        if row_index == 0:
            rendered.append("  ".join("-" * width for width in widths))
    return "\n".join(rendered)
