from __future__ import annotations

import re

WORKSPACE_ID = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
DISPATCH_ID = re.compile(r"^d-[0-9]{8}-[a-z0-9][a-z0-9-]{0,47}$")
SLUG = re.compile(r"[^a-z0-9]+")


def require_workspace_id(value: str) -> str:
    if not WORKSPACE_ID.match(value):
        raise ValueError(
            f"invalid workspace id {value!r}; use lowercase letters, digits, and hyphens"
        )
    return value


def slugify(text: str, fallback: str = "task") -> str:
    slug = SLUG.sub("-", text.strip().lower()).strip("-")
    slug = slug[:32].strip("-")
    return slug or fallback


def make_dispatch_id(stamp: str, objective: str, existing: set[str]) -> str:
    date = stamp[:8]
    base = f"d-{date}-{slugify(objective)}"
    if base not in existing and DISPATCH_ID.match(base):
        return base
    for index in range(2, 1000):
        candidate = f"{base}-{index}"
        if len(candidate) > 64:
            candidate = f"d-{date}-task-{index}"
        if candidate not in existing:
            return candidate
    raise ValueError("exhausted dispatch id space for this date")
