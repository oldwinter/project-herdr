from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

WorkspaceKind = Literal["control-plane", "product", "knowledge", "tooling"]
DispatchStatus = Literal[
    "drafted",
    "ready",
    "dispatched",
    "needs_review",
    "done",
    "blocked",
]
ReceiptVerdict = Literal["passed", "failed", "needs_review", "blocked"]
InboxKind = Literal["review", "blocked", "failed"]

WORKSPACE_KINDS: frozenset[str] = frozenset(
    {"control-plane", "product", "knowledge", "tooling"}
)
DISPATCH_STATUSES: frozenset[str] = frozenset(
    {"drafted", "ready", "dispatched", "needs_review", "done", "blocked"}
)
RECEIPT_VERDICTS: frozenset[str] = frozenset(
    {"passed", "failed", "needs_review", "blocked"}
)
KNOWN_HARNESSES: frozenset[str] = frozenset(
    {"droid", "grok", "codex", "pi", "claude", "hermes"}
)


@dataclass(frozen=True)
class Workspace:
    id: str
    name: str
    kind: WorkspaceKind
    remote: str
    default_harness: str = "grok"
    entry: str = ""
    forbid_product_edits_from_coordinator: bool = True
    notes: str = ""


@dataclass(frozen=True)
class Registry:
    version: int
    workspaces: tuple[Workspace, ...]

    def get(self, workspace_id: str) -> Workspace | None:
        for workspace in self.workspaces:
            if workspace.id == workspace_id:
                return workspace
        return None

    def ids(self) -> tuple[str, ...]:
        return tuple(workspace.id for workspace in self.workspaces)


@dataclass(frozen=True)
class Overlay:
    device: str
    paths: dict[str, str] = field(default_factory=dict)

    def path_for(self, workspace_id: str) -> str | None:
        return self.paths.get(workspace_id)


@dataclass(frozen=True)
class Authorization:
    push: bool = False
    merge: bool = False
    send: bool = False
    delete: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {
            "push": self.push,
            "merge": self.merge,
            "send": self.send,
            "delete": self.delete,
        }


@dataclass(frozen=True)
class Dispatch:
    id: str
    workspace: str
    objective: str
    created_at: str
    status: DispatchStatus = "drafted"
    harness: str = "grok"
    authorization: Authorization = field(default_factory=Authorization)
    acceptance_commands: tuple[str, ...] = ()
    writeback_receipt_dir: str = "control/receipts"
    prompt_path: str = ""
    herdr_requested: bool = False
    herdr_result: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "workspace": self.workspace,
            "objective": self.objective,
            "created_at": self.created_at,
            "status": self.status,
            "harness": self.harness,
            "authorization": self.authorization.as_dict(),
            "acceptance_commands": list(self.acceptance_commands),
            "writeback_receipt_dir": self.writeback_receipt_dir,
            "prompt_path": self.prompt_path,
            "herdr_requested": self.herdr_requested,
            "herdr_result": self.herdr_result,
        }


@dataclass(frozen=True)
class Receipt:
    dispatch_id: str
    workspace: str
    recorded_at: str
    verdict: ReceiptVerdict
    summary: str
    evidence: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "dispatch_id": self.dispatch_id,
            "workspace": self.workspace,
            "recorded_at": self.recorded_at,
            "verdict": self.verdict,
            "summary": self.summary,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class WorkspaceStatus:
    id: str
    name: str
    kind: WorkspaceKind
    remote: str
    path: str | None
    path_state: Literal["resolved", "unresolved", "missing"]
    git_state: Literal["ok", "missing", "not_git", "remote_mismatch", "skipped"]
    branch: str = ""
    head: str = ""
    dirty: bool = False
    observed_remote: str = ""
    live_dispatches: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "remote": self.remote,
            "path": self.path,
            "path_state": self.path_state,
            "git_state": self.git_state,
            "branch": self.branch,
            "head": self.head,
            "dirty": self.dirty,
            "observed_remote": self.observed_remote,
            "live_dispatches": list(self.live_dispatches),
        }


@dataclass(frozen=True)
class InboxItem:
    dispatch_id: str
    workspace: str
    status: DispatchStatus
    kind: InboxKind
    latest_verdict: str
    summary: str
    waiting_since: str

    def as_dict(self) -> dict[str, object]:
        return {
            "dispatch_id": self.dispatch_id,
            "workspace": self.workspace,
            "status": self.status,
            "kind": self.kind,
            "latest_verdict": self.latest_verdict,
            "summary": self.summary,
            "waiting_since": self.waiting_since,
        }


@dataclass(frozen=True)
class EnqueueRequest:
    dispatch: Dispatch
    workspace: Workspace
    workspace_path: str
    prompt_path: str
    harness: str


@dataclass(frozen=True)
class EnqueueResult:
    ok: bool
    reason: str
    detail: str = ""
