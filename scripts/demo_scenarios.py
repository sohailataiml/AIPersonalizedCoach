#!/usr/bin/env python
"""Run the three assessment demo scenarios end to end and assert the outcomes.

    python scripts/demo_scenarios.py

This is executable documentation: it drives the real workflow (resolver ->
graph traversal -> safety -> LLM composition -> post-generation gate) and fails
loudly if any scenario stops behaving as documented in the README.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.api.deps import build_services  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.domain.workout import WorkoutRequest  # noqa: E402

MEMBER_ID = "mbr_01HX9JORDAN"

SCENARIOS = [
    {
        "name": "Scenario 1 - Injury",
        "prompt": (
            "Create a 45-minute lower-body workout. Her left knee is bothering her."
        ),
        "duration": 45,
        "expect_excluded": ["Static Jump", "Vertical Jump to Broad Jump"],
        "expect_reason": "injury_contraindicated_pattern",
        "expect_resolved": "anatomy:knee",
    },
    {
        "name": "Scenario 2 - Limited equipment",
        "prompt": (
            "Build a full-body workout. She has no barbell, only dumbbells and a kettlebell."
        ),
        "duration": 45,
        "expect_excluded": [
            "Barbell Decline Bench Press",
            "Barbell Racked Forward Lunge",
            "Machine - Chest-Supported Row",
        ],
        "expect_reason": None,
        "expect_resolved": "equipment:dumbbell",
    },
    {
        "name": "Scenario 3 - Explicit exclusion",
        "prompt": "Create a lower-body workout but exclude deadlifts.",
        "duration": 45,
        # No exercise in the catalog is named "deadlift" - these are removed
        # because the phrase resolves to the hinge movement family.
        "expect_excluded": [
            "One-Kettlebell Hamstring Walkout",
            "Med Ball Hamstring Walkout",
        ],
        "expect_reason": "explicit_exclusion",
        "expect_resolved": "movement_family:hinge",
    },
]


def _report_longitudinal_context(services) -> list[str]:
    """Print the deterministic trajectory, and assert what the data supports.

    Printed once rather than per scenario because it describes the *member*,
    not the request. The assertions here are as much about restraint as
    accuracy: sleep must read flat (the nights do not trend down) and the
    injury trajectory must be the recorded status, never something derived
    from falling adherence.
    """
    member = services.repository.get_member_context(MEMBER_ID)
    trajectory = services.trajectory.analyze(member)
    problems: list[str] = []

    print("=" * 78)
    print("Longitudinal context (deterministic, personalization only)")
    for fact in trajectory.summary_facts():
        print(f"  {fact}")
    print(
        f"  bias: volume={trajectory.bias.volume_bias} "
        f"novelty={trajectory.bias.novelty_bias} "
        f"familiar={', '.join(trajectory.bias.familiar_movement_families)}"
    )
    print()

    if trajectory.adherence.direction != "declining":
        problems.append("longitudinal: adherence should read declining")
    if trajectory.sleep.direction != "flat":
        problems.append("longitudinal: sleep should read flat - the nights do not trend down")
    if trajectory.progression.state != "hold":
        problems.append("longitudinal: progression should be hold")
    if trajectory.injury_trajectory.source != "recorded_status":
        problems.append("longitudinal: injury trajectory must come from the recorded status")
    return problems


async def run() -> int:
    settings = get_settings()
    services = build_services(settings)
    failures: list[str] = []

    print(f"graph backend : {services.backend}")
    print(f"llm provider  : {getattr(services.llm, 'name', 'unknown')}\n")

    failures.extend(_report_longitudinal_context(services))

    for scenario in SCENARIOS:
        print("=" * 78)
        print(scenario["name"])
        print(f'  prompt: "{scenario["prompt"]}"')

        state = await services.workflow.run(
            WorkoutRequest(
                member_id=MEMBER_ID,
                prompt=scenario["prompt"],
                duration_minutes=scenario["duration"],
            )
        )

        workout = state["generated_workout"]
        provenance = state["provenance"]
        report = state["post_validation"]
        decisions = state["safety_decisions"]

        resolved_ids = {c.canonical_id for c in provenance.resolved_concepts}
        by_name = {d.exercise_name: d for d in decisions.values()}

        print(f"\n  {workout.title}")
        for section in workout.sections:
            names = ", ".join(e.name for e in section.exercises)
            print(f"    {section.name:9s} {names}")

        print(
            f"\n  eligible={provenance.counts['eligible']} "
            f"excluded={provenance.counts['excluded']} "
            f"downranked={provenance.counts['downranked']} "
            f"in_plan={provenance.counts['in_plan']}"
        )
        print(
            "  resolved: "
            + ", ".join(
                f"{c.source_text!r}->{c.canonical_id}({c.method})"
                for c in provenance.resolved_concepts
            )
        )

        # --- assertions ---
        if scenario["expect_resolved"] not in resolved_ids:
            failures.append(
                f"{scenario['name']}: expected to resolve {scenario['expect_resolved']}, "
                f"got {sorted(x for x in resolved_ids if x)}"
            )

        for name in scenario["expect_excluded"]:
            decision = by_name.get(name)
            if decision is None:
                failures.append(f"{scenario['name']}: '{name}' missing from catalog")
            elif not decision.is_excluded:
                failures.append(
                    f"{scenario['name']}: expected '{name}' excluded, got {decision.status}"
                )
            elif scenario["expect_reason"] and scenario["expect_reason"] not in {
                r.rule_id for r in decision.reasons
            }:
                failures.append(
                    f"{scenario['name']}: '{name}' excluded but not by "
                    f"{scenario['expect_reason']}"
                )

        if not report.passed:
            failures.append(f"{scenario['name']}: post-validation did not pass cleanly")
        if provenance.counts["in_plan"] == 0:
            failures.append(f"{scenario['name']}: produced an empty plan")

        example = next(
            (item for item in provenance.filtered if item.evidence), None
        )
        if example:
            print(f"\n  provenance sample - {example.exercise} [{example.decision}]")
            print(f"    {example.reasons[0]}")
            for evidence in example.evidence[:2]:
                print(f"    {evidence.rendered}")
        print()

    services.close()

    print("=" * 78)
    if failures:
        print("FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("All three demo scenarios behaved as documented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
