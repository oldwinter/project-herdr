from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_herdr.gitstatus import remotes_match
from project_herdr.overlay import load_overlay, resolve_workspace_path
from project_herdr.registry import load_registry, require_workspace
from project_herdr.status import collect_status
from support import init_git, make_root, write_overlay


class StatusTest(unittest.TestCase):
    def test_https_and_ssh_remotes_match(self) -> None:
        self.assertTrue(
            remotes_match(
                "git@github.com:oldwinter/project-herdr.git",
                "https://github.com/oldwinter/project-herdr",
            )
        )

    def test_overlay_resolves_and_reports_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = make_root(base / "control-plane")
            novel = base / "novel"
            init_git(novel, "https://github.com/example/novel.git")
            write_overlay(root, "testdev", {"novel": str(novel)})
            overlay = load_overlay(root, "testdev")
            workspace = require_workspace(root, "novel")
            path = resolve_workspace_path(root, "novel", overlay, workspace)
            self.assertEqual(path, novel.resolve())
            rows = collect_status(root, load_registry(root), overlay, "novel")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].path_state, "resolved")
            self.assertEqual(rows[0].git_state, "ok")
            self.assertFalse(rows[0].dirty)

    def test_unresolved_without_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            overlay = load_overlay(root, "testdev")
            rows = collect_status(root, load_registry(root), overlay, "novel")
            self.assertEqual(rows[0].path_state, "unresolved")
            self.assertEqual(rows[0].git_state, "skipped")
