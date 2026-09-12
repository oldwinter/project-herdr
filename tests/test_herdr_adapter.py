from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from project_herdr.dispatch import create_dispatch
from project_herdr.herdr import HerdrAdapter
from project_herdr.model import EnqueueRequest
from project_herdr.registry import require_workspace
from support import make_root


class HerdrAdapterTest(unittest.TestCase):
    def test_fails_closed_outside_herdr_pane(self) -> None:
        adapter = HerdrAdapter(env={}, which=lambda _: "/usr/bin/herdr")
        result = adapter.enqueue(_request())
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "not_in_herdr_pane")

    def test_fails_closed_when_herdr_missing(self) -> None:
        adapter = HerdrAdapter(env={"HERDR_ENV": "1"}, which=lambda _: None)
        result = adapter.enqueue(_request())
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "herdr_missing")

    def test_dispatches_without_waiting_for_worker(self) -> None:
        calls: list[list[str]] = []

        def runner(argv, env):
            calls.append(list(argv))
            if argv[1] == "pane":
                return 0, json.dumps({"result": {"pane": {"pane_id": "w1:p2"}}}), ""
            return 0, "{}", ""

        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            workspace = require_workspace(root, "novel")
            item = create_dispatch(root, workspace, "Draft chapter one")
            prompt = root.root / item.prompt_path
            adapter = HerdrAdapter(
                env={"HERDR_ENV": "1"},
                runner=runner,
                which=lambda _: "/usr/bin/herdr",
            )
            result = adapter.enqueue(
                EnqueueRequest(
                    dispatch=item,
                    workspace=workspace,
                    workspace_path="/tmp/novel",
                    prompt_path=str(prompt),
                    harness="codex",
                )
            )
        self.assertTrue(result.ok)
        self.assertEqual(result.reason, "dispatched")
        self.assertEqual(calls[0][1:3], ["pane", "split"])
        self.assertIn("/tmp/novel", calls[0])
        self.assertEqual(calls[1][1:3], ["agent", "start"])
        self.assertEqual(calls[2][1:3], ["agent", "prompt"])
        self.assertNotIn("--wait", calls[2])


def _request() -> EnqueueRequest:
    from project_herdr.model import Dispatch, Workspace

    workspace = Workspace(
        id="novel",
        name="Novel",
        kind="product",
        remote="git@github.com:example/novel.git",
    )
    dispatch = Dispatch(
        id="d-20260913-draft",
        workspace="novel",
        objective="Draft",
        created_at="20260913T000000Z",
    )
    return EnqueueRequest(
        dispatch=dispatch,
        workspace=workspace,
        workspace_path="/tmp/novel",
        prompt_path="/tmp/prompt.md",
        harness="codex",
    )
