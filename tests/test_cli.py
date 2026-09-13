from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from project_herdr.cli import main
from support import make_root, write_overlay


class CliTest(unittest.TestCase):
    def test_workspaces_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            payload = self._run(
                ["--root", str(root.root), "workspaces", "--json"]
            )
            ids = [row["id"] for row in json.loads(payload)]
            self.assertEqual(ids, ["project-herdr", "novel"])

    def test_dispatch_create_and_inbox(self) -> None:
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
            inbox = self._run(["--root", str(root.root), "--json", "inbox"])
            self.assertEqual(json.loads(inbox), [])
            self._run(
                [
                    "--root",
                    str(root.root),
                    "receipt",
                    "record",
                    "--dispatch",
                    dispatch_id,
                    "--verdict",
                    "needs_review",
                    "--summary",
                    "Please check the ending",
                ]
            )
            inbox = json.loads(self._run(["--root", str(root.root), "--json", "inbox"]))
            self.assertEqual(inbox[0]["dispatch_id"], dispatch_id)
            self.assertEqual(inbox[0]["kind"], "review")

    def test_enqueue_without_path_does_not_touch_product(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            product = base / "novel"
            product.mkdir()
            (product / "story.md").write_text("keep\n", encoding="utf-8")
            root = make_root(base / "control")
            code = main(
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
                    "--enqueue",
                ]
            )
            self.assertEqual(code, 3)
            self.assertEqual((product / "story.md").read_text(encoding="utf-8"), "keep\n")

    def test_status_uses_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp) / "cp")
            write_overlay(root, "testdev", {"novel": str(Path(tmp) / "missing-novel")})
            payload = json.loads(
                self._run(
                    [
                        "--root",
                        str(root.root),
                        "--device",
                        "testdev",
                        "--json",
                        "status",
                        "--workspace",
                        "novel",
                    ]
                )
            )
            self.assertEqual(payload[0]["path_state"], "missing")

    def test_dispatch_lifecycle_refreshes_notes_and_attaches_pr(self) -> None:
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
            notes = root.notes_file.read_text(encoding="utf-8")
            self.assertIn(f"- [ ] [{dispatch_id}]", notes)
            self.assertIn("waiting for a worker", notes)

            self._run(
                [
                    "--root",
                    str(root.root),
                    "dispatch",
                    "attach",
                    dispatch_id,
                    "--pr",
                    "https://github.com/example/novel/pull/7",
                ]
            )
            shown = json.loads(
                self._run(["--root", str(root.root), "--json", "dispatch", "show", dispatch_id])
            )
            self.assertEqual(shown["pr_url"], "https://github.com/example/novel/pull/7")
            self.assertIn("[PR](https://github.com/example/novel/pull/7)", root.notes_file.read_text(encoding="utf-8"))

            self._run(
                [
                    "--root",
                    str(root.root),
                    "receipt",
                    "record",
                    "--dispatch",
                    dispatch_id,
                    "--verdict",
                    "passed",
                    "--summary",
                    "Chapter merged",
                ]
            )
            notes = root.notes_file.read_text(encoding="utf-8")
            self.assertIn(f"- [x] [{dispatch_id}]", notes)
            printed = self._run(["--root", str(root.root), "notes"])
            self.assertEqual(printed, notes.strip())

    def test_context_layout_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            payload = json.loads(self._run(["--root", str(root.root), "--json", "context"]))
            for key in ("docs", "internal", "media"):
                self.assertTrue(Path(payload[key]).is_dir(), key)

    def test_worker_prompt_names_output_destination(self) -> None:
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
                ]
            )
            dispatch_id = created.split()[0]
            prompt = root.prompt_file(dispatch_id).read_text(encoding="utf-8")
            self.assertIn(f"context/internal/{dispatch_id}/report.md", prompt)
            self.assertIn("One dispatch is one workstream", prompt)
            self.assertIn(f"project-herdr dispatch attach {dispatch_id} --pr", prompt)

    def test_doctor_lists_harness_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            payload = json.loads(
                self._run(["--root", str(root.root), "--json", "doctor"])
            )
            self.assertIn("codex", payload["harnesses"])
            self.assertIn("pi", payload["harnesses"])
            self.assertEqual(payload["harnesses"], sorted(payload["harnesses"]))

    def _run(self, argv: list[str]) -> str:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(argv)
        self.assertEqual(code, 0, buffer.getvalue())
        return buffer.getvalue().strip()
