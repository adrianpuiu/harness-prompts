"""Gate runner.

The gate is a shell script (default: ``.harness/gate.sh``) that exits
zero if all configured checks pass and non-zero otherwise. We capture
stderr and a tail of stdout so the orchestrator can hand the output
back to the coder as failure feedback.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_TAIL_BYTES = 4000


@dataclass
class GateResult:
    passed: bool
    exit_code: int
    stderr_tail: str
    stdout_tail: str

    @property
    def feedback(self) -> str:
        """Single string suitable for ``last_feedback`` in the next round."""
        if self.passed:
            return ""
        parts: list[str] = []
        if self.stderr_tail.strip():
            parts.append(self.stderr_tail.strip())
        if self.stdout_tail.strip():
            parts.append("--- stdout ---\n" + self.stdout_tail.strip())
        return "\n".join(parts) or f"gate exited {self.exit_code} with no output"


def run_gate(
    workdir: Path,
    script: str = ".harness/gate.sh",
    timeout: int = 180,
    tail_bytes: int = DEFAULT_TAIL_BYTES,
) -> GateResult:
    """Execute the gate script under ``workdir`` and capture output.

    Returns a :class:`GateResult`. The output tails are truncated to
    ``tail_bytes`` each — the raw output is otherwise unbounded and
    would blow up the next-round prompt.
    """
    script_path = workdir / script
    if not script_path.exists():
        raise FileNotFoundError(f"gate script not found: {script_path}")
    if not script_path.is_file():
        raise ValueError(f"gate script is not a regular file: {script_path}")

    try:
        completed = subprocess.run(
            ["bash", str(script_path)],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        return GateResult(
            passed=False,
            exit_code=124,
            stderr_tail=_tail(stderr, tail_bytes)
            + f"\n[gate timed out after {timeout}s]",
            stdout_tail=_tail(stdout, tail_bytes),
        )

    return GateResult(
        passed=completed.returncode == 0,
        exit_code=completed.returncode,
        stderr_tail=_tail(completed.stderr, tail_bytes),
        stdout_tail=_tail(completed.stdout, tail_bytes),
    )


def _tail(text: Optional[str], n: int) -> str:
    if not text:
        return ""
    if len(text) <= n:
        return text
    return "…\n" + text[-n:]


__all__ = ["GateResult", "run_gate"]
