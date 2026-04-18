"""Command line entry point: ``python -m harness "<task description>"``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

from harness.orchestrator import Harness, HarnessConfig, HarnessResult


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m harness",
        description="Bounded coder ⇄ reviewer loop with a pluggable gate.",
    )
    p.add_argument("instruction", help="The coding task to perform.")
    p.add_argument(
        "--workdir",
        type=Path,
        default=Path.cwd(),
        help="Project root (default: cwd). Must be a git repo.",
    )
    p.add_argument("--max-rounds", type=int, default=4)
    p.add_argument("--gate-script", default=".harness/gate.sh")
    p.add_argument("--gate-timeout", type=int, default=180)
    p.add_argument("--coder-model", default="claude-sonnet-4-6")
    p.add_argument("--reviewer-model", default="claude-sonnet-4-6")
    p.add_argument("--digest-model", default="claude-haiku-4-5-20251001")
    p.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Skip the clean-tree preflight check.",
    )
    p.add_argument(
        "--allow-unsatisfiable-gate",
        action="store_true",
        help="Proceed even if the preflight gate fails.",
    )
    p.add_argument(
        "--verbose", "-v", action="count", default=0, help="Increase logging."
    )
    return p.parse_args(argv)


def _setup_logging(verbose: int) -> None:
    level = logging.WARNING
    if verbose == 1:
        level = logging.INFO
    elif verbose >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    _setup_logging(args.verbose)

    config = HarnessConfig(
        workdir=args.workdir.resolve(),
        instruction=args.instruction,
        max_rounds=args.max_rounds,
        gate_script=args.gate_script,
        gate_timeout=args.gate_timeout,
        coder_model=args.coder_model,
        reviewer_model=args.reviewer_model,
        digest_model=args.digest_model,
        require_clean_tree=not args.allow_dirty,
        allow_unsatisfiable_gate=args.allow_unsatisfiable_gate,
    )

    try:
        result = Harness(config).run()
    except RuntimeError as exc:
        print(f"harness: aborted — {exc}", file=sys.stderr)
        return 2

    _print_summary(result, config)
    return 0 if result.status == "PASS" else 1


def _print_summary(result: HarnessResult, config: HarnessConfig) -> None:
    confidence = _confidence(result, config.max_rounds)
    lines = [
        "=== HARNESS COMPLETE ===",
        f"Status:       {result.status}",
        f"Rounds used:  {result.rounds_used}/{config.max_rounds}",
        f"Confidence:   {confidence}",
        "",
        "Rounds:",
    ]
    for r in result.rounds:
        lines.append(f"  {r.short}")
    lines.extend(
        [
            "",
            "Final diff (summary):",
            result.diff_stat.rstrip() or "(no changes)",
        ]
    )
    if result.final_summary:
        lines.extend(["", f"Reviewer summary: {result.final_summary}"])
    print("\n".join(lines))


def _confidence(result: HarnessResult, max_rounds: int) -> str:
    if result.status == "MAX_CYCLES":
        return "low"
    if result.status != "PASS":
        return "low"
    if result.rounds_used <= max(1, max_rounds // 2):
        return "high"
    return "medium"


__all__ = ["main"]
