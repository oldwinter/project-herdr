from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from project_herdr.model import KNOWN_HARNESSES, EnqueueRequest, EnqueueResult

Runner = Callable[[Sequence[str], Mapping[str, str]], tuple[int, str, str]]


@dataclass(frozen=True)
class HerdrAdapter:
    env: Mapping[str, str]
    runner: Runner | None = None
    which: Callable[[str], str | None] = shutil.which

    def enqueue(self, request: EnqueueRequest) -> EnqueueResult:
        if self.env.get("HERDR_ENV") != "1":
            return EnqueueResult(
                ok=False,
                reason="not_in_herdr_pane",
                detail="Run enqueue from a Herdr-managed pane, or leave the dispatch ready.",
            )
        kind = request.harness
        if kind not in KNOWN_HARNESSES:
            return EnqueueResult(
                ok=False,
                reason="unknown_harness",
                detail=f"harness {kind!r} is not a herdr --kind (use {', '.join(sorted(KNOWN_HARNESSES))}).",
            )
        herdr = self.which("herdr")
        if not herdr:
            return EnqueueResult(
                ok=False,
                reason="herdr_missing",
                detail="herdr is not on PATH.",
            )
        split_code, split_out, split_err = self._run(
            [
                herdr,
                "pane",
                "split",
                "--current",
                "--direction",
                "right",
                "--cwd",
                request.workspace_path,
                "--no-focus",
            ]
        )
        if split_code != 0:
            return EnqueueResult(
                ok=False,
                reason="herdr_split_failed",
                detail=(split_err or split_out).strip() or f"exit {split_code}",
            )
        pane_id = _pane_id(split_out)
        if not pane_id:
            return EnqueueResult(
                ok=True,
                reason="pane_prepared",
                detail=(split_out or "").strip() or f"split cwd={request.workspace_path}",
            )
        agent = _agent_name(request.dispatch.id)
        start_code, start_out, start_err = self._run(
            [
                herdr,
                "agent",
                "start",
                agent,
                "--kind",
                kind,
                "--pane",
                pane_id,
            ]
        )
        if start_code != 0:
            return EnqueueResult(
                ok=False,
                reason="herdr_start_failed",
                detail=(start_err or start_out).strip() or f"exit {start_code}",
            )
        prompt = Path(request.prompt_path).read_text(encoding="utf-8")
        prompt_code, prompt_out, prompt_err = self._run(
            [herdr, "agent", "prompt", agent, prompt]
        )
        if prompt_code != 0:
            return EnqueueResult(
                ok=False,
                reason="herdr_prompt_failed",
                detail=(prompt_err or prompt_out).strip() or f"exit {prompt_code}",
            )
        if self.runner is None:
            check_code, check_out, check_err = self._run([herdr, "agent", "get", agent])
            if check_code != 0:
                return EnqueueResult(
                    ok=False,
                    reason="herdr_status_failed",
                    detail=(check_err or check_out).strip() or f"exit {check_code}",
                )
            try:
                payload = json.loads(check_out)
                status = payload["result"]["agent"]["agent_status"]
            except (json.JSONDecodeError, KeyError, TypeError):
                return EnqueueResult(ok=False, reason="herdr_status_invalid", detail=check_out.strip())
            if status == "idle":
                return EnqueueResult(
                    ok=False,
                    reason="herdr_prompt_stalled",
                    detail="Herdr accepted the prompt but the agent remained idle.",
                )
        return EnqueueResult(
            ok=True,
            reason="dispatched",
            detail=f"agent={agent} pane={pane_id}",
        )

    def _run(self, argv: Sequence[str]) -> tuple[int, str, str]:
        if self.runner is not None:
            return self.runner(argv, self.env)
        import subprocess

        completed = subprocess.run(argv, check=False, capture_output=True, text=True)
        return completed.returncode, completed.stdout, completed.stderr


def default_adapter(env: Mapping[str, str] | None = None) -> HerdrAdapter:
    return HerdrAdapter(env=env if env is not None else os.environ)


def _pane_id(stdout: str) -> str | None:
    text = stdout.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        result = payload if isinstance(payload, dict) else {}
    pane = result.get("pane") if isinstance(result, dict) else None
    if not isinstance(pane, dict):
        return None
    pane_id = pane.get("pane_id")
    return str(pane_id) if pane_id else None


def _agent_name(dispatch_id: str) -> str:
    compact = dispatch_id.replace("-", "")
    if not compact or not compact[0].isalpha():
        compact = "w" + compact
    return compact[:32]
