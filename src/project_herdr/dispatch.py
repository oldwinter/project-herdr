from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from project_herdr.errors import ConfigError, NotFoundError
from project_herdr.ids import make_dispatch_id
from project_herdr.model import (
    DISPATCH_STATUSES,
    KNOWN_HARNESSES,
    Authorization,
    Dispatch,
    DispatchStatus,
    Workspace,
)
from project_herdr.store import ControlRoot
from project_herdr.tomlutil import dump_toml, load_toml

WORKER_PROMPT = """# Dispatch {id}

You are a worker, not the coordinator. One dispatch is one workstream: finish
this objective, report, stop. Do not pick up neighbouring work.

Work only in this workspace:

- workspace: {workspace}
- path: {path}
- remote: {remote}

Do not edit the control-plane repository except by recording a receipt from
the control-plane root `{control_root}`, and by writing
under the output directory below.

## Objective

{objective}

## Output

- report: `{output_dir}/report.md` (what changed, how it was verified, open questions)
- other agent-facing files: `{output_dir}/`
- human deliverables (only if the objective asks for one): `{docs_dir}/`
- screenshots / recordings: `{media_dir}/`

Shared context lives in `{context_dir}`. If you learn something durable about this
workspace (how to run its tests, a footgun), write it into the workspace's own
AGENTS.md; cross-workspace lessons go to `{docs_dir}/lessons.md`.

## Authorization

- push: {push}
- merge: {merge}
- send: {send}
- delete: {delete}

Refuse any unauthorized external action.

## Acceptance

{acceptance}

## Progress

While working, report a short step. This does not finish the dispatch:

```
PYTHONPATH=src python3 -m project_herdr --root . session update --dispatch {id} --step "..."
```

The coordinator can `session show {id}` at any time, or `session pull {id}` to
read only new Herdr pane output since the last pull.

## Writeback

When finished, run this from the control-plane root `{control_root}`:

```
PYTHONPATH=src python3 -m project_herdr --root . receipt record --dispatch {id} --verdict passed|failed|needs_review|blocked --summary "..." --evidence {output_dir}/report.md
```

If you opened a pull request (only with push authorization), attach it:

```
PYTHONPATH=src python3 -m project_herdr --root . dispatch attach {id} --pr <url>
```

The equivalent installed command is `project-herdr dispatch attach {id} --pr <url>`.

Then stop. Do not push, merge, publish, or send unless authorization above is true.
"""


def list_dispatches(root: ControlRoot, workspace_id: str | None = None) -> tuple[Dispatch, ...]:
    if not root.dispatches_dir.is_dir():
        return ()
    items: list[Dispatch] = []
    for path in sorted(root.dispatches_dir.glob("*.toml")):
        item = load_dispatch(path)
        if workspace_id is None or item.workspace == workspace_id:
            items.append(item)
    return tuple(items)


def get_dispatch(root: ControlRoot, dispatch_id: str) -> Dispatch:
    path = root.dispatch_file(dispatch_id)
    if not path.is_file():
        raise NotFoundError(f"unknown dispatch {dispatch_id!r}")
    return load_dispatch(path)


def load_dispatch(path: Path) -> Dispatch:
    try:
        payload = load_toml(path)
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read dispatch {path}: {exc}") from exc
    status = str(payload.get("status") or "drafted")
    if status not in DISPATCH_STATUSES:
        raise ConfigError(f"{path} has invalid status {status!r}")
    harness = str(payload.get("harness") or "grok")
    if harness not in KNOWN_HARNESSES:
        raise ConfigError(f"{path} has unknown harness {harness!r}")
    auth_raw = payload.get("authorization") or {}
    if not isinstance(auth_raw, dict):
        raise ConfigError(f"{path} authorization must be a table")
    acceptance = payload.get("acceptance") or {}
    commands = tuple(str(item) for item in acceptance.get("commands", [])) if isinstance(acceptance, dict) else ()
    writeback = payload.get("writeback") or {}
    receipt_dir = (
        str(writeback.get("receipt_dir") or "control/receipts")
        if isinstance(writeback, dict)
        else "control/receipts"
    )
    return Dispatch(
        id=str(payload["id"]),
        workspace=str(payload["workspace"]),
        objective=str(payload.get("objective") or ""),
        created_at=str(payload.get("created_at") or ""),
        status=cast(DispatchStatus, status),
        harness=harness,
        authorization=Authorization(
            push=bool(auth_raw.get("push", False)),
            merge=bool(auth_raw.get("merge", False)),
            send=bool(auth_raw.get("send", False)),
            delete=bool(auth_raw.get("delete", False)),
        ),
        acceptance_commands=commands,
        writeback_receipt_dir=receipt_dir,
        prompt_path=str(payload.get("prompt_path") or ""),
        herdr_requested=bool(payload.get("herdr_requested", False)),
        herdr_result=str(payload.get("herdr_result") or ""),
        pr_url=str(payload.get("pr_url") or ""),
    )


def create_dispatch(
    root: ControlRoot,
    workspace: Workspace,
    objective: str,
    *,
    harness: str | None = None,
    authorization: Authorization | None = None,
    acceptance_commands: tuple[str, ...] = (),
    now: datetime | None = None,
) -> Dispatch:
    text = objective.strip()
    if not text:
        raise ConfigError("dispatch objective is required")
    chosen = harness or workspace.default_harness
    if chosen not in KNOWN_HARNESSES:
        raise ConfigError(f"unknown harness {chosen!r}")
    root.ensure_layout()
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    existing = {path.stem for path in root.dispatches_dir.glob("*.toml")}
    dispatch_id = make_dispatch_id(stamp, text, existing)
    prompt_path = root.prompt_file(dispatch_id)
    item = Dispatch(
        id=dispatch_id,
        workspace=workspace.id,
        objective=text,
        created_at=stamp,
        status="drafted",
        harness=chosen,
        authorization=authorization or Authorization(),
        acceptance_commands=acceptance_commands,
        prompt_path=_relpath(root.root, prompt_path),
    )
    write_worker_prompt(root, item, workspace, workspace_path="(unresolved)")
    save_dispatch(root, item)
    return item


def save_dispatch(root: ControlRoot, item: Dispatch) -> None:
    root.ensure_layout()
    payload: dict[str, Any] = {
        "id": item.id,
        "workspace": item.workspace,
        "objective": item.objective,
        "created_at": item.created_at,
        "status": item.status,
        "harness": item.harness,
        "prompt_path": item.prompt_path,
        "herdr_requested": item.herdr_requested,
        "herdr_result": item.herdr_result,
        "pr_url": item.pr_url,
        "authorization": item.authorization.as_dict(),
        "acceptance": {"commands": list(item.acceptance_commands)},
        "writeback": {"receipt_dir": item.writeback_receipt_dir},
    }
    root.dispatch_file(item.id).write_text(dump_toml(payload), encoding="utf-8")


def mark_dispatch(
    root: ControlRoot,
    item: Dispatch,
    *,
    status: DispatchStatus | None = None,
    herdr_requested: bool | None = None,
    herdr_result: str | None = None,
    prompt_path: str | None = None,
    pr_url: str | None = None,
) -> Dispatch:
    updated = replace(
        item,
        status=status or item.status,
        herdr_requested=item.herdr_requested if herdr_requested is None else herdr_requested,
        herdr_result=item.herdr_result if herdr_result is None else herdr_result,
        prompt_path=item.prompt_path if prompt_path is None else prompt_path,
        pr_url=item.pr_url if pr_url is None else pr_url,
    )
    save_dispatch(root, updated)
    return updated


def write_worker_prompt(
    root: ControlRoot,
    item: Dispatch,
    workspace: Workspace,
    workspace_path: str,
) -> Path:
    path = root.prompt_file(item.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    acceptance = "\n".join(f"- `{command}`" for command in item.acceptance_commands)
    if not acceptance:
        acceptance = "- (none declared; report evidence of the objective)"
    body = WORKER_PROMPT.format(
        id=item.id,
        workspace=workspace.id,
        path=workspace_path,
        remote=workspace.remote,
        objective=item.objective,
        push=_bool(item.authorization.push),
        merge=_bool(item.authorization.merge),
        send=_bool(item.authorization.send),
        delete=_bool(item.authorization.delete),
        acceptance=acceptance,
        context_dir=_relpath(root.root, root.context_dir),
        docs_dir=_relpath(root.root, root.context_docs_dir),
        media_dir=_relpath(root.root, root.context_media_dir),
        output_dir=_relpath(root.root, root.worker_output_dir(item.id)),
        control_root=str(root.root),
    )
    path.write_text(body, encoding="utf-8")
    return path


def live_dispatch_ids(root: ControlRoot, workspace_id: str) -> tuple[str, ...]:
    live = []
    for item in list_dispatches(root, workspace_id):
        if item.status not in {"done"}:
            live.append(item.id)
    return tuple(live)


def _relpath(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _bool(value: bool) -> str:
    return "true" if value else "false"
