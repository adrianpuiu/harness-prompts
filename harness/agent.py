"""Thin wrapper around the Anthropic Messages API that runs a tool-use loop.

The agent is instantiated with a system prompt, a model, and a
``Toolset``. Calling :meth:`Agent.run` executes the model ↔ tool loop
until the model produces a message with ``stop_reason == "end_turn"``
or no further ``tool_use`` blocks, and returns the final textual
content.

The module depends on the ``anthropic`` Python SDK at runtime but does
not import it at module import time — the rest of the package (state,
gate, git utils, tools) is useful for tests without the SDK installed.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from harness.tools import Toolset

log = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """The end-of-run result from an agent."""

    text: str
    turns: int
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)


class AgentError(RuntimeError):
    """Raised when the agent loop exceeds its budget or the API errors."""


@dataclass
class Agent:
    system_prompt: str
    toolset: Toolset
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 8192
    max_turns: int = 25
    temperature: float = 0.0
    _client: Any = None  # anthropic.Anthropic

    def _lazy_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic  # type: ignore
            except ImportError as exc:  # pragma: no cover
                raise AgentError(
                    "the 'anthropic' package is required to run agents; "
                    "install it with `pip install anthropic`"
                ) from exc
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise AgentError(
                    "ANTHROPIC_API_KEY is not set; export it or put it "
                    "in a .env file before running the harness."
                )
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    # ------------------------------------------------------------------

    def run(self, user_prompt: str) -> AgentResult:
        client = self._lazy_client()
        messages: List[Dict[str, Any]] = [
            {"role": "user", "content": user_prompt},
        ]
        total_in = total_out = 0
        tool_calls: List[Dict[str, Any]] = []

        for turn in range(1, self.max_turns + 1):
            response = client.messages.create(
                model=self.model,
                system=self.system_prompt,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                tools=self.toolset.schemas,
                messages=messages,
            )
            total_in += getattr(response.usage, "input_tokens", 0) or 0
            total_out += getattr(response.usage, "output_tokens", 0) or 0

            # Record the assistant message verbatim so the API can match
            # tool_use ids to tool_result blocks on the next turn.
            assistant_content = _blocks_to_plain(response.content)
            messages.append({"role": "assistant", "content": assistant_content})

            tool_uses = [
                b for b in assistant_content if b.get("type") == "tool_use"
            ]
            if not tool_uses:
                text = _join_text(assistant_content)
                return AgentResult(
                    text=text,
                    turns=turn,
                    input_tokens=total_in,
                    output_tokens=total_out,
                    tool_calls=tool_calls,
                )

            # Execute every tool_use in this turn and feed the results back.
            tool_results: List[Dict[str, Any]] = []
            for block in tool_uses:
                name = block["name"]
                args = block.get("input", {}) or {}
                tool_calls.append({"name": name, "input": args})
                try:
                    output = self.toolset.call(name, args)
                    is_error = False
                except Exception as exc:
                    output = f"{type(exc).__name__}: {exc}"
                    is_error = True
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": output,
                        "is_error": is_error,
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        raise AgentError(
            f"agent exceeded max_turns={self.max_turns} without finishing"
        )


# --- helpers ---------------------------------------------------------------


def _blocks_to_plain(blocks: Any) -> List[Dict[str, Any]]:
    """Normalise SDK content blocks to plain dicts.

    The SDK returns ``TextBlock`` / ``ToolUseBlock`` objects; we want
    JSON-serialisable dicts that round-trip safely when appended back
    to the message history.
    """
    plain: List[Dict[str, Any]] = []
    for b in blocks:
        t = getattr(b, "type", None) or b.get("type")
        if t == "text":
            plain.append(
                {"type": "text", "text": getattr(b, "text", None) or b.get("text", "")}
            )
        elif t == "tool_use":
            plain.append(
                {
                    "type": "tool_use",
                    "id": getattr(b, "id", None) or b.get("id"),
                    "name": getattr(b, "name", None) or b.get("name"),
                    "input": getattr(b, "input", None) or b.get("input", {}),
                }
            )
        else:
            # Fallback: include whatever repr the block has.
            try:
                plain.append(json.loads(json.dumps(b, default=lambda o: o.__dict__)))
            except Exception:
                plain.append({"type": t or "unknown", "repr": repr(b)})
    return plain


def _join_text(blocks: List[Dict[str, Any]]) -> str:
    parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    return "\n".join(p for p in parts if p).strip()


__all__ = ["Agent", "AgentError", "AgentResult"]
