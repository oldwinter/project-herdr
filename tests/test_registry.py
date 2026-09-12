from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_herdr.errors import ConfigError, NotFoundError
from project_herdr.registry import load_registry, require_workspace
from support import make_root


class RegistryTest(unittest.TestCase):
    def test_loads_tracked_workspaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            registry = load_registry(root)
            self.assertEqual(registry.ids(), ("project-herdr", "novel"))
            novel = require_workspace(root, "novel")
            self.assertEqual(novel.kind, "product")
            self.assertTrue(novel.forbid_product_edits_from_coordinator)

    def test_local_override_replaces_by_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            root.workspaces_local_file.write_text(
                """
version = 1

[[workspaces]]
id = "novel"
name = "Novel Local"
kind = "product"
remote = "git@github.com:example/novel.git"
default_harness = "grok"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            novel = require_workspace(root, "novel")
            self.assertEqual(novel.name, "Novel Local")
            self.assertEqual(novel.default_harness, "grok")

    def test_rejects_duplicate_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            root.workspaces_file.write_text(
                """
version = 1

[[workspaces]]
id = "dup"
name = "A"
kind = "product"
remote = "git@github.com:example/a.git"
default_harness = "grok"

[[workspaces]]
id = "dup"
name = "B"
kind = "product"
remote = "git@github.com:example/b.git"
default_harness = "grok"
""".strip()
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError):
                load_registry(root)

    def test_unknown_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            with self.assertRaises(NotFoundError):
                require_workspace(root, "missing")


if __name__ == "__main__":
    unittest.main()
