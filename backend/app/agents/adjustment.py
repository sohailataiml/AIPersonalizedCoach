"""Graph-driven workout adjustment.

The load-bearing rule: **the LLM never edits the existing plan.** A coach
adjustment is not a patch instruction handed to a model — it is a new
deterministic request that runs the entire pipeline again:

    existing plan + adjustment
        -> combined coach request
        -> parse intent + resolve concepts
        -> longitudinal context
        -> deterministic SafetyEngine
        -> rank candidates
        -> LLM recomposition (from approved ids only)
        -> deterministic final validation
        -> provenance + diff

Asking a model to "remove the deadlifts from this plan" would put it in charge
of a safety decision, and it would silently keep whatever it did not notice.
Re-running instead means every adjustment re-derives exclusions from the graph,
so "avoid anything that stresses her knee" is answered by traversal rather than
by the model's reading of the sentence.

Two details are resolved here rather than left to a regex:

* **Duration.** The combined request contains the original prompt *and* the new
  instruction, so it can hold two durations ("45-minute ... make it 30
  minutes"). The adjustment wins, explicitly.
* **Baseline scores.** The diff re-runs only the deterministic half of the
  original request - no second LLM call - so score movement is measured, not
  inferred.
"""

from __future__ import annotations

import time
import uuid

from app.agents.intent import extract_duration, parse_intent
from app.domain.workout import WorkoutRequest
from app.member.trajectory import MemberTrajectoryService
from app.provenance.diff import AdjustmentDiff, build_adjustment_diff
from app.safety.ranking import rank_candidates


def combine(base_prompt: str, adjustment: str) -> str:
    """One coach request carrying the original brief and the new instruction.

    Joined with a sentence break because intent parsing is clause-scoped: the
    adjustment must be classified on its own cues, not inherit the base
    clause's. That is what keeps "only use dumbbells" restrictive without
    making the original equipment mention restrictive too.
    """
    base = (base_prompt or "").strip().rstrip(".")
    extra = (adjustment or "").strip()
    if not base:
        return extra
    if not extra:
        return base
    return f"{base}. {extra}"


def resolve_duration(base_duration: int, base_prompt: str, adjustment: str) -> int:
    """The adjustment's duration wins; otherwise the original stands."""
    stated = extract_duration(adjustment)
    if stated is not None:
        return stated
    return extract_duration(base_prompt) or base_duration


async def adjust_workout(
    *,
    services,
    member_id: str,
    base_prompt: str,
    adjustment: str,
    base_duration: int,
    previous_exercise_ids: list[str],
) -> dict:
    """Re-run the full pipeline for an adjusted request and diff the result."""
    started = time.perf_counter()

    effective_prompt = combine(base_prompt, adjustment)
    duration = resolve_duration(base_duration, base_prompt, adjustment)

    state = await services.workflow.run(
        WorkoutRequest(
            member_id=member_id,
            prompt=effective_prompt,
            duration_minutes=duration,
            # The duration was decided above; do not let the scan re-pick the
            # original prompt's number just because it appears first.
            duration_is_explicit=True,
        )
    )

    baseline_started = time.perf_counter()
    baseline = _baseline_candidates(services, member_id, base_prompt, base_duration)
    baseline_rerun_ms = round((time.perf_counter() - baseline_started) * 1000, 2)
    new_plan_ids = [
        item.exercise_id
        for section in state["generated_workout"].sections
        for item in section.exercises
    ]

    diff: AdjustmentDiff = build_adjustment_diff(
        previous_exercise_ids=previous_exercise_ids,
        new_plan_ids=new_plan_ids,
        decisions=state["safety_decisions"],
        baseline_candidates=baseline,
        adjusted_candidates=state["eligible_exercises"],
        provenance=state["provenance"],
    )

    return {
        "request_id": uuid.uuid4().hex[:12],
        "state": state,
        "diff": diff,
        "effective_prompt": effective_prompt,
        "duration_minutes": duration,
        "baseline_rerun_ms": baseline_rerun_ms,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def _baseline_candidates(services, member_id: str, base_prompt: str, base_duration: int):
    """Re-derive the original request's ranking, deterministically and cheaply.

    Runs intent -> safety -> ranking and stops. No composition, no LLM, no
    provenance: the diff only needs the scores the ranker would have produced
    before the adjustment, and those are reproducible by construction.
    """
    member = services.repository.get_member_context(member_id)
    if member is None:
        return []

    intent, resolved = parse_intent(base_prompt, base_duration, services.resolver)
    context = services.engine.build_context(member, intent, resolved)
    decisions = {d.exercise_id: d for d in services.engine.evaluate_all(context)}

    trajectory_service = services.trajectory or MemberTrajectoryService(services.ontology)
    return rank_candidates(
        services.repository.list_exercises(),
        decisions,
        member,
        intent,
        resolved,
        services.ontology,
        trajectory=trajectory_service.analyze(member),
    )
