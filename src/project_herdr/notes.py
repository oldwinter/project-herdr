"""Render the coordinator's human-readable status file.

Mirrors the ``notes.md`` a Cursor Project coordinator keeps: short checkbox
items grouped by workstream, a capped list of the newest completed items, and
an append-only ``archived.md`` that older completed items decay into. The file
is derived from dispatches and receipts on every write, so it is a readout, not
a changelog.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from project_herdr.dispatch import list_dispatches
from project_herdr.model import Dispatch, Receipt
from project_herdr.receipts import latest_receipt
from project_herdr.store import ControlRoot

COMPLETED_CAP = 3
ARCHIVED_HEADER = "# Archived\n\nCompleted dispatches that fell out of `notes.md`.\n"
_ITEM_ID = re.compile(r"\[(d-[0-9]{8}-[a-z0-9-]+)\]\(")

STATUS_TEXT = {
    "drafted": "drafted, not yet ready for a worker",
    "ready": "ready, waiting for a worker",
    "dispatched": "worker running",
    "needs_review": "needs your review",
    "blocked": "blocked",
    "done": "done",
}


@dataclass(frozen=True)
class NotesResult:
    notes: str
    archived_added: tuple[str, ...]


def render_notes(root: ControlRoot) -> NotesResult:
    dispatches = list_dispatches(root)
    live = [item for item in dispatches if item.status != "done"]
    done = sorted(
        (item for item in dispatches if item.status == "done"),
        key=lambda item: _finished_at(root, item),
        reverse=True,
    )
    keep, overflow = done[:COMPLETED_CAP], done[COMPLETED_CAP:]

    lines = ["# Notes", ""]
    if not dispatches:
        lines.append("- [ ] no dispatches yet; create one with `project-herdr dispatch create`")
    groups: dict[str, list[Dispatch]] = {}
    for item in live:
        groups.setdefault(item.workspace, []).append(item)
    multi = len(groups) > 1
    for workspace in sorted(groups):
        if multi:
            lines.extend([f"## {workspace}", ""])
        for item in groups[workspace]:
            lines.append(_item(root, item, checked=False, show_workspace=not multi))
        if multi:
            lines.append("")
    if keep:
        if multi or not groups:
            lines.extend(["## Done", ""])
        for item in keep:
            lines.append(_item(root, item, checked=True, show_workspace=True))
    lines.append("")
    lines.append(f"[archived]({root.archived_file.name})")
    notes = "\n".join(lines).rstrip("\n") + "\n"
    archived_added = tuple(
        _item(root, item, checked=True, show_workspace=True) for item in overflow
    )
    return NotesResult(notes=notes, archived_added=archived_added)


def write_notes(root: ControlRoot) -> NotesResult:
    root.ensure_layout()
    result = render_notes(root)
    _append_archived(root, result.archived_added)
    _atomic_write(root.notes_file, result.notes)
    return result


def _item(root: ControlRoot, item: Dispatch, *, checked: bool, show_workspace: bool) -> str:
    receipt = latest_receipt(root, item.id)
    box = "[x]" if checked else "[ ]"
    label = f"[{item.id}]({_rel(root, root.dispatch_file(item.id))})"
    parts = [f"- {box} {label}"]
    if show_workspace:
        parts.append(f"`{item.workspace}`")
    parts.append(_readout(item, receipt))
    if item.pr_url:
        parts.append(f"[PR]({item.pr_url})")
    return " ".join(parts)


def _readout(item: Dispatch, receipt: Receipt | None) -> str:
    objective = " ".join(item.objective.split())
    if len(objective) > 72:
        objective = objective[:71] + "…"
    if receipt is not None and receipt.summary:
        summary = " ".join(receipt.summary.split())
        return f"{objective} — {summary}"
    return f"{objective} — {STATUS_TEXT.get(item.status, item.status)}"


def _finished_at(root: ControlRoot, item: Dispatch) -> str:
    receipt = latest_receipt(root, item.id)
    return receipt.recorded_at if receipt is not None else item.created_at


def _append_archived(root: ControlRoot, rows: tuple[str, ...]) -> None:
    if not rows:
        return
    existing = root.archived_file.read_text(encoding="utf-8") if root.archived_file.exists() else ""
    seen = set(_ITEM_ID.findall(existing))
    fresh: list[str] = []
    for row in rows:
        match = _ITEM_ID.search(row)
        if match is not None and match.group(1) not in seen:
            fresh.append(row)
            seen.add(match.group(1))
    if not fresh:
        return
    body = existing if existing else ARCHIVED_HEADER
    if not body.endswith("\n"):
        body += "\n"
    if body == ARCHIVED_HEADER:
        body += "\n"
    body += "\n".join(fresh) + "\n"
    _atomic_write(root.archived_file, body)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _rel(root: ControlRoot, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.control.resolve()).as_posix()
    except ValueError:
        return str(path)
