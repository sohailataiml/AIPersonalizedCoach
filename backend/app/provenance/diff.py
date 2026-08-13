"""Deterministic diff between a plan and its adjusted successor.

Built entirely from safety decisions and ranking scores the engine produced for
both requests. Nothing here asks a model why something changed, and nothing here
invents a relationship between what left and what arrived.

That last point is the one worth defending. It is tempting to render

    Removed: Barbell Back Squat
    Added:   Dumbbell Step-Up  (equivalent alternative)

but the graph encodes no equivalence between those two exercises. The ranker
simply scored one higher once the constraints changed. So an added exercise is
explained by *its own* inclusion reasons, and a removed one by the rule that
removed it - never by a substitution relationship that does not exist.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.exercise import ExerciseCandidate
from app.domain.safety import SafetyDecision
from app.provenance.builder import ProvenanceBundle

ChangeKind = Literal["removed", "added", "downranked"]

#: Score movement below this is noise from re-ranking rather than a signal worth
#: showing a coach.
MIN_SCORE_DELTA = 1.0


class PlanChange(BaseModel):
    exercise_id: str
    exercise: str
    kind: ChangeKind
    reasons: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    #: Present for down-ranked entries only, and always a real arithmetic delta.
    score_before: float | None = None
    score_after: float | None = None
    #: True when the adjustment made this exercise ineligible outright, rather
    #: than merely un-chosen. The distinction matters: one is a safety event.
    now_excluded: bool = False


class AdjustmentDiff(BaseModel):
    removed: list[PlanChange] = Field(default_factory=list)
    added: list[PlanChange] = Field(default_factory=list)
    downranked: list[PlanChange] = Field(default_factory=list)
    retained_ids: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    """Deterministic remarks, including why an adjustment changed nothing.

    "No change" is a real and common outcome - asking to avoid knee stress when
    the member's knee injury is already in the graph re-runs every rule and
    reaches the same answer. Saying so plainly is better than a silent no-op
    that reads like a failure.
    """


def build_adjustment_diff(
    *,
    previous_exercise_ids: list[str],
    new_plan_ids: list[str],
    decisions: dict[str, SafetyDecision],
    baseline_candidates: list[ExerciseCandidate],
    adjusted_candidates: list[ExerciseCandidate],
    provenance: ProvenanceBundle,
) -> AdjustmentDiff:
    """Compare the previous plan with the adjusted one.

    ``baseline_candidates`` come from re-running the *deterministic* half of the
    pipeline against the original request - no LLM call - so score movement is a
    genuine before/after comparison rather than a guess.
    """
    previous = list(dict.fromkeys(previous_exercise_ids))
    current = list(dict.fromkeys(new_plan_ids))
    previous_set, current_set = set(previous), set(current)

    diff = AdjustmentDiff(retained_ids=[i for i in current if i in previous_set])
    included_by_id = {item.exercise_id: item for item in provenance.included}

    for exercise_id in previous:
        if exercise_id in current_set:
            continue
        diff.removed.append(_removed(exercise_id, decisions, adjusted_candidates))

    for exercise_id in current:
        if exercise_id in previous_set:
            continue
        item = included_by_id.get(exercise_id)
        decision = decisions.get(exercise_id)
        diff.added.append(
            PlanChange(
                exercise_id=exercise_id,
                exercise=item.exercise if item else _name(exercise_id, decisions),
                kind="added",
                # The exercise's own deterministic inclusion reasons. No claim
                # is made that it replaces anything.
                reasons=list(item.reasons) if item else [],
                rule_ids=list(decision.reasons and [r.rule_id for r in decision.reasons] or [])
                if decision
                else [],
            )
        )

    diff.downranked = _downranked(baseline_candidates, adjusted_candidates, decisions)

    diff.counts = {
        "removed": len(diff.removed),
        "added": len(diff.added),
        "downranked": len(diff.downranked),
        "retained": len(diff.retained_ids),
        "newly_excluded": sum(1 for change in diff.removed if change.now_excluded),
    }

    excluded_now = sum(1 for d in decisions.values() if d.is_excluded)
    if not (diff.removed or diff.added or diff.downranked):
        diff.notes.append(
            "The adjusted request produced the same plan. Every rule was "
            f"re-evaluated against the graph ({excluded_now} of {len(decisions)} "
            "exercises excluded); the constraint was already in force."
        )
    if diff.counts["newly_excluded"]:
        diff.notes.append(
            f"{diff.counts['newly_excluded']} exercise(s) became ineligible, not "
            "merely unselected - the adjustment changed a hard safety decision."
        )
    return diff


def _removed(
    exercise_id: str,
    decisions: dict[str, SafetyDecision],
    adjusted_candidates: list[ExerciseCandidate],
) -> PlanChange:
    """Explain a departure with the rule that caused it, where one did.

    Two genuinely different outcomes, kept distinct rather than blurred into
    "removed": the adjustment made it *ineligible*, or it stayed eligible and
    simply lost its place in the ranking.
    """
    decision = decisions.get(exercise_id)
    name = _name(exercise_id, decisions)

    if decision is not None and decision.is_excluded:
        return PlanChange(
            exercise_id=exercise_id,
            exercise=name,
            kind="removed",
            reasons=decision.reason_messages(),
            rule_ids=[r.rule_id for r in decision.reasons],
            now_excluded=True,
        )

    still_eligible = any(c.exercise.id == exercise_id for c in adjusted_candidates)
    if still_eligible:
        return PlanChange(
            exercise_id=exercise_id,
            exercise=name,
            kind="removed",
            reasons=[
                "Still eligible after the adjustment, but no longer selected once "
                "candidates were re-ranked."
            ],
            rule_ids=[r.rule_id for r in decision.reasons] if decision else [],
        )

    return PlanChange(
        exercise_id=exercise_id,
        exercise=name,
        kind="removed",
        reasons=(
            decision.reason_messages()
            if decision
            else ["No longer present in the adjusted candidate set."]
        ),
        rule_ids=[r.rule_id for r in decision.reasons] if decision else [],
    )


def _downranked(
    baseline: list[ExerciseCandidate],
    adjusted: list[ExerciseCandidate],
    decisions: dict[str, SafetyDecision],
) -> list[PlanChange]:
    """Exercises that survived both rankings but scored lower after the change."""
    before = {c.exercise.id: c for c in baseline}
    changes: list[PlanChange] = []

    for candidate in adjusted:
        previous = before.get(candidate.exercise.id)
        if previous is None:
            continue
        delta = candidate.score - previous.score
        if delta > -MIN_SCORE_DELTA:
            continue

        decision = decisions.get(candidate.exercise.id)
        reasons = list(candidate.rank_reasons)
        if decision is not None and decision.reasons:
            reasons.extend(decision.reason_messages())

        changes.append(
            PlanChange(
                exercise_id=candidate.exercise.id,
                exercise=candidate.exercise.name,
                kind="downranked",
                reasons=reasons,
                rule_ids=[r.rule_id for r in decision.reasons] if decision else [],
                score_before=previous.score,
                score_after=candidate.score,
            )
        )

    changes.sort(key=lambda change: (change.score_after or 0) - (change.score_before or 0))
    return changes


def _name(exercise_id: str, decisions: dict[str, SafetyDecision]) -> str:
    decision = decisions.get(exercise_id)
    return decision.exercise_name if decision else exercise_id
