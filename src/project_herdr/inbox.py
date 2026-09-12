from __future__ import annotations

from project_herdr.dispatch import list_dispatches
from project_herdr.model import InboxItem, InboxKind
from project_herdr.receipts import latest_receipt
from project_herdr.store import ControlRoot


def build_inbox(root: ControlRoot) -> tuple[InboxItem, ...]:
    items: list[InboxItem] = []
    for dispatch in list_dispatches(root):
        if dispatch.status == "done":
            continue
        receipt = latest_receipt(root, dispatch.id)
        kind = _kind(dispatch.status, receipt.verdict if receipt else "")
        if kind is None:
            continue
        items.append(
            InboxItem(
                dispatch_id=dispatch.id,
                workspace=dispatch.workspace,
                status=dispatch.status,
                kind=kind,
                latest_verdict=receipt.verdict if receipt else "",
                summary=(receipt.summary if receipt else dispatch.objective),
                waiting_since=(receipt.recorded_at if receipt else dispatch.created_at),
            )
        )
    return tuple(items)


def _kind(status: str, verdict: str) -> InboxKind | None:
    if status == "blocked" or verdict == "blocked":
        return "blocked"
    if status == "needs_review" or verdict == "needs_review":
        return "review"
    if verdict == "failed":
        return "failed"
    return None
