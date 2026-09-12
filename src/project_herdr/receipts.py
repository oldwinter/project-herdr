from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from project_herdr.errors import ConfigError, NotFoundError
from project_herdr.model import RECEIPT_VERDICTS, Receipt, ReceiptVerdict
from project_herdr.store import ControlRoot


def list_receipts(root: ControlRoot, dispatch_id: str | None = None) -> tuple[Receipt, ...]:
    if not root.receipts_dir.is_dir():
        return ()
    items: list[Receipt] = []
    for path in sorted(root.receipts_dir.glob("*.json")):
        item = load_receipt(path)
        if dispatch_id is None or item.dispatch_id == dispatch_id:
            items.append(item)
    return tuple(items)


def latest_receipt(root: ControlRoot, dispatch_id: str) -> Receipt | None:
    matches = list_receipts(root, dispatch_id)
    if not matches:
        return None
    return matches[-1]


def load_receipt(path: Path) -> Receipt:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read receipt {path}: {exc}") from exc
    verdict = str(payload.get("verdict") or "")
    if verdict not in RECEIPT_VERDICTS:
        raise ConfigError(f"{path} has invalid verdict {verdict!r}")
    evidence = payload.get("evidence") or []
    if not isinstance(evidence, list):
        raise ConfigError(f"{path} evidence must be a list")
    return Receipt(
        dispatch_id=str(payload["dispatch_id"]),
        workspace=str(payload.get("workspace") or ""),
        recorded_at=str(payload.get("recorded_at") or ""),
        verdict=verdict,  # type: ignore[arg-type]
        summary=str(payload.get("summary") or ""),
        evidence=tuple(str(item) for item in evidence),
    )


def record_receipt(
    root: ControlRoot,
    *,
    dispatch_id: str,
    workspace: str,
    verdict: ReceiptVerdict,
    summary: str,
    evidence: tuple[str, ...] = (),
    now: datetime | None = None,
) -> Receipt:
    if verdict not in RECEIPT_VERDICTS:
        raise ConfigError(f"invalid verdict {verdict!r}")
    text = summary.strip()
    if not text:
        raise ConfigError("receipt summary is required")
    if not root.dispatch_file(dispatch_id).is_file():
        raise NotFoundError(f"unknown dispatch {dispatch_id!r}")
    stamp_dt = now or datetime.now(UTC)
    recorded_at = stamp_dt.strftime("%Y%m%dT%H%M%SZ")
    root.ensure_layout()
    receipt = Receipt(
        dispatch_id=dispatch_id,
        workspace=workspace,
        recorded_at=recorded_at,
        verdict=verdict,
        summary=text,
        evidence=evidence,
    )
    path = root.receipt_file(dispatch_id, recorded_at)
    if path.exists():
        path = root.receipt_file(dispatch_id, stamp_dt.strftime("%Y%m%dT%H%M%S%fZ"))
    path.write_text(json.dumps(receipt.as_dict(), indent=2) + "\n", encoding="utf-8")
    return receipt
