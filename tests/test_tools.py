"""Tests for the filesystem tool implementations."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.tools import (
    edit_file,
    glob_tool,
    grep,
    read_file,
    reader_toolset,
    write_file,
    writer_toolset,
)


def test_write_and_read_roundtrip(tmp_path: Path) -> None:
    write_file(tmp_path, "a.txt", "hello")
    assert read_file(tmp_path, "a.txt") == "hello"


def test_write_creates_parent_dirs(tmp_path: Path) -> None:
    write_file(tmp_path, "pkg/sub/inner.py", "print('hi')\n")
    assert (tmp_path / "pkg" / "sub" / "inner.py").exists()


def test_edit_requires_unique_match(tmp_path: Path) -> None:
    write_file(tmp_path, "f.txt", "foo foo")
    with pytest.raises(ValueError, match="matches 2 times"):
        edit_file(tmp_path, "f.txt", "foo", "bar")


def test_edit_replace_all(tmp_path: Path) -> None:
    write_file(tmp_path, "f.txt", "foo foo foo")
    msg = edit_file(tmp_path, "f.txt", "foo", "bar", replace_all=True)
    assert "3 occurrences" in msg
    assert read_file(tmp_path, "f.txt") == "bar bar bar"


def test_edit_missing_string_raises(tmp_path: Path) -> None:
    write_file(tmp_path, "f.txt", "hello")
    with pytest.raises(ValueError, match="not found"):
        edit_file(tmp_path, "f.txt", "world", "earth")


def test_edit_identical_strings_rejected(tmp_path: Path) -> None:
    write_file(tmp_path, "f.txt", "hello")
    with pytest.raises(ValueError, match="identical"):
        edit_file(tmp_path, "f.txt", "hello", "hello")


def test_grep_finds_matches(tmp_path: Path) -> None:
    write_file(tmp_path, "a.py", "def foo():\n    pass\n")
    write_file(tmp_path, "b.py", "def bar():\n    pass\n")
    out = grep(tmp_path, r"def \w+")
    assert "a.py:1:def foo():" in out
    assert "b.py:1:def bar():" in out


def test_grep_respects_path(tmp_path: Path) -> None:
    write_file(tmp_path, "pkg/a.py", "hit\n")
    write_file(tmp_path, "other/b.py", "hit\n")
    out = grep(tmp_path, "hit", path="pkg")
    assert "pkg/a.py" in out
    assert "other/b.py" not in out


def test_grep_invalid_regex(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid regex"):
        grep(tmp_path, "(")


def test_glob_matches_names(tmp_path: Path) -> None:
    write_file(tmp_path, "a.py", "")
    write_file(tmp_path, "b.txt", "")
    write_file(tmp_path, "sub/c.py", "")
    out = glob_tool(tmp_path, "*.py")
    assert "a.py" in out
    assert "sub/c.py" in out
    assert "b.txt" not in out


def test_glob_ignores_virtualenvs_and_git(tmp_path: Path) -> None:
    write_file(tmp_path, ".git/hidden.py", "")
    write_file(tmp_path, "real.py", "")
    out = glob_tool(tmp_path, "*.py")
    assert "real.py" in out
    assert ".git" not in out


def test_path_escape_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes workdir"):
        read_file(tmp_path, "../outside.txt")


def test_read_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_file(tmp_path, "nope.txt")


def test_read_directory_raises(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    with pytest.raises(IsADirectoryError):
        read_file(tmp_path, "sub")


def test_reader_toolset_is_read_only(tmp_path: Path) -> None:
    ts = reader_toolset(tmp_path)
    names = {s["name"] for s in ts.schemas}
    assert names == {"read_file", "grep", "glob"}


def test_writer_toolset_has_write_tools(tmp_path: Path) -> None:
    ts = writer_toolset(tmp_path)
    names = {s["name"] for s in ts.schemas}
    assert {"read_file", "grep", "glob", "write_file", "edit_file"} <= names


def test_toolset_dispatch(tmp_path: Path) -> None:
    ts = writer_toolset(tmp_path)
    ts.call("write_file", {"path": "x.txt", "content": "ok"})
    assert ts.call("read_file", {"path": "x.txt"}) == "ok"


def test_toolset_unknown_tool(tmp_path: Path) -> None:
    ts = reader_toolset(tmp_path)
    with pytest.raises(KeyError):
        ts.call("nope", {})
