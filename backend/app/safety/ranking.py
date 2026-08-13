"""Candidate ranking.

Ranking is separate from safety on purpose: safety decides *eligibility*,
ranking decides *ordering*. A preference can move an exercise down this list but
can never remove it - that only happens in the safety engine.

Note on ``priority_tier``: every row in the supplied catalog has
``priority_tier == 2``, so the field carries no ranking signal at all. We rank on
goal alignment, requested focus, equipment fit and recency instead, and say so
rather than pretending the tier means something.
"""

from __future__ import annotations

from app.domain.exercise import Exercise, ExerciseCandidate
from app.domain.member import MemberContext
from app.domain.resolution import ResolvedConcept
from app.domain.safety import SafetyDecision
from app.domain.workout import WorkoutIntent
from app.ontology.loader import Ontology
from app.safety import policies

BASE_SCORE = 50.0


def rank_candidates(
    exercises: list[Exercise],
    decisions: dict[str, SafetyDecision],
    member: MemberContext,
    intent: WorkoutIntent,
    resolved: list[ResolvedConcept],
    ontology: Ontology,
) -> list[ExerciseCandidate]:
    """Score every non-excluded exercise. Excluded ones never appear."""
    focus_muscles, focus_joints = _focus_targets(intent, resolved, ontology)
    recent = _recent_exercise_names(member)

    candidates: list[ExerciseCandidate] = []
    for exercise in exercises:
        decision = decisions.get(exercise.id)
        if decision is not None and decision.is_excluded:
            continue

        score = BASE_SCORE
        reasons: list[str] = []

        if decision is not None and decision.score_adjustment:
            score += decision.score_adjustment
            reasons.append(f"safety adjustment {decision.score_adjustment:+.0f}")

        if focus_muscles and set(exercise.muscle_groups) & focus_muscles:
            score += policies.BONUS_FOCUS_MATCH
            reasons.append("matches requested focus (muscles)")
        elif focus_joints and set(exercise.joints_loaded) & focus_joints:
            score += policies.BONUS_FOCUS_MATCH * 0.6
            reasons.append("matches requested focus (joints)")
        elif focus_muscles or focus_joints:
            # Off-brief. Mobility/regen work is exempt: it is always usable as
            # warmup or cooldown regardless of the session's focus.
            if not _is_restorative(exercise):
                score += policies.PENALTY_OFF_FOCUS
                reasons.append("outside the requested focus")

        goal_bonus, goal_reason = _goal_alignment(exercise, member)
        if goal_bonus:
            score += goal_bonus
            reasons.append(goal_reason)

        if exercise.name.lower() in recent:
            score += policies.PENALTY_RECENTLY_PERFORMED
            reasons.append("performed recently - rotate for variety")

        candidates.append(
            ExerciseCandidate(exercise=exercise, score=round(score, 2), rank_reasons=reasons)
        )

    candidates.sort(key=lambda c: (-c.score, c.exercise.name))
    return candidates


def _focus_targets(
    intent: WorkoutIntent, resolved: list[ResolvedConcept], ontology: Ontology
) -> tuple[set[str], set[str]]:
    muscles: set[str] = set()
    joints: set[str] = set()

    focus_text = " ".join(intent.requested_focus).lower()
    for target in ontology.focus_targets.values():
        if any(alias in focus_text for alias in target.aliases):
            muscles.update(target.muscle_groups)
            joints.update(target.joints)

    for concept in resolved:
        if not concept.is_resolved or not concept.canonical_id:
            continue
        if concept.canonical_id.startswith("focus:"):
            target = ontology.focus_targets.get(concept.canonical_id.split(":", 1)[1])
            if target:
                muscles.update(target.muscle_groups)
                joints.update(target.joints)

    return muscles, joints


def _goal_alignment(exercise: Exercise, member: MemberContext) -> tuple[float, str]:
    """Reward exercises that serve the member's highest-priority goals."""
    for goal in sorted(member.goals, key=lambda g: g.priority):
        text = goal.text.lower()
        if "lower-body" in text or "lower body" in text:
            if {"quads", "glutes", "hamstrings", "calves"} & set(exercise.muscle_groups):
                return policies.BONUS_GOAL_ALIGNED, f'supports goal: "{goal.text}"'
        if "squat" in text and any("squat" in p for p in exercise.movement_patterns):
            return policies.BONUS_GOAL_ALIGNED * 0.5, f'progresses goal: "{goal.text}"'
    return 0.0, ""


def _is_restorative(exercise: Exercise) -> bool:
    """Mobility, stretching, yoga and regen work - always valid warmup/cooldown."""
    patterns = exercise.movement_patterns
    if not patterns:
        return False
    return all(policies.is_low_load_pattern(pattern) for pattern in patterns)


def _recent_exercise_names(member: MemberContext) -> set[str]:
    names: set[str] = set()
    for session in member.workout_history[:2]:
        for performance in session.exercises:
            names.add(performance.name.lower())
    return names
