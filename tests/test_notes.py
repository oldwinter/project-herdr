from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from project_herdr.dispatch import create_dispatch, mark_dispatch
from project_herdr.notes import COMPLETED_CAP, render_notes, write_notes
from project_herdr.receipts import record_receipt
from project_herdr.registry import load_registry
from support import make_root


class NotesTest(unittest.TestCase):
    def test_empty_root_renders_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            result = write_notes(root)
            self.assertIn("- [ ] no dispatches yet", result.notes)
            self.assertTrue(root.notes_file.is_file())
            self.assertEqual(result.archived_added, ())
            self.assertFalse(root.archived_file.exists())

    def test_live_items_are_unchecked_and_link_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            novel = load_registry(root).get("novel")
            assert novel is not None
            item = create_dispatch(root, novel, "Draft chapter one")
            mark_dispatch(root, item, status="dispatched", pr_url="https://example.com/pr/1")
            notes = render_notes(root).notes
            self.assertIn(f"- [ ] [{item.id}](dispatches/{item.id}.toml)", notes)
            self.assertIn("worker running", notes)
            self.assertIn("[PR](https://example.com/pr/1)", notes)
            self.assertNotIn("## novel", notes)

    def test_multiple_workspaces_get_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            registry = load_registry(root)
            for workspace_id, objective in (("novel", "Draft"), ("project-herdr", "Add doc")):
                workspace = registry.get(workspace_id)
                assert workspace is not None
                create_dispatch(root, workspace, objective)
            notes = render_notes(root).notes
            self.assertIn("## novel", notes)
            self.assertIn("## project-herdr", notes)

    def test_receipt_summary_replaces_status_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            novel = load_registry(root).get("novel")
            assert novel is not None
            item = create_dispatch(root, novel, "Draft chapter one")
            record_receipt(
                root,
                dispatch_id=item.id,
                workspace="novel",
                verdict="needs_review",
                summary="Ending still open",
            )
            mark_dispatch(root, item, status="needs_review")
            notes = render_notes(root).notes
            self.assertIn("Draft chapter one — Ending still open", notes)

    def test_completed_capped_and_overflow_archived_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            novel = load_registry(root).get("novel")
            assert novel is not None
            ids: list[str] = []
            for index in range(COMPLETED_CAP + 2):
                stamp = datetime(2026, 9, 1 + index, tzinfo=UTC)
                item = create_dispatch(root, novel, f"Task {index}", now=stamp)
                record_receipt(
                    root,
                    dispatch_id=item.id,
                    workspace="novel",
                    verdict="passed",
                    summary=f"finished {index}",
                    now=stamp,
                )
                mark_dispatch(root, item, status="done")
                ids.append(item.id)
            result = write_notes(root)
            checked = [line for line in result.notes.splitlines() if line.startswith("- [x]")]
            self.assertEqual(len(checked), COMPLETED_CAP)
            self.assertIn(ids[-1], checked[0])
            self.assertEqual(len(result.archived_added), 2)
            archived = root.archived_file.read_text(encoding="utf-8")
            self.assertIn(ids[0], archived)
            self.assertIn(ids[1], archived)
            self.assertNotIn(ids[-1], archived)

            write_notes(root)
            self.assertEqual(
                root.archived_file.read_text(encoding="utf-8").count(f"- [x] [{ids[0]}]"), 1
            )
            self.assertIn("[archived](archived.md)", result.notes)

    def test_write_is_atomic_and_leaves_no_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            write_notes(root)
            self.assertEqual(sorted(p.name for p in root.control.glob("notes.md*")), ["notes.md"])


if __name__ == "__main__":
    unittest.main()
