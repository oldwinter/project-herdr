"""Append cross-workspace lessons to the shared context.

Cursor Projects grow their shared context as agents record what they learn.
Here that is one append-only Markdown list at ``context/docs/lessons.md``;
per-workspace knowledge still belongs in that workspace's own AGENTS.md.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from project_herdr.errors import ConfigError
from project_herdr.store import ControlRoot

LESSONS_HEADER = "# Lessons\n\nCross-workspace lessons the coordinator should reuse.\n"


def lessons_file(root: ControlRoot) -> Path:
    return root.context_docs_dir / "lessons.md"


def add_lesson(
    root: ControlRoot,
    text: str,
    *,
    workspace: str = "",
    now: datetime | None = None,
) -> str:
    body = " ".join(text.split())
    if not body:
        raise ConfigError("lesson text is required")
    root.ensure_layout()
    path = lessons_file(root)
    stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%d")
    scope = f" `{workspace}`" if workspace else ""
    line = f"- {stamp}{scope} {body}"
    existing = path.read_text(encoding="utf-8") if path.exists() else LESSONS_HEADER + "\n"
    if not existing.endswith("\n"):
        existing += "\n"
    path.write_text(existing + line + "\n", encoding="utf-8")
    return line
