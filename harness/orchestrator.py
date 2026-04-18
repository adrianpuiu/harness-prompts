"""The outer loop of the harness.

The orchestrator drives rounds of CODER → GATE → REVIEWER → DIGEST
until one of three things happens:

1. The reviewer returns zero blocker/major findings — PASS.
2. The round budget is exhausted — MAX_CYCLES.
3. A preflight check fails — we abort with an explanatory message.

The orchestrator itself never edits project code. It only reads/writes
``.harness/`` via :class:`HarnessState`.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from harness import git_utils, prompts
from harness.agent import Agent, AgentError
from harness.gate import GateResult, run_gate
from harness.state import HarnessState
from harness.tools import reader_toolset, writer_toolset

log = logging.getLogger(__name__)


# --- data types ------------------------------------------------------------


@dataclass
class ReviewFinding:
    severity: str
    category: str
    problem: str
    suggested_fix: str
    file: Optional[str] = None
    line_range: Optional[List[int]] = None

    @classmethod
    def from_dict(cls, d: dict) -> "ReviewFinding":
        return cls(
            severity=str(d.get("severity", "")).lower(),
            category=str(d.get("category", "")),
            problem=str(d.get("problem", "")),
            suggested_fix=str(d.get("suggested_fix", "")),
            file=d.get("file"),
            line_range=d.get("line_range"),
        )


@dataclass
class RoundRecord:
    index: int
    coder_approach: str = ""
    gate_passed: bool = False
    gate_feedback: str = ""
    review_summary: str = ""
    review_findings: List[ReviewFinding] = field(default_factory=list)

    @property
    def blocker_or_major(self) -> List[ReviewFinding]:
        return [
            f for f in self.review_findings if f.severity in {"blocker", "major"}
        ]

    @property
    def short(self) -> str:
        gate = "PASS" if self.gate_passed else "FAIL"
        if not self.gate_passed:
            return f"R{self.index}: gate={gate}"
        n = len(self.blocker_or_major)
        if n == 0:
            return f"R{self.index}: gate=PASS review=CLEAN"
        return f"R{self.index}: gate=PASS review={n}_blockers"


@dataclass
class HarnessResult:
    status: str  # "PASS" | "MAX_CYCLES" | "ABORTED"
    rounds: List[RoundRecord] = field(default_factory=list)
    final_summary: str = ""
    diff_stat: str = ""
    base_sha: str = ""

    @property
    def rounds_used(self) -> int:
        return len(self.rounds)


# --- config ----------------------------------------------------------------


@dataclass
class HarnessConfig:
    workdir: Path
    instruction: str
    max_rounds: int = 4
    coder_model: str = "claude-sonnet-4-6"
    reviewer_model: str = "claude-sonnet-4-6"
    digest_model: str = "claude-haiku-4-5-20251001"
    gate_script: str = ".harness/gate.sh"
    gate_timeout: int = 180
    require_clean_tree: bool = True
    allow_unsatisfiable_gate: bool = False


# --- main loop -------------------------------------------------------------


class Harness:
    def __init__(self, config: HarnessConfig) -> None:
        self.cfg = config
        self.state = HarnessState(root=config.workdir)

    # ---------- preflight --------------------------------------------

    def preflight(self) -> None:
        git_utils.ensure_repo(self.cfg.workdir)
        if self.cfg.require_clean_tree and not git_utils.is_clean(self.cfg.workdir):
            raise RuntimeError(
                "working tree is dirty — commit or stash first, or pass "
                "--allow-dirty to override."
            )
        self.state.init()
        # Drive the gate once to catch config problems early.
        try:
            pre = run_gate(
                self.cfg.workdir,
                script=self.cfg.gate_script,
                timeout=self.cfg.gate_timeout,
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"gate script not found: {self.cfg.gate_script} — create it "
                "before running the harness."
            )
        if not pre.passed and not self.cfg.allow_unsatisfiable_gate:
            raise RuntimeError(
                "preflight gate failed BEFORE any edits — refusing to burn "
                "rounds on an unsatisfiable gate. Re-run with "
                "allow_unsatisfiable_gate=True to override.\n\n"
                f"gate stderr:\n{pre.stderr_tail}"
            )

    # ---------- run ---------------------------------------------------

    def run(self) -> HarnessResult:
        self.preflight()
        base_sha = git_utils.head_sha(self.cfg.workdir)
        result = HarnessResult(status="MAX_CYCLES", base_sha=base_sha)

        last_feedback: str = "none"
        rounds_remaining = self.cfg.max_rounds

        for k in range(1, self.cfg.max_rounds + 1):
            record = RoundRecord(index=k)
            result.rounds.append(record)
            rounds_remaining = self.cfg.max_rounds - k

            self.state.write_round_ref(git_utils.head_sha(self.cfg.workdir))

            # --- CODER -----------------------------------------------
            coder_out = self._run_coder(last_feedback, k, rounds_remaining)
            record.coder_approach = _extract_section(coder_out, "APPROACH")

            # --- GATE ------------------------------------------------
            gate = run_gate(
                self.cfg.workdir,
                script=self.cfg.gate_script,
                timeout=self.cfg.gate_timeout,
            )
            record.gate_passed = gate.passed
            record.gate_feedback = gate.feedback

            if not gate.passed:
                self.state.write_gate_failure(gate.feedback)
                last_feedback = _pack_gate_feedback(gate)
                self._run_digest(record, last_feedback, k)
                continue

            # --- REVIEWER --------------------------------------------
            review = self._run_reviewer(k)
            record.review_summary = review.get("summary", "")
            record.review_findings = [
                ReviewFinding.from_dict(f) for f in review.get("findings", [])
            ]
            self.state.write_review(json.dumps(review, indent=2))

            if not record.blocker_or_major:
                result.status = "PASS"
                result.final_summary = record.review_summary
                break

            last_feedback = _pack_review_feedback(record.blocker_or_major)
            self._run_digest(record, last_feedback, k)

        # summary diff
        try:
            result.diff_stat = git_utils.diff_stat(self.cfg.workdir, base_sha)
        except git_utils.GitError:
            result.diff_stat = "(diff unavailable)"

        return result

    # ---------- subagent calls ---------------------------------------

    def _run_coder(self, last_feedback: str, k: int, rounds_remaining: int) -> str:
        agent = Agent(
            system_prompt=prompts.CODER,
            toolset=writer_toolset(self.cfg.workdir),
            model=self.cfg.coder_model,
        )
        user = _format_coder_prompt(
            instruction=self.cfg.instruction,
            last_feedback=last_feedback,
            digest=self.state.read_digest(),
            round_index=k,
            rounds_remaining=rounds_remaining,
            workdir=self.cfg.workdir,
        )
        result = agent.run(user)
        log.info("coder round %d: %d turns, %d out tokens", k, result.turns, result.output_tokens)
        return result.text

    def _run_reviewer(self, k: int) -> dict:
        base = self.state.read_round_ref() or ""
        diff_text = git_utils.diff(self.cfg.workdir, base)
        files = git_utils.changed_files(self.cfg.workdir, base)
        agent = Agent(
            system_prompt=prompts.REVIEWER,
            toolset=reader_toolset(self.cfg.workdir),
            model=self.cfg.reviewer_model,
        )
        user = _format_reviewer_prompt(
            instruction=self.cfg.instruction,
            diff=diff_text,
            changed_files=files,
        )
        result = agent.run(user)
        return _parse_reviewer_json(result.text)

    def _run_digest(self, record: RoundRecord, last_feedback: str, k: int) -> None:
        # Digest uses no tools at all; it writes prose.
        from harness.tools import Toolset  # local import to avoid a cycle
        empty = Toolset(schemas=[], handlers={})
        agent = Agent(
            system_prompt=prompts.DIGEST,
            toolset=empty,
            model=self.cfg.digest_model,
        )
        user = _format_digest_prompt(
            prior_digest=self.state.read_digest(),
            latest_approach=record.coder_approach,
            latest_outcome=last_feedback,
            round_index=k,
            max_rounds=self.cfg.max_rounds,
        )
        try:
            result = agent.run(user)
        except AgentError as exc:
            log.warning("digest agent failed: %s", exc)
            return
        self.state.write_digest(result.text)


# --- prompt formatting -----------------------------------------------------


def _format_coder_prompt(
    *,
    instruction: str,
    last_feedback: str,
    digest: str,
    round_index: int,
    rounds_remaining: int,
    workdir: Path,
) -> str:
    return (
        f"instruction:\n{instruction}\n\n"
        f"last_feedback:\n{last_feedback}\n\n"
        f"digest:\n{digest or '(empty)'}\n\n"
        f"round_index: {round_index}\n"
        f"rounds_remaining: {rounds_remaining}\n"
        f"workdir: {workdir}\n\n"
        "Make the edits now using read_file / write_file / edit_file / "
        "grep / glob, then emit the APPROACH / CHANGED / NOTES block as "
        "your final message."
    )


def _format_reviewer_prompt(
    *, instruction: str, diff: str, changed_files: List[str]
) -> str:
    files_block = "\n".join(f"- {f}" for f in changed_files) or "(none)"
    return (
        f"instruction:\n{instruction}\n\n"
        f"changed_files:\n{files_block}\n\n"
        f"diff:\n```diff\n{diff}\n```\n\n"
        "Use read_file on every changed file before filing findings. "
        "Emit the JSON findings object as your final message."
    )


def _format_digest_prompt(
    *,
    prior_digest: str,
    latest_approach: str,
    latest_outcome: str,
    round_index: int,
    max_rounds: int,
) -> str:
    return (
        f"prior_digest:\n{prior_digest or '(empty)'}\n\n"
        f"latest_approach:\n{latest_approach or '(none)'}\n\n"
        f"latest_outcome:\n{latest_outcome}\n\n"
        f"round_index: {round_index}\nmax_rounds: {max_rounds}"
    )


# --- feedback packing -------------------------------------------------------


def _pack_gate_feedback(gate: GateResult) -> str:
    return "gate_failure:\n" + gate.feedback


def _pack_review_feedback(findings: List[ReviewFinding]) -> str:
    payload = [
        {
            "severity": f.severity,
            "category": f.category,
            "file": f.file,
            "line_range": f.line_range,
            "problem": f.problem,
            "suggested_fix": f.suggested_fix,
        }
        for f in findings
    ]
    return "review_findings:\n" + json.dumps(payload, indent=2)


# --- parsing ---------------------------------------------------------------


_SECTION_RE = re.compile(
    r"^(?P<name>APPROACH|CHANGED|NOTES)\s*\n(?P<body>.*?)(?=\n(?:APPROACH|CHANGED|NOTES)\s*\n|\Z)",
    re.DOTALL | re.MULTILINE,
)


def _extract_section(text: str, name: str) -> str:
    for m in _SECTION_RE.finditer(text):
        if m.group("name") == name:
            return m.group("body").strip()
    return ""


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(?P<body>\{.*?\})\s*```", re.DOTALL)


def _parse_reviewer_json(text: str) -> dict:
    """Parse reviewer output, tolerating a stray markdown fence."""
    candidate = text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    fence = _JSON_FENCE_RE.search(candidate)
    if fence:
        try:
            return json.loads(fence.group("body"))
        except json.JSONDecodeError:
            pass
    # synthetic blocker so the orchestrator can continue
    return {
        "summary": "reviewer output was not parseable JSON",
        "findings": [
            {
                "severity": "blocker",
                "category": "architecture",
                "problem": "reviewer emitted non-JSON output",
                "suggested_fix": "re-emit a single valid JSON object matching the schema",
                "file": None,
                "line_range": None,
            }
        ],
    }


__all__ = [
    "Harness",
    "HarnessConfig",
    "HarnessResult",
    "ReviewFinding",
    "RoundRecord",
]
