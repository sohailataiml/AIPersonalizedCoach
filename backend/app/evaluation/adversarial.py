"""Adversarial composers used by the validation cases.

These exist to attack the post-generation gate from the outside. Each returns a
draft the safety engine has already ruled out, and the case passes only if none
of it survives.

This is deliberately not a mock of the workflow: the real LangGraph pipeline
runs, the real engine produces the decisions, and only the *model* is swapped.
Testing the gate against a cooperative model would measure nothing.
"""

from __future__ import annotations

from typing import Any

from app.domain.exercise import ExerciseCandidate
from app.domain.safety import SafetyDecision
from app.domain.workout import LLMWorkoutDraft
from app.llm.base import LLMClient

HALLUCINATED_ID = "hallucinated-id-9000"


def adversarial_draft(
    mode: str,
    decisions: dict[str, SafetyDecision],
    candidates: list[ExerciseCandidate],
) -> list[tuple[str, str]]:
    """The (id, name) pairs the fake model will insist on returning."""
    excluded = [(eid, d.exercise_name) for eid, d in decisions.items() if d.is_excluded]
    approved = {c.exercise.id for c in candidates}

    if mode == "excluded":
        return excluded[:1]
    if mode == "all_excluded":
        return excluded
    if mode == "hallucinated":
        return [(HALLUCINATED_ID, "Ghost Exercise")]
    if mode == "unavailable_equipment":
        # Anything the equipment rule removed is, by definition, unavailable.
        equipment_blocked = [
            (eid, d.exercise_name)
            for eid, d in decisions.items()
            if d.is_excluded
            and any(r.rule_id == "equipment_unavailable" for r in d.reasons)
        ]
        return equipment_blocked[:2] or excluded[:1]
    if mode == "outside_candidates":
        outside = [
            (eid, d.exercise_name) for eid, d in decisions.items() if eid not in approved
        ]
        return outside[:2] or excluded[:1]

    raise ValueError(f"unknown adversarial mode: {mode}")


class AdversarialLLM(LLMClient):
    """Returns exactly what it was told to, ignoring the candidate list."""

    name = "adversarial"

    def __init__(self, banned: list[tuple[str, str]]) -> None:
        self._banned = banned

    async def generate_structured(
        self, *, schema: Any, system: str, user: str
    ) -> LLMWorkoutDraft:  # noqa: ARG002
        return LLMWorkoutDraft.model_validate(
            {
                "title": "Adversarial plan",
                "sections": [
                    {
                        "name": "main",
                        "exercises": [
                            {
                                "exercise_id": exercise_id,
                                "name": name,
                                "sets": 3,
                                "reps": "8",
                            }
                            for exercise_id, name in self._banned
                        ],
                    }
                ],
            }
        )
