from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        payload = tomllib.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a TOML table")
    return payload


def dump_toml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    tables: list[tuple[str, dict[str, Any]]] = []
    for key, value in data.items():
        if isinstance(value, dict):
            tables.append((key, value))
        else:
            lines.append(f"{key} = {_format_value(value)}")
    if lines and tables:
        lines.append("")
    for name, table in tables:
        lines.append(f"[{name}]")
        for key, value in table.items():
            lines.append(f"{key} = {_format_value(value)}")
        lines.append("")
    text = "\n".join(lines).rstrip() + "\n"
    return text


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_format_value(item) for item in value) + "]"
    if value is None:
        return '""'
    return _format_string(str(value))


def _format_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'
