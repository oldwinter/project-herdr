"""Pull PR state back into dispatches.

This is the file-based stand-in for a Cursor Project *subscription* on PRs:
instead of an event stream, the coordinator polls ``gh pr view`` for every
dispatch that has a ``pr_url`` and is not yet done, and converts the observed
state into a receipt plus a status change. ``gh`` is optional; without it the
command fails closed and touches nothing.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from project_herdr.dispatch import list_dispatches, mark_dispatch
from project_herdr.errors import AdapterError
from project_herdr.model import Dispatch
from project_herdr.receipts import record_receipt
from project_herdr.store import ControlRoot

Runner = Callable[[Sequence[str]], tuple[int, str, str]]
PrLifecycle = Literal["open", "merged", "closed", "unknown"]
Checks = Literal["passing", "failing", "pending", "none", "unknown"]

_FAILING = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}
_PENDING = {"PENDING", "QUEUED", "IN_PROGRESS", "WAITING", "REQUESTED", "EXPECTED"}


@dataclass(frozen=True)
class PrState:
    url: str
    lifecycle: PrLifecycle
    checks: Checks
    detail: str = ""


@dataclass(frozen=True)
class SyncResult:
    dispatch_id: str
    pr_url: str
    lifecycle: PrLifecycle
    checks: Checks
    action: Literal["done", "blocked", "needs_review", "unchanged", "probe_failed"]
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "dispatch_id": self.dispatch_id,
            "pr_url": self.pr_url,
            "lifecycle": self.lifecycle,
            "checks": self.checks,
            "action": self.action,
            "detail": self.detail,
        }


def probe_pr(url: str, gh: str, runner: Runner) -> PrState:
    code, out, err = runner(
        [gh, "pr", "view", url, "--json", "state,mergedAt,statusCheckRollup"]
    )
    if code != 0:
        return PrState(url=url, lifecycle="unknown", checks="unknown", detail=(err or out).strip())
    try:
        payload = json.loads(out or "{}")
    except json.JSONDecodeError as exc:
        return PrState(url=url, lifecycle="unknown", checks="unknown", detail=f"bad json: {exc}")
    state = str(payload.get("state") or "").upper()
    lifecycle: PrLifecycle
    if state == "MERGED" or payload.get("mergedAt"):
        lifecycle = "merged"
    elif state == "CLOSED":
        lifecycle = "closed"
    elif state == "OPEN":
        lifecycle = "open"
    else:
        lifecycle = "unknown"
    return PrState(url=url, lifecycle=lifecycle, checks=_checks(payload.get("statusCheckRollup")))


def sync_dispatches(
    root: ControlRoot,
    *,
    runner: Runner | None = None,
    which: Callable[[str], str | None] | None = None,
    dry_run: bool = False,
) -> tuple[SyncResult, ...]:
    candidates = [
        item for item in list_dispatches(root) if item.pr_url and item.status != "done"
    ]
    if not candidates:
        return ()
    gh = (which or shutil.which)("gh")
    if not gh:
        raise AdapterError("gh is not on PATH; nothing synced (install GitHub CLI or record receipts by hand)")
    run = runner or _subprocess_runner
    results: list[SyncResult] = []
    for item in candidates:
        state = probe_pr(item.pr_url, gh, run)
        results.append(_apply(root, item, state, dry_run=dry_run))
    return tuple(results)


def _apply(root: ControlRoot, item: Dispatch, state: PrState, *, dry_run: bool) -> SyncResult:
    base = {
        "dispatch_id": item.id,
        "pr_url": item.pr_url,
        "lifecycle": state.lifecycle,
        "checks": state.checks,
    }
    if state.lifecycle == "unknown":
        return SyncResult(**base, action="probe_failed", detail=state.detail)  # type: ignore[arg-type]
    if state.lifecycle == "merged":
        return _transition(root, item, "passed", "done", "PR merged", base, dry_run)
    if state.lifecycle == "closed":
        if item.status == "blocked":
            return SyncResult(**base, action="unchanged")  # type: ignore[arg-type]
        return _transition(root, item, "blocked", "blocked", "PR closed without merge", base, dry_run)
    if state.checks == "failing" and item.status != "needs_review":
        return _transition(root, item, "needs_review", "needs_review", "CI failing on PR", base, dry_run)
    return SyncResult(**base, action="unchanged")  # type: ignore[arg-type]


def _transition(
    root: ControlRoot,
    item: Dispatch,
    verdict: str,
    status: str,
    summary: str,
    base: dict[str, object],
    dry_run: bool,
) -> SyncResult:
    if not dry_run:
        record_receipt(
            root,
            dispatch_id=item.id,
            workspace=item.workspace,
            verdict=verdict,  # type: ignore[arg-type]
            summary=summary,
            evidence=(item.pr_url,),
        )
        mark_dispatch(root, item, status=status)  # type: ignore[arg-type]
    return SyncResult(**base, action=status, detail=summary)  # type: ignore[arg-type]


def _checks(rollup: object) -> Checks:
    if not isinstance(rollup, list) or not rollup:
        return "none"
    seen_pending = False
    for entry in rollup:
        if not isinstance(entry, dict):
            continue
        verdict = str(entry.get("conclusion") or entry.get("state") or entry.get("status") or "").upper()
        if verdict in _FAILING:
            return "failing"
        if verdict in _PENDING or not verdict:
            seen_pending = True
    return "pending" if seen_pending else "passing"


def _subprocess_runner(argv: Sequence[str]) -> tuple[int, str, str]:
    import subprocess

    completed = subprocess.run(argv, check=False, capture_output=True, text=True)
    return completed.returncode, completed.stdout, completed.stderr
