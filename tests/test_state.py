"""Tests for the .harness/ state manager."""

from __future__ import annotations

from pathlib import Path

from harness.state import HarnessState


def test_init_creates_dir_and_digest(tmp_path: Path) -> None:
    s = HarnessState(root=tmp_path)
    s.init()
    assert (tmp_path / ".harness").is_dir()
    assert s.digest_path.exists()
    assert s.read_digest() == ""


def test_digest_roundtrip(tmp_path: Path) -> None:
    s = HarnessState(root=tmp_path)
    s.init()
    s.write_digest("R1: tried x\nR2: tried y")
    assert s.read_digest() == "R1: tried x\nR2: tried y"


def test_digest_trims_whitespace(tmp_path: Path) -> None:
    s = HarnessState(root=tmp_path)
    s.init()
    s.write_digest("   hello\n\n")
    assert s.read_digest() == "hello"


def test_round_ref_roundtrip(tmp_path: Path) -> None:
    s = HarnessState(root=tmp_path)
    s.init()
    assert s.read_round_ref() is None
    s.write_round_ref("abc123")
    assert s.read_round_ref() == "abc123"


def test_reset_clears_files(tmp_path: Path) -> None:
    s = HarnessState(root=tmp_path)
    s.init()
    s.write_round_ref("deadbeef")
    s.write_gate_failure("oops")
    s.reset()
    assert not s.round_ref_path.exists()
    assert not s.last_gate_fail_path.exists()
    assert s.dir.exists()


def test_reset_is_safe_on_empty(tmp_path: Path) -> None:
    s = HarnessState(root=tmp_path)
    s.reset()  # no .harness dir yet — must not raise
    assert not s.dir.exists()
