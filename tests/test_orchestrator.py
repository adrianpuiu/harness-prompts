"""Tests for orchestrator plumbing that does not require the Anthropic API."""

from __future__ import annotations

import json

from harness.gate import GateResult
from harness.orchestrator import (
    RoundRecord,
    ReviewFinding,
    _extract_section,
    _pack_gate_feedback,
    _pack_review_feedback,
    _parse_reviewer_json,
)


def test_extract_approach_section() -> None:
    text = (
        "APPROACH\nUsed a single regex pass.\n\n"
        "CHANGED\nfoo.py — new regex\n\n"
        "NOTES\nNone.\n"
    )
    assert _extract_section(text, "APPROACH") == "Used a single regex pass."
    assert _extract_section(text, "CHANGED") == "foo.py — new regex"
    assert _extract_section(text, "NOTES") == "None."


def test_extract_missing_section_returns_empty() -> None:
    text = "APPROACH\ndone.\n"
    assert _extract_section(text, "NOTES") == ""


def test_parse_reviewer_plain_json() -> None:
    raw = json.dumps({"summary": "ok", "findings": []})
    parsed = _parse_reviewer_json(raw)
    assert parsed == {"summary": "ok", "findings": []}


def test_parse_reviewer_json_in_markdown_fence() -> None:
    raw = "```json\n" + json.dumps({"summary": "ok", "findings": []}) + "\n```"
    parsed = _parse_reviewer_json(raw)
    assert parsed["summary"] == "ok"


def test_parse_reviewer_non_json_synthesises_blocker() -> None:
    parsed = _parse_reviewer_json("nope, no json here")
    assert len(parsed["findings"]) == 1
    assert parsed["findings"][0]["severity"] == "blocker"


def test_pack_gate_feedback_prefixes_label() -> None:
    gate = GateResult(
        passed=False, exit_code=1, stderr_tail="boom", stdout_tail=""
    )
    out = _pack_gate_feedback(gate)
    assert out.startswith("gate_failure:")
    assert "boom" in out


def test_pack_review_feedback_includes_severity() -> None:
    findings = [
        ReviewFinding(
            severity="blocker",
            category="correctness",
            problem="oops",
            suggested_fix="fix it",
            file="a.py",
            line_range=[1, 2],
        )
    ]
    out = _pack_review_feedback(findings)
    assert out.startswith("review_findings:")
    parsed = json.loads(out.split("review_findings:", 1)[1])
    assert parsed[0]["severity"] == "blocker"
    assert parsed[0]["file"] == "a.py"


def test_round_record_short_labels() -> None:
    r = RoundRecord(index=1, gate_passed=False)
    assert "gate=FAIL" in r.short
    r2 = RoundRecord(index=2, gate_passed=True)
    assert "review=CLEAN" in r2.short
    r3 = RoundRecord(
        index=3,
        gate_passed=True,
        review_findings=[
            ReviewFinding(
                severity="blocker",
                category="correctness",
                problem="x",
                suggested_fix="y",
            )
        ],
    )
    assert "review=1_blockers" in r3.short
