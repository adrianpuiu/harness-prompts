"""Tests for the gate runner."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.gate import run_gate


def _make_gate(tmp_path: Path, body: str) -> None:
    script = tmp_path / ".harness" / "gate.sh"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    script.chmod(0o755)


def test_gate_passes(tmp_path: Path) -> None:
    _make_gate(tmp_path, "exit 0\n")
    result = run_gate(tmp_path)
    assert result.passed is True
    assert result.exit_code == 0


def test_gate_fails_and_captures_stderr(tmp_path: Path) -> None:
    _make_gate(tmp_path, "echo some error 1>&2\nexit 7\n")
    result = run_gate(tmp_path)
    assert result.passed is False
    assert result.exit_code == 7
    assert "some error" in result.stderr_tail


def test_gate_tail_truncates(tmp_path: Path) -> None:
    _make_gate(
        tmp_path,
        "python3 -c 'import sys; sys.stderr.write(\"x\" * 20000)'\nexit 1\n",
    )
    result = run_gate(tmp_path, tail_bytes=500)
    assert result.passed is False
    assert len(result.stderr_tail) <= 520  # 500 + ellipsis/newline slack


def test_gate_missing_script(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_gate(tmp_path)


def test_gate_timeout(tmp_path: Path) -> None:
    _make_gate(tmp_path, "sleep 5\n")
    result = run_gate(tmp_path, timeout=1)
    assert result.passed is False
    assert result.exit_code == 124
    assert "timed out" in result.stderr_tail


def test_gate_feedback_property(tmp_path: Path) -> None:
    _make_gate(tmp_path, "echo on_stdout\necho on_stderr 1>&2\nexit 3\n")
    result = run_gate(tmp_path)
    assert "on_stderr" in result.feedback
    assert "on_stdout" in result.feedback
