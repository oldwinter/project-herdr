from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from project_herdr.cli import main
from project_herdr.dispatch import create_dispatch, get_dispatch, mark_dispatch
from project_herdr.errors import AdapterError, ConfigError
from project_herdr.herdr import HerdrAdapter, extract_read_text
from project_herdr.notes import render_notes
from project_herdr.receipts import record_receipt
from project_herdr.registry import load_registry
from project_herdr.session import incremental_text, pull_session, resolve_herdr_agent, update_session
from support import make_root


class SessionTest(unittest.TestCase):
    def test_update_appends_step_without_changing_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            item = self._dispatch(root, status="ready")
            entry = update_session(root, item.id, "  Write the opening  ")
            self.assertEqual(entry.kind, "step")
            self.assertEqual(entry.step, "Write the opening")
            self.assertEqual(get_dispatch(root, item.id).status, "ready")
            log = root.session_log_file(item.id).read_text(encoding="utf-8")
            self.assertIn('"kind": "step"', log)
            self.assertIn("Write the opening", log)

    def test_blank_step_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            item = self._dispatch(root)
            with self.assertRaises(ConfigError):
                update_session(root, item.id, "   ")

    def test_notes_prefer_step_while_dispatched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            item = self._dispatch(root, status="dispatched")
            update_session(root, item.id, "Drafting chapter one")
            notes = render_notes(root).notes
            self.assertIn("Draft chapter one — Drafting chapter one", notes)
            self.assertNotIn("worker running", notes)

    def test_receipt_still_wins_after_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            item = self._dispatch(root, status="dispatched")
            update_session(root, item.id, "Drafting")
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
            self.assertNotIn("Drafting", notes)

    def test_incremental_suffix_and_unchanged(self) -> None:
        self.assertEqual(incremental_text("abc", "abcdef"), ("def", False))
        self.assertEqual(incremental_text("abc", "abc"), ("", False))
        self.assertEqual(incremental_text("", "hello"), ("hello", False))

    def test_incremental_sliding_window_and_reset(self) -> None:
        self.assertEqual(incremental_text("xxabc", "abcdef"), ("def", False))
        self.assertEqual(incremental_text("old pane", "brand new"), ("brand new", True))

    def test_extract_read_text_from_herdr_json(self) -> None:
        payload = json.dumps({"id": "cli:agent:read", "result": {"text": "hello pane"}})
        self.assertEqual(extract_read_text(payload), "hello pane")
        self.assertEqual(extract_read_text("plain"), "plain")

    def test_pull_appends_only_new_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            item = self._dispatch(
                root,
                status="dispatched",
                herdr_result="agent=wdraft pane=w1:p2",
            )
            snapshots = ["hello", "hello world"]

            def runner(argv, env):
                self.assertEqual(argv[1:4], ["agent", "read", "wdraft"])
                text = snapshots.pop(0)
                return 0, json.dumps({"result": {"text": text}}), ""

            adapter = HerdrAdapter(
                env={"HERDR_ENV": "1"},
                runner=runner,
                which=lambda _: "/usr/bin/herdr",
            )
            first = pull_session(root, item.id, adapter=adapter)
            second = pull_session(root, item.id, adapter=adapter)
            self.assertEqual(first.action, "appended")
            self.assertEqual(first.increment, "hello")
            self.assertEqual(second.action, "appended")
            self.assertEqual(second.increment, " world")
            self.assertFalse(second.reset)
            log = root.session_log_file(item.id).read_text(encoding="utf-8")
            self.assertEqual(log.count('"kind": "readout"'), 2)
            self.assertEqual(root.session_cursor_file(item.id).read_text(encoding="utf-8"), "hello world")

    def test_pull_unchanged_and_dry_run_write_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            item = self._dispatch(root, status="dispatched", herdr_result="dispatched")

            def runner(argv, env):
                return 0, json.dumps({"result": {"text": "same"}}), ""

            adapter = HerdrAdapter(
                env={"HERDR_ENV": "1"},
                runner=runner,
                which=lambda _: "/usr/bin/herdr",
            )
            dry = pull_session(root, item.id, adapter=adapter, dry_run=True)
            self.assertEqual(dry.action, "appended")
            self.assertFalse(root.session_log_file(item.id).exists())
            written = pull_session(root, item.id, adapter=adapter)
            again = pull_session(root, item.id, adapter=adapter)
            self.assertEqual(written.action, "appended")
            self.assertEqual(again.action, "unchanged")
            self.assertEqual(root.session_log_file(item.id).read_text(encoding="utf-8").count("\n"), 1)

    def test_pull_fails_closed_without_herdr_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            item = self._dispatch(root, status="ready")
            with self.assertRaises(AdapterError):
                pull_session(root, item.id)
            self.assertFalse(root.session_log_file(item.id).exists())

    def test_pull_fails_closed_outside_herdr_pane(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            item = self._dispatch(root, status="dispatched", herdr_result="dispatched")
            adapter = HerdrAdapter(env={}, which=lambda _: "/usr/bin/herdr")
            with self.assertRaises(AdapterError):
                pull_session(root, item.id, adapter=adapter)

    def test_resolve_agent_from_legacy_dispatched_reason(self) -> None:
        item = self._dispatch_obj(herdr_result="dispatched")
        self.assertTrue(resolve_herdr_agent(item).startswith("d"))

    def test_cli_update_show_and_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            created = self._run(
                [
                    "--root",
                    str(root.root),
                    "--device",
                    "testdev",
                    "dispatch",
                    "create",
                    "--workspace",
                    "novel",
                    "--objective",
                    "Draft chapter one",
                    "--ready",
                ]
            )
            dispatch_id = created.split()[0]
            prompt = root.prompt_file(dispatch_id).read_text(encoding="utf-8")
            self.assertIn("session update --dispatch", prompt)
            shown = self._run(
                [
                    "--root",
                    str(root.root),
                    "session",
                    "update",
                    "--dispatch",
                    dispatch_id,
                    "--step",
                    "Write the opening",
                ]
            )
            self.assertIn("Write the opening", shown)
            self.assertIn("Write the opening", root.notes_file.read_text(encoding="utf-8"))
            listing = json.loads(
                self._run(["--root", str(root.root), "--json", "session", "show"])
            )
            self.assertEqual(listing[0]["dispatch_id"], dispatch_id)
            self.assertEqual(listing[0]["latest_step"], "Write the opening")
            one = json.loads(
                self._run(["--root", str(root.root), "--json", "session", "show", dispatch_id])
            )
            self.assertEqual(one["entries"][0]["step"], "Write the opening")

    def test_pull_probe_failed_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            item = self._dispatch(root, status="dispatched", herdr_result="dispatched")

            def runner(argv, env):
                return 1, "", '{"error":{"code":"agent_not_found","message":"gone"}}'

            adapter = HerdrAdapter(
                env={"HERDR_ENV": "1"},
                runner=runner,
                which=lambda _: "/usr/bin/herdr",
            )
            result = pull_session(root, item.id, adapter=adapter)
            self.assertEqual(result.action, "probe_failed")
            self.assertFalse(root.session_log_file(item.id).exists())

    def test_cli_pull_without_session_exits_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            created = self._run(
                [
                    "--root",
                    str(root.root),
                    "--device",
                    "testdev",
                    "dispatch",
                    "create",
                    "--workspace",
                    "novel",
                    "--objective",
                    "Draft chapter one",
                    "--ready",
                ]
            )
            dispatch_id = created.split()[0]
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = main(["--root", str(root.root), "session", "pull", dispatch_id])
            self.assertEqual(code, 3)
            self.assertIn("no Herdr session", stderr.getvalue())

    def _dispatch(self, root, status="drafted", herdr_result=""):
        novel = load_registry(root).get("novel")
        assert novel is not None
        item = create_dispatch(root, novel, "Draft chapter one")
        if status == item.status and not herdr_result:
            return item
        return mark_dispatch(
            root,
            item,
            status=status,
            herdr_requested=bool(herdr_result),
            herdr_result=herdr_result,
        )

    def _dispatch_obj(self, herdr_result="dispatched"):
        from project_herdr.model import Dispatch

        return Dispatch(
            id="d-20260916-draft",
            workspace="novel",
            objective="Draft",
            created_at="20260916T000000Z",
            status="dispatched",
            herdr_requested=True,
            herdr_result=herdr_result,
        )

    def _run(self, argv: list[str]) -> str:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(argv)
        self.assertEqual(code, 0, buffer.getvalue())
        return buffer.getvalue().strip()


if __name__ == "__main__":
    unittest.main()
