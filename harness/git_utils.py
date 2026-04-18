"""Minimal git wrappers used by the orchestrator.

We shell out to git — no library dependency. All functions take a
``workdir`` (the repo root) and raise :class:`GitError` on non-zero
exit unless otherwise noted.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List


class GitError(RuntimeError):
    pass


def _run(workdir: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *argv],
        cwd=str(workdir),
        capture_output=True,
        text=True,
        check=False,
    )
    return result


def ensure_repo(workdir: Path) -> None:
    """Raise ``GitError`` if ``workdir`` is not inside a git work tree."""
    result = _run(workdir, "rev-parse", "--is-inside-work-tree")
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise GitError(f"{workdir} is not a git working tree")


def is_clean(workdir: Path) -> bool:
    result = _run(workdir, "status", "--porcelain")
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or "git status failed")
    return result.stdout.strip() == ""


def head_sha(workdir: Path) -> str:
    result = _run(workdir, "rev-parse", "HEAD")
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or "git rev-parse HEAD failed")
    return result.stdout.strip()


def diff(workdir: Path, base: str, head: str = "HEAD") -> str:
    result = _run(workdir, "diff", f"{base}..{head}")
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or "git diff failed")
    return result.stdout


def changed_files(workdir: Path, base: str, head: str = "HEAD") -> List[str]:
    result = _run(workdir, "diff", "--name-only", f"{base}..{head}")
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or "git diff --name-only failed")
    return [line for line in result.stdout.splitlines() if line.strip()]


def diff_stat(workdir: Path, base: str, head: str = "HEAD") -> str:
    result = _run(workdir, "diff", "--stat", f"{base}..{head}")
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or "git diff --stat failed")
    return result.stdout


__all__ = [
    "GitError",
    "ensure_repo",
    "is_clean",
    "head_sha",
    "diff",
    "changed_files",
    "diff_stat",
]
