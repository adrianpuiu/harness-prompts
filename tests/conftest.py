"""Shared pytest fixtures."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterator

import pytest


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Iterator[Path]:
    """Initialise a small git repo in ``tmp_path`` and yield its root."""
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(tmp_path)], check=True
    )
    # Local identity so `git commit` works under CI sandboxes.
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "t@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True
    )
    (tmp_path / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "-A"], check=True
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "seed"], check=True
    )
    yield tmp_path
    shutil.rmtree(tmp_path, ignore_errors=True)
