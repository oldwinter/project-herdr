from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ControlRoot:
    root: Path

    @classmethod
    def resolve(cls, root: str | Path | None) -> ControlRoot:
        base = Path(root).expanduser().resolve() if root else Path.cwd().resolve()
        return cls(root=base)

    @property
    def control(self) -> Path:
        return self.root / "control"

    @property
    def workspaces_file(self) -> Path:
        return self.control / "workspaces.toml"

    @property
    def workspaces_local_file(self) -> Path:
        return self.control / "workspaces.local.toml"

    @property
    def dispatches_dir(self) -> Path:
        return self.control / "dispatches"

    @property
    def receipts_dir(self) -> Path:
        return self.control / "receipts"

    @property
    def overlays_dir(self) -> Path:
        return self.control / "overlays"

    @property
    def runtime_dir(self) -> Path:
        return self.control / "runtime"

    def overlay_file(self, device: str) -> Path:
        return self.overlays_dir / device / "paths.toml"

    def dispatch_file(self, dispatch_id: str) -> Path:
        return self.dispatches_dir / f"{dispatch_id}.toml"

    def receipt_file(self, dispatch_id: str, recorded_at_stamp: str) -> Path:
        return self.receipts_dir / f"{dispatch_id}-{recorded_at_stamp}.json"

    def prompt_file(self, dispatch_id: str) -> Path:
        return self.runtime_dir / dispatch_id / "prompt.md"

    def ensure_layout(self) -> None:
        self.dispatches_dir.mkdir(parents=True, exist_ok=True)
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
