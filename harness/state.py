"""Filesystem-backed state for the harness loop.

Everything in ``.harness/`` is owned by the orchestrator. Nothing else
should touch these files — the coder and reviewer agents operate on
the project's working tree, not on the harness's memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class HarnessState:
    root: Path  # the project root, i.e. where ``.harness/`` lives

    @property
    def dir(self) -> Path:
        return self.root / ".harness"

    @property
    def digest_path(self) -> Path:
        return self.dir / "digest.txt"

    @property
    def round_ref_path(self) -> Path:
        return self.dir / "round_ref"

    @property
    def last_gate_fail_path(self) -> Path:
        return self.dir / "last_gate_fail.txt"

    @property
    def last_review_path(self) -> Path:
        return self.dir / "last_review.json"

    # --- lifecycle -----------------------------------------------------

    def init(self) -> None:
        """Create ``.harness/`` and initialise empty state files."""
        self.dir.mkdir(parents=True, exist_ok=True)
        if not self.digest_path.exists():
            self.digest_path.write_text("", encoding="utf-8")

    def reset(self) -> None:
        """Delete all state files inside ``.harness/``."""
        if not self.dir.exists():
            return
        for child in self.dir.iterdir():
            if child.is_file():
                child.unlink()

    # --- digest --------------------------------------------------------

    def read_digest(self) -> str:
        if not self.digest_path.exists():
            return ""
        return self.digest_path.read_text(encoding="utf-8").strip()

    def write_digest(self, text: str) -> None:
        self.digest_path.write_text(text.strip() + "\n", encoding="utf-8")

    # --- round ref -----------------------------------------------------

    def write_round_ref(self, sha: str) -> None:
        self.round_ref_path.write_text(sha.strip() + "\n", encoding="utf-8")

    def read_round_ref(self) -> Optional[str]:
        if not self.round_ref_path.exists():
            return None
        data = self.round_ref_path.read_text(encoding="utf-8").strip()
        return data or None

    # --- feedback ------------------------------------------------------

    def write_gate_failure(self, text: str) -> None:
        self.last_gate_fail_path.write_text(text, encoding="utf-8")

    def write_review(self, text: str) -> None:
        self.last_review_path.write_text(text, encoding="utf-8")


__all__ = ["HarnessState"]
