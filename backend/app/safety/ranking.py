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
from app.domain.trajectory import MemberTrajectory
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
    trajectory: MemberTrajectory | None = None,
) -> list[ExerciseCandidate]:
    """Score every non-excluded exercise. Excluded ones never appear.

    ``trajectory`` is optional and additive. When present it can only reorder
    what safety already allowed: exclusions are applied before any longitudinal
    arithmetic runs, and the adjustment itself is bounded below the smallest
    safety penalty. A caller that omits it gets the pre-longitudinal ordering
    unchanged.
    """
    focus_muscles, focus_joints = _focus_targets(intent, resolved, ontology)
    recent = _recent_exercise_names(member)
    familiar_families = set(trajectory.bias.familiar_movement_families) if trajectory else set()

    candidates: list[ExerciseCandidate] = []
    for exercise in exercises:
        decision = decisions.get(exercise.id)
        # Hard safety first, and unconditionally: an excluded exercise never
        # reaches the personalization arithmetic below.
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

        # Rotation for variety is the default, but it is exactly the wrong
        # instinct while adherence is falling: familiarity is what gets a
        # wavering member to finish the session. The longitudinal layer owns
        # this lever when it has a reading.
        novelty_bias = trajectory.bias.novelty_bias if trajectory else "standard"
        if exercise.name.lower() in recent and novelty_bias != "low":
            score += policies.PENALTY_RECENTLY_PERFORMED
            reasons.append("performed recently - rotate for variety")

        # Kept out of `rank_reasons` deliberately: longitudinal influence is
        # carried in its own field so provenance can show it as a distinct line
        # and a caller can measure it independently of graph-derived ranking.
        longitudinal, longitudinal_reasons = _longitudinal_adjustment(
            exercise, ontology, trajectory, familiar_families
        )
        score += longitudinal

        candidates.append(
            ExerciseCandidate(
                exercise=exercise,
                score=round(score, 2),
                rank_reasons=reasons,
                longitudinal_adjustment=longitudinal,
                longitudinal_reasons=longitudinal_reasons,
            )
        )

    candidates.sort(key=lambda c: (-c.score, c.exercise.name))
    return candidates


def _longitudinal_adjustment(
    exercise: Exercise,
    ontology: Ontology,
    trajectory: MemberTrajectory | None,
    familiar_families: set[str],
) -> tuple[float, list[str]]:
    """Familiarity weighting, bounded and explainable.

    One lever, two directions:

    * ``novelty_bias == "low"`` - the member is wavering, so movement families
      they have actually completed recently get a small lift.
    * ``novelty_bias == "high"`` - they are ahead of their own target, so
      unfamiliar families get the lift instead.

    Returns the adjustment and the reasons behind it, which provenance renders
    verbatim. An empty reason list means longitudinal reasoning did not move
    this exercise at all, which is itself worth being able to state.
    """
    if trajectory is None or not familiar_families:
        return 0.0, []

    families = _families_of(exercise, ontology)
    if not families:
        return 0.0, []

    bias = trajectory.bias.novelty_bias
    overlap = families & familiar_families

    if bias == "low" and overlap:
        return policies.BONUS_FAMILIAR_FAMILY, [
            f"familiar movement family ({', '.join(sorted(overlap))}) - "
            f"trained recently while adherence is {trajectory.adherence.direction}"
        ]

    if bias == "high" and not overlap:
        return policies.BONUS_NOVEL_FAMILY, [
            "new movement family - adherence and training load support new stimulus"
        ]

    return 0.0, []


def _families_of(exercise: Exercise, ontology: Ontology) -> set[str]:
    families = set()
    for pattern in exercise.movement_patterns:
        family = ontology.family_for_pattern(pattern)
        if family:
            families.add(family.id)
    return families


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
