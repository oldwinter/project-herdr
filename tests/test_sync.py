from __future__ import annotations

import io
import json
import tempfile
import unittest
from collections.abc import Sequence
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from project_herdr.cli import main
from project_herdr.dispatch import create_dispatch, get_dispatch, mark_dispatch
from project_herdr.errors import AdapterError
from project_herdr.lessons import add_lesson, lessons_file
from project_herdr.receipts import latest_receipt
from project_herdr.registry import load_registry
from project_herdr.sync import probe_pr, sync_dispatches
from support import make_root

PR = "https://github.com/example/novel/pull/7"


def _gh(payload: dict[str, object], code: int = 0):
    def runner(argv: Sequence[str]) -> tuple[int, str, str]:
        assert argv[:3] == ["/usr/bin/gh", "pr", "view"], argv
        return code, json.dumps(payload), "" if code == 0 else "boom"

    return runner


class SyncTest(unittest.TestCase):
    def _dispatch(self, root, status="dispatched"):
        novel = load_registry(root).get("novel")
        assert novel is not None
        item = create_dispatch(root, novel, "Draft chapter one")
        return mark_dispatch(root, item, status=status, pr_url=PR)

    def test_probe_classifies_checks(self) -> None:
        state = probe_pr(
            PR,
            "/usr/bin/gh",
            _gh({"state": "OPEN", "statusCheckRollup": [{"conclusion": "SUCCESS"}, {"status": "IN_PROGRESS"}]}),
        )
        self.assertEqual((state.lifecycle, state.checks), ("open", "pending"))
        state = probe_pr(PR, "/usr/bin/gh", _gh({"state": "OPEN", "statusCheckRollup": [{"conclusion": "FAILURE"}]}))
        self.assertEqual(state.checks, "failing")
        state = probe_pr(PR, "/usr/bin/gh", _gh({}, code=1))
        self.assertEqual(state.lifecycle, "unknown")
        self.assertIn("boom", state.detail)

    def test_merged_pr_closes_dispatch_with_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            item = self._dispatch(root)
            results = sync_dispatches(
                root,
                runner=_gh({"state": "MERGED", "mergedAt": "2026-09-13T00:00:00Z", "statusCheckRollup": []}),
                which=lambda _: "/usr/bin/gh",
            )
            self.assertEqual(results[0].action, "done")
            self.assertEqual(get_dispatch(root, item.id).status, "done")
            receipt = latest_receipt(root, item.id)
            assert receipt is not None
            self.assertEqual(receipt.verdict, "passed")
            self.assertEqual(receipt.evidence, (PR,))

    def test_failing_ci_flags_review_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            item = self._dispatch(root)
            runner = _gh({"state": "OPEN", "statusCheckRollup": [{"conclusion": "FAILURE"}]})
            first = sync_dispatches(root, runner=runner, which=lambda _: "/usr/bin/gh")
            second = sync_dispatches(root, runner=runner, which=lambda _: "/usr/bin/gh")
            self.assertEqual(first[0].action, "needs_review")
            self.assertEqual(second[0].action, "unchanged")
            self.assertEqual(get_dispatch(root, item.id).status, "needs_review")

    def test_closed_pr_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            item = self._dispatch(root)
            results = sync_dispatches(
                root, runner=_gh({"state": "CLOSED"}), which=lambda _: "/usr/bin/gh"
            )
            self.assertEqual(results[0].action, "blocked")
            self.assertEqual(get_dispatch(root, item.id).status, "blocked")

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            item = self._dispatch(root)
            results = sync_dispatches(
                root, runner=_gh({"state": "MERGED"}), which=lambda _: "/usr/bin/gh", dry_run=True
            )
            self.assertEqual(results[0].action, "done")
            self.assertEqual(get_dispatch(root, item.id).status, "dispatched")
            self.assertIsNone(latest_receipt(root, item.id))

    def test_missing_gh_fails_closed_only_when_needed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            self.assertEqual(sync_dispatches(root, which=lambda _: None), ())
            self._dispatch(root)
            with self.assertRaises(AdapterError):
                sync_dispatches(root, which=lambda _: None)

    def test_cli_sync_refreshes_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            item = self._dispatch(root)
            with mock.patch("project_herdr.sync.shutil.which", lambda _: "/usr/bin/gh"), mock.patch(
                "project_herdr.sync._subprocess_runner", _gh({"state": "MERGED"})
            ):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = main(["--root", str(root.root), "sync"])
            self.assertEqual(code, 0, buffer.getvalue())
            self.assertIn("done", buffer.getvalue())
            self.assertIn(f"- [x] [{item.id}]", root.notes_file.read_text(encoding="utf-8"))


class LessonsTest(unittest.TestCase):
    def test_add_lesson_appends_with_header_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            add_lesson(root, "  run   just check before receipts ", workspace="novel")
            add_lesson(root, "second")
            text = lessons_file(root).read_text(encoding="utf-8")
            self.assertEqual(text.count("# Lessons"), 1)
            self.assertIn("`novel` run just check before receipts", text)
            self.assertTrue(text.rstrip().endswith("second"))

    def test_cli_lesson_add(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(["--root", str(root.root), "lesson", "add", "hello", "--workspace", "novel"])
            self.assertEqual(code, 0)
            self.assertIn("`novel` hello", buffer.getvalue())
            self.assertTrue(lessons_file(root).is_file())


if __name__ == "__main__":
    unittest.main()
