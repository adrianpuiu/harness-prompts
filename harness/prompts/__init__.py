"""Agent system prompts, loaded from markdown siblings."""

from __future__ import annotations

from pathlib import Path

_HERE = Path(__file__).parent


def load(name: str) -> str:
    """Return the system prompt stored at ``{name}.md``."""
    path = _HERE / f"{name}.md"
    return path.read_text(encoding="utf-8")


CODER = load("coder")
REVIEWER = load("reviewer")
DIGEST = load("digest")

__all__ = ["CODER", "REVIEWER", "DIGEST", "load"]
