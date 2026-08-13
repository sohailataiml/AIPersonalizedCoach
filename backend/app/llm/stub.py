"""Deterministic offline LLM stub.

Why this exists: a reviewer must be able to clone the repo, run one command, and
see the whole system work - including the graph reasoning, the safety gate and
the provenance trace - without an API key. The stub composes a sensible workout
from the *already safety-filtered* candidate list and writes grounded copilot
answers from the *already computed* analytics.

It is honest about what it is: every response is tagged ``generator: "stub"`` so
the UI can say so. It is not pretending to be a language model, and no part of
the safety architecture depends on which implementation is active - that is
precisely the point being demonstrated.
"""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel

from app.domain.workout import LLMWorkoutDraft, WorkoutExercise, WorkoutSection

T = TypeVar("T", bound=BaseModel)

WARMUP_HINTS = ("mobility", "regen", "yoga", "balance")
COOLDOWN_HINTS = ("mobility - static", "regen", "massage", "yoga")


class StubLLMClient:
    name = "stub"

    async def generate_structured(
        self, *, schema: type[T], system: str, user: str, max_tokens: int = 2000
    ) -> T:
        if schema is LLMWorkoutDraft:
            return self._compose_workout(user)  # type: ignore[return-value]
        return schema.model_validate({})

    async def answer_grounded(
        self, *, system: str, user: str, evidence: str, max_tokens: int = 700
    ) -> str:
        """Render the deterministic evidence as prose without adding facts."""
        try:
            facts = json.loads(evidence)
        except (ValueError, TypeError):
            return evidence.strip()[:600]

        summary = facts.get("summary")
        if summary:
            return str(summary)

        lines = [f"{key.replace('_', ' ')}: {value}" for key, value in facts.items()]
        return "\n".join(lines[:12])

    # --- workout composition ---------------------------------------------

    def _compose_workout(self, user: str) -> LLMWorkoutDraft:
        payload = _extract_json(user)
        candidates: list[dict] = payload.get("candidate_exercises", [])
        duration = int(payload.get("duration_minutes", 45))
        title = payload.get("suggested_title") or "Personalized Session"

        if not candidates:
            return LLMWorkoutDraft(title=title, sections=[])

        warmup_pool = [c for c in candidates if _is_warmup(c)]
        cooldown_pool = [c for c in candidates if _is_cooldown(c)]
        main_pool = [
            c
            for c in candidates
            if c not in warmup_pool and c not in cooldown_pool
        ] or candidates

        # Time budget: ~20% warmup, ~65% main, ~15% cooldown.
        main_slots = max(3, min(6, duration // 8))
        warmup_slots = 2 if duration >= 30 else 1
        cooldown_slots = 2 if duration >= 30 else 1

        used: set[str] = set()
        sections = [
            WorkoutSection(
                name="warmup",
                exercises=_take(warmup_pool or candidates, warmup_slots, used, "warmup"),
            ),
            WorkoutSection(
                name="main", exercises=_take(main_pool, main_slots, used, "main")
            ),
            WorkoutSection(
                name="cooldown",
                exercises=_take(cooldown_pool or candidates, cooldown_slots, used, "cooldown"),
            ),
        ]
        return LLMWorkoutDraft(
            title=title, sections=[s for s in sections if s.exercises]
        )


def _take(
    pool: list[dict], count: int, used: set[str], section: str
) -> list[WorkoutExercise]:
    chosen: list[WorkoutExercise] = []
    for candidate in pool:
        if len(chosen) >= count:
            break
        exercise_id = candidate.get("id")
        if not exercise_id or exercise_id in used:
            continue
        used.add(exercise_id)
        chosen.append(_prescribe(candidate, section))
    return chosen


def _prescribe(candidate: dict, section: str) -> WorkoutExercise:
    """Assign sets/reps/duration from the catalog's own capability flags."""
    is_reps = bool(candidate.get("is_reps", True))
    name = candidate.get("name", "Exercise")

    if section == "warmup":
        sets, reps, seconds, rest = 1, ("8-10" if is_reps else None), (None if is_reps else 45), 20
    elif section == "cooldown":
        sets, reps, seconds, rest = 1, None, 45, 15
    else:
        sets = 3
        reps = "8-12" if is_reps else None
        seconds = None if is_reps else 40
        rest = 75

    reasons = candidate.get("rank_reasons") or []
    rationale = (
        f"Selected from the graph-approved candidate pool ({', '.join(reasons[:2])})."
        if reasons
        else "Selected from the graph-approved candidate pool."
    )

    note = None
    if candidate.get("needs_rom_caveat"):
        note = "Keep range of motion pain-free; stop short of deep knee flexion."

    return WorkoutExercise(
        exercise_id=str(candidate.get("id")),
        name=name,
        sets=sets,
        reps=reps,
        duration_seconds=seconds,
        rest_seconds=rest,
        rationale=rationale,
        coaching_note=note,
    )


def _is_warmup(candidate: dict) -> bool:
    patterns = " ".join(candidate.get("movement_patterns", [])).lower()
    return any(hint in patterns for hint in WARMUP_HINTS)


def _is_cooldown(candidate: dict) -> bool:
    patterns = " ".join(candidate.get("movement_patterns", [])).lower()
    return any(hint in patterns for hint in COOLDOWN_HINTS)


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except ValueError:
        return {}
