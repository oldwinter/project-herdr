"""Incremental worker-session readout.

Cursor Projects show a worker's current step while it is still running.
Here that is an append-only JSONL log plus an optional Herdr pane pull
that records only text that appeared since the last cursor. Neither
command writes a receipt or changes dispatch status.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from project_herdr.dispatch import get_dispatch, list_dispatches
from project_herdr.errors import AdapterError, ConfigError
from project_herdr.herdr import HerdrAdapter, agent_name_for, default_adapter
from project_herdr.model import Dispatch
from project_herdr.store import ControlRoot

STEP_MAX = 200
READOUT_MAX = 8000
_AGENT = re.compile(r"(?:^|\s)agent=([a-z][a-z0-9_-]{0,31})(?:\s|$)")

SessionKind = Literal["step", "readout"]
PullAction = Literal["appended", "unchanged", "probe_failed"]


@dataclass(frozen=True)
class SessionEntry:
    at: str
    kind: SessionKind
    step: str = ""
    text: str = ""
    reset: bool = False
    source: str = ""

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"at": self.at, "kind": self.kind}
        if self.step:
            payload["step"] = self.step
        if self.text:
            payload["text"] = self.text
        if self.reset:
            payload["reset"] = True
        if self.source:
            payload["source"] = self.source
        return payload


@dataclass(frozen=True)
class SessionView:
    dispatch_id: str
    status: str
    latest_step: str
    entries: tuple[SessionEntry, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "dispatch_id": self.dispatch_id,
            "status": self.status,
            "latest_step": self.latest_step,
            "entries": [item.as_dict() for item in self.entries],
        }


@dataclass(frozen=True)
class PullResult:
    dispatch_id: str
    agent: str
    action: PullAction
    increment: str = ""
    reset: bool = False
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "dispatch_id": self.dispatch_id,
            "agent": self.agent,
            "action": self.action,
            "increment": self.increment,
            "reset": self.reset,
            "detail": self.detail,
        }


def update_session(
    root: ControlRoot,
    dispatch_id: str,
    step: str,
    *,
    now: datetime | None = None,
) -> SessionEntry:
    item = get_dispatch(root, dispatch_id)
    body = " ".join(step.split())
    if not body:
        raise ConfigError("session step is required")
    if len(body) > STEP_MAX:
        body = body[: STEP_MAX - 1] + "…"
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    entry = SessionEntry(at=stamp, kind="step", step=body, source="worker")
    _append(root, item.id, entry)
    return entry


def show_session(root: ControlRoot, dispatch_id: str | None = None) -> tuple[SessionView, ...]:
    if dispatch_id:
        item = get_dispatch(root, dispatch_id)
        return (_view(root, item),)
    views = [_view(root, item) for item in list_dispatches(root) if item.status != "done"]
    return tuple(views)


def latest_step(root: ControlRoot, dispatch_id: str) -> str:
    for entry in reversed(load_session(root, dispatch_id)):
        if entry.kind == "step" and entry.step:
            return entry.step
    return ""


def load_session(root: ControlRoot, dispatch_id: str) -> tuple[SessionEntry, ...]:
    path = root.session_log_file(dispatch_id)
    if not path.is_file():
        return ()
    entries: list[SessionEntry] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"cannot read session {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ConfigError(f"{path} has a non-object session line")
        kind = str(payload.get("kind") or "")
        if kind not in {"step", "readout"}:
            raise ConfigError(f"{path} has invalid session kind {kind!r}")
        entries.append(
            SessionEntry(
                at=str(payload.get("at") or ""),
                kind=kind,  # type: ignore[arg-type]
                step=str(payload.get("step") or ""),
                text=str(payload.get("text") or ""),
                reset=bool(payload.get("reset", False)),
                source=str(payload.get("source") or ""),
            )
        )
    return tuple(entries)


def pull_session(
    root: ControlRoot,
    dispatch_id: str,
    *,
    adapter: HerdrAdapter | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
    lines: int = 120,
) -> PullResult:
    item = get_dispatch(root, dispatch_id)
    agent = resolve_herdr_agent(item)
    result = (adapter or default_adapter()).read_agent(agent, lines=lines)
    if not result.ok:
        if result.reason in {"not_in_herdr_pane", "herdr_missing"}:
            raise AdapterError(f"{result.reason}: {result.detail}")
        return PullResult(
            dispatch_id=item.id,
            agent=agent,
            action="probe_failed",
            detail=f"{result.reason}: {result.detail}".strip(),
        )
    previous = _cursor(root, item.id)
    increment, reset = incremental_text(previous, result.text)
    if not increment:
        return PullResult(dispatch_id=item.id, agent=agent, action="unchanged")
    stored = increment if len(increment) <= READOUT_MAX else increment[: READOUT_MAX - 1] + "…"
    if not dry_run:
        stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
        _append(
            root,
            item.id,
            SessionEntry(
                at=stamp,
                kind="readout",
                text=stored,
                reset=reset,
                source="herdr",
            ),
        )
        _write_cursor(root, item.id, result.text)
    return PullResult(
        dispatch_id=item.id,
        agent=agent,
        action="appended",
        increment=stored,
        reset=reset,
    )


def resolve_herdr_agent(item: Dispatch) -> str:
    match = _AGENT.search(item.herdr_result)
    if match:
        return match.group(1)
    if item.herdr_requested and item.herdr_result == "dispatched":
        return agent_name_for(item.id)
    raise AdapterError(
        f"{item.id} has no Herdr session to pull; enqueue from a Herdr pane or use session update"
    )


def incremental_text(previous: str, current: str) -> tuple[str, bool]:
    if not current:
        return "", False
    if not previous:
        return current, False
    if current == previous:
        return "", False
    if current.startswith(previous):
        return current[len(previous) :], False
    overlap = _suffix_prefix_overlap(previous, current)
    if overlap:
        return current[overlap:], False
    return current, True


def render_session(views: tuple[SessionView, ...]) -> str:
    if not views:
        return "No live dispatches."
    if len(views) == 1:
        view = views[0]
        if not view.entries:
            return f"{view.dispatch_id}  {view.status}  (no session yet)"
        lines = [f"{entry.at}  {entry.kind:<7}  {_preview(entry)}" for entry in view.entries]
        return "\n".join(lines)
    rows = []
    for view in views:
        rows.append(
            f"{view.dispatch_id}  {view.status}  {view.latest_step or '(no session yet)'}"
        )
    return "\n".join(rows)


def _view(root: ControlRoot, item: Dispatch) -> SessionView:
    entries = load_session(root, item.id)
    return SessionView(
        dispatch_id=item.id,
        status=item.status,
        latest_step=latest_step(root, item.id),
        entries=entries,
    )


def _append(root: ControlRoot, dispatch_id: str, entry: SessionEntry) -> None:
    path = root.session_log_file(dispatch_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry.as_dict(), ensure_ascii=False) + "\n")


def _cursor(root: ControlRoot, dispatch_id: str) -> str:
    path = root.session_cursor_file(dispatch_id)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _write_cursor(root: ControlRoot, dispatch_id: str, snapshot: str) -> None:
    path = root.session_cursor_file(dispatch_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(snapshot, encoding="utf-8")


def _suffix_prefix_overlap(previous: str, current: str) -> int:
    limit = min(len(previous), len(current))
    for size in range(limit, 0, -1):
        if previous.endswith(current[:size]):
            return size
    return 0


def _preview(entry: SessionEntry) -> str:
    if entry.kind == "step":
        return entry.step
    text = " ".join(entry.text.split())
    if entry.reset:
        text = f"[reset] {text}"
    return text if len(text) <= 80 else text[:79] + "…"
