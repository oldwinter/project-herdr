from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_herdr.dispatch import create_dispatch, list_dispatches, mark_dispatch
from project_herdr.errors import ConfigError
from project_herdr.inbox import build_inbox
from project_herdr.receipts import record_receipt
from project_herdr.registry import require_workspace
from support import make_root


class DispatchInboxTest(unittest.TestCase):
    def test_create_writes_contract_not_product_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            product = base / "novel"
            product.mkdir()
            sentinel = product / "story.md"
            sentinel.write_text("keep\n", encoding="utf-8")
            root = make_root(base / "control")
            workspace = require_workspace(root, "novel")
            item = create_dispatch(root, workspace, "Draft chapter one")
            self.assertTrue(item.id.startswith("d-"))
            self.assertEqual(item.status, "drafted")
            self.assertTrue(root.dispatch_file(item.id).is_file())
            self.assertTrue((root.root / item.prompt_path).is_file())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")
            self.assertEqual(list(product.iterdir()), [sentinel])

    def test_blank_objective_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            workspace = require_workspace(root, "novel")
            with self.assertRaises(ConfigError):
                create_dispatch(root, workspace, "   ")

    def test_receipt_moves_dispatch_into_and_out_of_inbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            workspace = require_workspace(root, "novel")
            item = create_dispatch(root, workspace, "Draft chapter one")
            self.assertEqual(build_inbox(root), ())
            record_receipt(
                root,
                dispatch_id=item.id,
                workspace=item.workspace,
                verdict="needs_review",
                summary="Need a human look at the ending",
            )
            mark_dispatch(root, item, status="needs_review")
            inbox = build_inbox(root)
            self.assertEqual(len(inbox), 1)
            self.assertEqual(inbox[0].kind, "review")
            record_receipt(
                root,
                dispatch_id=item.id,
                workspace=item.workspace,
                verdict="passed",
                summary="Accepted",
            )
            mark_dispatch(root, get_latest(root), status="done")
            self.assertEqual(build_inbox(root), ())


def get_latest(root):
    items = list_dispatches(root)
    return items[-1]
