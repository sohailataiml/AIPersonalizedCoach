#!/usr/bin/env python
"""Run the offline evaluation suite.

    python scripts/run_evals.py                # run, print, save artifact
    python scripts/run_evals.py --no-save      # run and print only
    python scripts/run_evals.py --json         # machine-readable, for CI
    python scripts/run_evals.py --category safety

Exit code is 0 only when every case passed and no unsafe exercise survived
final validation, so this is usable as a CI gate.

Offline evaluation answers "does the system behave correctly across known
scenarios?". Runtime tracing answers "what happened during this request?". They
are deliberately separate; this script is the former.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.api.deps import build_services  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.domain.evaluation import CASE_CATEGORY_LABEL, EvaluationRun  # noqa: E402
from app.evaluation.artifacts import EvaluationArtifactStore  # noqa: E402
from app.evaluation.cases import ALL_CASES  # noqa: E402
from app.evaluation.runner import EvaluationRunner  # noqa: E402

BAR_WIDTH = 24


def _bar(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return " " * BAR_WIDTH
    filled = round(BAR_WIDTH * numerator / denominator)
    return "#" * filled + "." * (BAR_WIDTH - filled)


def render(run: EvaluationRun) -> str:
    lines = [
        "",
        "FUTURE COACH EVALUATION",
        "-" * 62,
        f"run        : {run.run_id}",
        f"backend    : graph.{run.graph_backend}  llm.{run.llm_provider}",
        f"cases      : {run.total_cases}  ({run.passed_cases} passed, "
        f"{run.failed_cases} failed)",
        "",
    ]

    for metric in run.metrics:
        if metric.denominator == 0:
            continue
        percent = "  n/a" if metric.value is None else f"{metric.value * 100:5.1f}%"
        lines.append(
            f"  {metric.label:<28} {metric.numerator:>3} / {metric.denominator:<3} "
            f"{_bar(metric.numerator, metric.denominator)} {percent}"
        )

    lines += [
        "",
        f"  {'Unsafe validation escapes':<28} {run.unsafe_escapes:>3}"
        f"        {'<-- MUST BE ZERO' if run.unsafe_escapes else ''}",
        "",
        f"latency    : p50 {run.latency.p50_ms} ms | p95 {run.latency.p95_ms} ms "
        f"| max {run.latency.max_ms} ms",
        f"duration   : {run.duration_ms} ms",
        "",
        "SAFETY INVARIANTS",
        "-" * 62,
    ]

    for invariant in run.invariants:
        mark = "PASS" if invariant.holds else "FAIL"
        lines.append(f"  [{mark}] {invariant.statement}")
        if not invariant.holds:
            detail = invariant.detail or f"failing cases: {', '.join(invariant.failed_by)}"
            lines.append(f"         {detail}")

    failures = [r for r in run.results if not r.passed]
    if failures:
        lines += ["", "FAILING CASES", "-" * 62]
        for result in failures:
            lines.append(
                f"  {CASE_CATEGORY_LABEL[result.category]} / {result.case_id}"
            )
            lines.append(f"    expected : {result.expected}")
            lines.append(f"    actual   : {result.actual}")

    lines += ["", f"Overall: {run.status.upper()}", ""]
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the run as JSON")
    parser.add_argument("--no-save", action="store_true", help="do not write an artifact")
    parser.add_argument(
        "--category", action="append", help="restrict to one or more categories"
    )
    args = parser.parse_args()

    cases = ALL_CASES
    if args.category:
        wanted = set(args.category)
        cases = [c for c in ALL_CASES if c.category in wanted]
        if not cases:
            print(f"No cases match {sorted(wanted)}", file=sys.stderr)
            return 2

    services = build_services(get_settings())
    try:
        run = await EvaluationRunner(services).run(cases)
    finally:
        services.close()

    if not args.no_save:
        path = EvaluationArtifactStore().save(run)
        if not args.json:
            print(f"\nartifact   : {path.relative_to(REPO_ROOT)}")

    if args.json:
        print(json.dumps(run.model_dump(mode="json"), indent=2))
    else:
        print(render(run))

    return 0 if run.status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
