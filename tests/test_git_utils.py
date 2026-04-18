"""Tests for the git wrappers."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from harness import git_utils


def test_ensure_repo_passes(tmp_repo: Path) -> None:
    git_utils.ensure_repo(tmp_repo)


def test_ensure_repo_fails_outside(tmp_path: Path) -> None:
    with pytest.raises(git_utils.GitError):
        git_utils.ensure_repo(tmp_path)


def test_is_clean_true_on_seed(tmp_repo: Path) -> None:
    assert git_utils.is_clean(tmp_repo) is True


def test_is_clean_false_after_edit(tmp_repo: Path) -> None:
    (tmp_repo / "README.md").write_text("dirty\n", encoding="utf-8")
    assert git_utils.is_clean(tmp_repo) is False


def test_head_sha_is_40_chars(tmp_repo: Path) -> None:
    sha = git_utils.head_sha(tmp_repo)
    assert len(sha) == 40
    assert all(c in "0123456789abcdef" for c in sha)


def test_diff_and_changed_files(tmp_repo: Path) -> None:
    base = git_utils.head_sha(tmp_repo)
    (tmp_repo / "new.txt").write_text("hi\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_repo), "add", "-A"], check=True
    )
    subprocess.run(
        ["git", "-C", str(tmp_repo), "commit", "-q", "-m", "add new"],
        check=True,
    )
    files = git_utils.changed_files(tmp_repo, base)
    assert files == ["new.txt"]
    diff = git_utils.diff(tmp_repo, base)
    assert "new.txt" in diff
    stat = git_utils.diff_stat(tmp_repo, base)
    assert "new.txt" in stat
