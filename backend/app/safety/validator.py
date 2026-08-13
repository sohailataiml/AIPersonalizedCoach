"""Post-generation safety gate.

This is the module that turns safety from a prompt hope into a system
invariant. Whatever the LLM returns - however well or badly it followed
instructions - every exercise id in the plan is re-checked against the
deterministic decisions produced by graph traversal.

Three failure modes are handled:

1. **Excluded exercise selected.** The model picked something the graph
   removed. Rejected, and replaced from the ranked safe pool when possible.
2. **Hallucinated id.** The model invented an id that is not in the catalog.
   Rejected the same way - an unknown id can never be certified safe.
3. **Empty result.** If nothing survives, we fail closed rather than returning
   an unvalidated plan.

Every correction is recorded in ``PostValidationReport`` and surfaced in the UI,
because a silent fix would hide exactly the event a reviewer most wants to see.
"""

from __future__ import annotations

from app.domain.exercise import ExerciseCandidate
from app.domain.safety import SafetyDecision
from app.domain.workout import (
    GeneratedWorkout,
    LLMWorkoutDraft,
    PostValidationReport,
    WorkoutExercise,
    WorkoutSection,
)


class UnsafePlanError(RuntimeError):
    """Raised when a plan cannot be made safe."""


def validate_and_repair(
    draft: LLMWorkoutDraft,
    decisions: dict[str, SafetyDecision],
    candidates: list[ExerciseCandidate],
    duration_minutes: int,
    *,
    allow_repair: bool = True,
) -> tuple[GeneratedWorkout, PostValidationReport]:
    """Re-check every selected exercise against the graph's decisions."""
    report = PostValidationReport()
    candidate_by_id = {c.exercise.id: c for c in candidates}

    used: set[str] = set()
    repaired_sections: list[WorkoutSection] = []

    for section in draft.sections:
        kept: list[WorkoutExercise] = []
        for item in section.exercises:
            report.checked_exercise_ids.append(item.exercise_id)
            decision = decisions.get(item.exercise_id)

            # Case 2: an id the catalog has never heard of.
            if decision is None:
                report.passed = False
                report.hallucinated_ids.append(item.exercise_id)
                report.rejected.append(
                    {
                        "exercise_id": item.exercise_id,
                        "name": item.name,
                        "section": section.name,
                        "reason": "Exercise id is not in the catalog (model hallucination).",
                        "rule_id": "hallucinated_id",
                    }
                )
                replacement = _next_safe(candidates, candidate_by_id, used, decisions)
                if allow_repair and replacement is not None:
                    kept.append(_as_workout_exercise(replacement, item))
                    used.add(replacement.exercise.id)
                    report.replacements.append(
                        {
                            "replaced_id": item.exercise_id,
                            "replaced_name": item.name,
                            "with_id": replacement.exercise.id,
                            "with_name": replacement.exercise.name,
                            "section": section.name,
                        }
                    )
                continue

            # Case 1: the graph excluded it.
            if decision.is_excluded:
                report.passed = False
                report.rejected.append(
                    {
                        "exercise_id": item.exercise_id,
                        "name": decision.exercise_name,
                        "section": section.name,
                        "reason": "; ".join(decision.reason_messages())
                        or "Excluded by deterministic safety engine.",
                        "rule_id": decision.reasons[0].rule_id if decision.reasons else "excluded",
                        "graph_paths": [p.render() for p in decision.graph_paths],
                    }
                )
                replacement = _next_safe(candidates, candidate_by_id, used, decisions)
                if allow_repair and replacement is not None:
                    kept.append(_as_workout_exercise(replacement, item))
                    used.add(replacement.exercise.id)
                    report.replacements.append(
                        {
                            "replaced_id": item.exercise_id,
                            "replaced_name": decision.exercise_name,
                            "with_id": replacement.exercise.id,
                            "with_name": replacement.exercise.name,
                            "section": section.name,
                        }
                    )
                continue

            # Survived. Duplicates are dropped quietly - not a safety event.
            if item.exercise_id in used:
                continue
            used.add(item.exercise_id)
            kept.append(item)

        if kept:
            repaired_sections.append(WorkoutSection(name=section.name, exercises=kept))

    if not repaired_sections or not any(s.exercises for s in repaired_sections):
        raise UnsafePlanError(
            "No exercise in the generated plan survived deterministic safety validation, "
            "and no safe replacement was available. Failing closed."
        )

    if report.rejected:
        report.notes.append(
            f"{len(report.rejected)} exercise(s) rejected by post-generation validation; "
            f"{len(report.replacements)} replaced from the ranked safe pool."
        )

    workout = GeneratedWorkout(
        title=draft.title or "Workout",
        duration_minutes=duration_minutes,
        sections=repaired_sections,
    )
    return workout, report


def _next_safe(
    candidates: list[ExerciseCandidate],
    candidate_by_id: dict[str, ExerciseCandidate],
    used: set[str],
    decisions: dict[str, SafetyDecision],
) -> ExerciseCandidate | None:
    """Highest-ranked candidate that is safe and not already in the plan."""
    for candidate in candidates:
        exercise_id = candidate.exercise.id
        if exercise_id in used:
            continue
        decision = decisions.get(exercise_id)
        if decision is not None and decision.is_excluded:
            continue
        return candidate
    return None


def _as_workout_exercise(
    candidate: ExerciseCandidate, original: WorkoutExercise
) -> WorkoutExercise:
    exercise = candidate.exercise
    return WorkoutExercise(
        exercise_id=exercise.id,
        name=exercise.name,
        sets=original.sets if exercise.is_reps else None,
        reps=original.reps if exercise.is_reps else None,
        duration_seconds=original.duration_seconds
        or (45 if not exercise.is_reps else None),
        rest_seconds=original.rest_seconds or 60,
        rationale=(
            "Substituted by the deterministic safety gate after the model selected an "
            "exercise the knowledge graph had excluded."
        ),
        substituted_for=original.name or original.exercise_id,
    )
