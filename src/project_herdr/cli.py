from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from project_herdr import __version__
from project_herdr.dispatch import (
    create_dispatch,
    get_dispatch,
    list_dispatches,
    mark_dispatch,
    write_worker_prompt,
)
from project_herdr.errors import AdapterError, ProjectHerdrError
from project_herdr.herdr import HerdrAdapter, default_adapter
from project_herdr.inbox import build_inbox
from project_herdr.lessons import add_lesson, lessons_file
from project_herdr.model import KNOWN_HARNESSES, Authorization, EnqueueRequest
from project_herdr.notes import write_notes
from project_herdr.overlay import load_overlay, resolve_workspace_path
from project_herdr.receipts import record_receipt
from project_herdr.registry import load_registry, require_workspace
from project_herdr.render import render_dispatches, render_inbox, render_status, render_workspaces
from project_herdr.status import collect_status
from project_herdr.store import ControlRoot
from project_herdr.sync import sync_dispatches


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--root",
        default=argparse.SUPPRESS,
        help="Control-plane root. Defaults to the current directory.",
    )
    common.add_argument(
        "--device",
        default=argparse.SUPPRESS,
        help="Overlay device name. Defaults to PROJECT_HERDR_DEVICE or hostname.",
    )
    common.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Machine-readable output.",
    )
    parser = argparse.ArgumentParser(
        prog="project-herdr",
        description=(
            "Coordinator control plane for multi-repo agent work. "
            "This process plans and records; workers edit product workspaces."
        ),
        parents=[common],
    )
    parser.add_argument("--version", action="version", version=f"project-herdr {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("start", help="Print the coordinator entry path.", parents=[common])
    sub.add_parser("doctor", help="Check registry, git, and optional Herdr.", parents=[common])
    sub.add_parser("workspaces", help="List registered workspaces.", parents=[common])
    show = sub.add_parser("workspace", help="Show one workspace.", parents=[common])
    show.add_argument("id")

    status = sub.add_parser("status", help="Read-only workspace and dispatch status.", parents=[common])
    status.add_argument("--workspace")

    dispatch = sub.add_parser("dispatch", help="Create or inspect dispatch contracts.", parents=[common])
    dispatch_sub = dispatch.add_subparsers(dest="dispatch_command", required=True)
    create = dispatch_sub.add_parser(
        "create",
        help="Write a dispatch contract. Does not edit the target repo.",
        parents=[common],
    )
    create.add_argument("--workspace", required=True)
    create.add_argument("--objective", required=True)
    create.add_argument(
        "--harness",
        choices=sorted(KNOWN_HARNESSES),
        help="Worker herdr --kind. Defaults to the workspace default_harness.",
    )
    create.add_argument("--accept", action="append", default=[], help="Acceptance command; repeatable.")
    create.add_argument("--allow-push", action="store_true")
    create.add_argument("--allow-merge", action="store_true")
    create.add_argument("--allow-send", action="store_true")
    create.add_argument("--allow-delete", action="store_true")
    create.add_argument("--ready", action="store_true", help="Mark the contract ready for a worker.")
    create.add_argument(
        "--enqueue",
        action="store_true",
        help="Ask Herdr to open a worker pane in the target workspace. Coordinator does not wait.",
    )
    dispatch_sub.add_parser("list", help="List dispatch contracts.", parents=[common])
    show_dispatch = dispatch_sub.add_parser(
        "show", help="Show one dispatch contract.", parents=[common]
    )
    show_dispatch.add_argument("id")
    attach = dispatch_sub.add_parser(
        "attach",
        help="Attach external evidence (a pull request URL) to a dispatch.",
        parents=[common],
    )
    attach.add_argument("id")
    attach.add_argument("--pr", required=True, help="Pull request URL opened by the worker.")

    sub.add_parser("inbox", help="List work waiting for human review.", parents=[common])
    sub.add_parser(
        "notes",
        help="Rewrite control/notes.md from dispatches and receipts, then print it.",
        parents=[common],
    )
    sub.add_parser(
        "context",
        help="Show the shared-context layout (docs/, internal/, media/).",
        parents=[common],
    )
    sync = sub.add_parser(
        "sync",
        help="Pull PR state (via gh) into dispatches that have a pr_url. Optional; fails closed without gh.",
        parents=[common],
    )
    sync.add_argument("--dry-run", action="store_true", help="Report what would change, write nothing.")

    lesson = sub.add_parser("lesson", help="Shared-context lessons.", parents=[common])
    lesson_sub = lesson.add_subparsers(dest="lesson_command", required=True)
    lesson_add = lesson_sub.add_parser(
        "add", help="Append a cross-workspace lesson to context/docs/lessons.md.", parents=[common]
    )
    lesson_add.add_argument("text")
    lesson_add.add_argument("--workspace", default="", help="Workspace the lesson came from.")

    receipt = sub.add_parser("receipt", help="Record writeback evidence.", parents=[common])
    receipt_sub = receipt.add_subparsers(dest="receipt_command", required=True)
    record = receipt_sub.add_parser(
        "record", help="Append a receipt for a dispatch.", parents=[common]
    )
    record.add_argument("--dispatch", required=True)
    record.add_argument(
        "--verdict",
        required=True,
        choices=["passed", "failed", "needs_review", "blocked"],
    )
    record.add_argument("--summary", required=True)
    record.add_argument("--evidence", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except ProjectHerdrError as exc:
        print(exc, file=sys.stderr)
        return exc.exit_code


def _dispatch(args: argparse.Namespace) -> int:
    root = ControlRoot.resolve(getattr(args, "root", None))
    if args.command == "start":
        return _start(args, root)
    if args.command == "doctor":
        return _doctor(args, root)
    if args.command == "workspaces":
        return _workspaces(args, root)
    if args.command == "workspace":
        return _workspace_show(args, root)
    if args.command == "status":
        return _status(args, root)
    if args.command == "dispatch":
        return _dispatch_command(args, root)
    if args.command == "inbox":
        return _inbox(args, root)
    if args.command == "notes":
        return _notes(args, root)
    if args.command == "context":
        return _context(args, root)
    if args.command == "sync":
        return _sync(args, root)
    if args.command == "lesson":
        return _lesson(args, root)
    if args.command == "receipt":
        return _receipt_command(args, root)
    raise ProjectHerdrError(f"unknown command {args.command}")


def _start(args: argparse.Namespace, root: ControlRoot) -> int:
    payload = {
        "root": str(root.root),
        "next": [
            "project-herdr doctor",
            "project-herdr workspaces",
            "project-herdr status",
            "project-herdr inbox",
            "project-herdr notes",
        ],
        "rule": "Coordinator sessions stay in this repo. Workers edit registered workspaces only.",
        "harnesses": sorted(KNOWN_HARNESSES),
    }
    _emit(args, payload, "\n".join([payload["rule"], *payload["next"]]))
    return 0


def _doctor(args: argparse.Namespace, root: ControlRoot) -> int:
    overlay = load_overlay(root, getattr(args, "device", None))
    registry = load_registry(root)
    herdr = shutil.which("herdr")
    in_herdr = os_env_herdr()
    payload = {
        "ok": True,
        "root": str(root.root),
        "device": overlay.device,
        "workspaces": len(registry.workspaces),
        "git": bool(shutil.which("git")),
        "herdr": herdr or "",
        "herdr_pane": in_herdr,
        "harnesses": sorted(KNOWN_HARNESSES),
    }
    kinds = " ".join(payload["harnesses"])
    lines = [
        f"root            {payload['root']}",
        f"device          {payload['device']}",
        f"workspaces      {payload['workspaces']}",
        f"git             {'yes' if payload['git'] else 'no'}",
        f"herdr           {payload['herdr'] or 'missing (optional)'}",
        f"herdr_pane      {'yes' if in_herdr else 'no'}",
        f"harnesses       {kinds}",
    ]
    _emit(args, payload, "\n".join(lines))
    return 0 if payload["git"] else 1


def _workspaces(args: argparse.Namespace, root: ControlRoot) -> int:
    registry = load_registry(root)
    payload = [
        {
            "id": item.id,
            "name": item.name,
            "kind": item.kind,
            "remote": item.remote,
            "default_harness": item.default_harness,
            "entry": item.entry,
            "notes": item.notes,
        }
        for item in registry.workspaces
    ]
    _emit(args, payload, render_workspaces(registry.workspaces))
    return 0


def _workspace_show(args: argparse.Namespace, root: ControlRoot) -> int:
    workspace = require_workspace(root, args.id)
    overlay = load_overlay(root, getattr(args, "device", None))
    path = resolve_workspace_path(root, workspace.id, overlay, workspace)
    payload = {
        "id": workspace.id,
        "name": workspace.name,
        "kind": workspace.kind,
        "remote": workspace.remote,
        "default_harness": workspace.default_harness,
        "entry": workspace.entry,
        "notes": workspace.notes,
        "path": None if path is None else str(path),
        "device": overlay.device,
    }
    text = "\n".join(f"{key:18} {value}" for key, value in payload.items())
    _emit(args, payload, text)
    return 0


def _status(args: argparse.Namespace, root: ControlRoot) -> int:
    registry = load_registry(root)
    overlay = load_overlay(root, getattr(args, "device", None))
    rows = collect_status(root, registry, overlay, args.workspace)
    _emit(args, [row.as_dict() for row in rows], render_status(rows))
    return 0


def _dispatch_command(args: argparse.Namespace, root: ControlRoot) -> int:
    if args.dispatch_command == "list":
        items = list_dispatches(root)
        _emit(args, [item.as_dict() for item in items], render_dispatches(items))
        return 0
    if args.dispatch_command == "show":
        item = get_dispatch(root, args.id)
        _emit(args, item.as_dict(), json.dumps(item.as_dict(), indent=2))
        return 0
    if args.dispatch_command == "create":
        return _dispatch_create(args, root)
    if args.dispatch_command == "attach":
        item = mark_dispatch(root, get_dispatch(root, args.id), pr_url=args.pr)
        write_notes(root)
        _emit(args, item.as_dict(), f"{item.id}  {item.status}  {item.pr_url}")
        return 0
    raise ProjectHerdrError(f"unknown dispatch command {args.dispatch_command}")


def _dispatch_create(
    args: argparse.Namespace,
    root: ControlRoot,
    adapter: HerdrAdapter | None = None,
) -> int:
    workspace = require_workspace(root, args.workspace)
    overlay = load_overlay(root, getattr(args, "device", None))
    item = create_dispatch(
        root,
        workspace,
        args.objective,
        harness=args.harness,
        authorization=Authorization(
            push=args.allow_push,
            merge=args.allow_merge,
            send=args.allow_send,
            delete=args.allow_delete,
        ),
        acceptance_commands=tuple(args.accept),
    )
    path = resolve_workspace_path(root, workspace.id, overlay, workspace)
    prompt = write_worker_prompt(
        root,
        item,
        workspace,
        str(path) if path is not None else "(unresolved)",
    )
    item = mark_dispatch(root, item, prompt_path=_rel(root, prompt))
    if args.ready or args.enqueue:
        item = mark_dispatch(root, item, status="ready")
    if args.enqueue:
        if path is None or not path.exists():
            raise AdapterError(
                f"workspace {workspace.id} path is unresolved; wrote a ready contract instead"
            )
        if workspace.kind != "control-plane" and path.resolve() == root.root:
            raise AdapterError(
                "refusing to enqueue a product workspace whose path is the control-plane root"
            )
        result = (adapter or default_adapter()).enqueue(
            EnqueueRequest(
                dispatch=item,
                workspace=workspace,
                workspace_path=str(path),
                prompt_path=str(prompt),
                harness=item.harness,
            )
        )
        item = mark_dispatch(
            root,
            item,
            status="dispatched" if result.ok else "ready",
            herdr_requested=True,
            herdr_result=result.reason,
        )
        if not result.ok:
            write_notes(root)
            raise AdapterError(f"{result.reason}: {result.detail}")
    write_notes(root)
    _emit(args, item.as_dict(), f"{item.id}  {item.status}  {item.workspace}")
    return 0


def _inbox(args: argparse.Namespace, root: ControlRoot) -> int:
    items = build_inbox(root)
    _emit(args, [item.as_dict() for item in items], render_inbox(items))
    return 0


def _notes(args: argparse.Namespace, root: ControlRoot) -> int:
    result = write_notes(root)
    payload = {
        "path": str(root.notes_file),
        "archived": str(root.archived_file),
        "archived_added": len(result.archived_added),
        "notes": result.notes,
    }
    _emit(args, payload, result.notes.rstrip("\n"))
    return 0


def _context(args: argparse.Namespace, root: ControlRoot) -> int:
    root.ensure_layout()
    payload = {
        "root": str(root.context_dir),
        "docs": str(root.context_docs_dir),
        "internal": str(root.context_internal_dir),
        "media": str(root.context_media_dir),
        "notes": str(root.notes_file),
        "rule": (
            "docs/ holds deliverables a human will open; internal/ holds worker reports "
            "and agent-facing evidence; media/ holds screenshots and recordings."
        ),
    }
    lines = [f"{key:10} {value}" for key, value in payload.items() if key != "rule"]
    lines.append(payload["rule"])
    _emit(args, payload, "\n".join(lines))
    return 0


def _sync(args: argparse.Namespace, root: ControlRoot) -> int:
    results = sync_dispatches(root, dry_run=args.dry_run)
    if not args.dry_run and results:
        write_notes(root)
    if not results:
        _emit(args, [], "No dispatches with a PR to sync.")
        return 0
    rows = [
        (item.dispatch_id, item.lifecycle, item.checks, item.action, " ".join(item.detail.split()))
        for item in results
    ]
    text = "\n".join("  ".join(cell or "-" for cell in row) for row in rows)
    _emit(args, [item.as_dict() for item in results], text)
    return 0


def _lesson(args: argparse.Namespace, root: ControlRoot) -> int:
    if args.lesson_command == "add":
        line = add_lesson(root, args.text, workspace=args.workspace)
        payload = {"path": str(lessons_file(root)), "line": line}
        _emit(args, payload, line)
        return 0
    raise ProjectHerdrError(f"unknown lesson command {args.lesson_command}")


def _receipt_command(args: argparse.Namespace, root: ControlRoot) -> int:
    item = get_dispatch(root, args.dispatch)
    receipt = record_receipt(
        root,
        dispatch_id=item.id,
        workspace=item.workspace,
        verdict=args.verdict,  # type: ignore[arg-type]
        summary=args.summary,
        evidence=tuple(args.evidence),
    )
    status = {
        "passed": "done",
        "needs_review": "needs_review",
        "failed": "blocked",
        "blocked": "blocked",
    }[receipt.verdict]
    mark_dispatch(root, item, status=status)  # type: ignore[arg-type]
    write_notes(root)
    _emit(args, receipt.as_dict(), f"{receipt.dispatch_id}  {receipt.verdict}  {receipt.summary}")
    return 0


def os_env_herdr() -> bool:
    import os

    return os.environ.get("HERDR_ENV") == "1"


def _rel(root: ControlRoot, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.root).as_posix()
    except ValueError:
        return str(path)


def _emit(args: argparse.Namespace, payload: object, text: str) -> None:
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(text)
