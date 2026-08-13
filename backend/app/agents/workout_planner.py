"""LLM workout composition.

The model receives a deliberately narrow payload:

* the member's goals, preferences and session duration;
* the resolved intent;
* **only** the safety-approved candidate exercise ids.

It never sees the filtered exercises, so it cannot select one, and it is told
plainly that ids are the only valid currency. Even so, nothing here is trusted:
``validate_and_repair`` re-checks every returned id against the graph.
"""

from __future__ import annotations

import json
import logging
import re

from app.domain.exercise import ExerciseCandidate
from app.domain.member import MemberContext
from app.domain.safety import SafetyDecision
from app.domain.workout import LLMWorkoutDraft, WorkoutIntent
from app.llm.base import LLMClient, LLMError
from app.safety.engine import SafetyContext

logger = logging.getLogger(__name__)

MAX_CANDIDATES = 24

SYSTEM_PROMPT = """You are an expert strength coach composing a single training session.

HARD RULES
1. Use ONLY exercise ids from the supplied candidate list. Never invent an id.
2. Never add an exercise because it seems useful - if its id is not listed, it is
   not available to you.
3. Respect the session duration budget.
4. Produce warmup, main and cooldown sections.
5. For each exercise give sets and reps, or a duration in seconds for timed work.
6. If a candidate carries `needs_rom_caveat`, include a short coaching_note about
   keeping range of motion pain-free.

The candidate list has already been filtered for safety by a clinical knowledge
graph. You are composing and explaining, not judging safety."""


async def compose_workout_draft(
    *,
    llm: LLMClient,
    member: MemberContext,
    intent: WorkoutIntent,
    candidates: list[ExerciseCandidate],
    safety_context: SafetyContext,
    decisions: dict[str, SafetyDecision],
) -> LLMWorkoutDraft:
    payload = _build_payload(member, intent, candidates, safety_context, decisions)
    user = (
        "Compose the session described by this JSON brief. "
        "Return warmup, main and cooldown sections.\n\n"
        f"{json.dumps(payload, indent=2)}"
    )

    try:
        return await llm.generate_structured(
            schema=LLMWorkoutDraft, system=SYSTEM_PROMPT, user=user
        )
    except LLMError as exc:
        # Fail soft on composition only. Safety is unaffected: the deterministic
        # fallback draws from the same approved candidate pool, and the plan is
        # validated afterwards either way.
        logger.warning("LLM composition failed (%s); using deterministic fallback", exc)
        from app.llm.stub import StubLLMClient

        return await StubLLMClient().generate_structured(
            schema=LLMWorkoutDraft, system=SYSTEM_PROMPT, user=user
        )


def _build_payload(
    member: MemberContext,
    intent: WorkoutIntent,
    candidates: list[ExerciseCandidate],
    safety_context: SafetyContext,
    decisions: dict[str, SafetyDecision],
) -> dict:
    top = candidates[:MAX_CANDIDATES]

    return {
        "member": {
            "name": member.profile.name,
            "goals": [g.text for g in sorted(member.goals, key=lambda g: g.priority)],
            "preferred_session_minutes": member.preferences.preferred_session_minutes,
            "dislikes": member.preferences.dislikes,
            "notes": member.preferences.notes,
        },
        "session": {
            "duration_minutes": intent.duration_minutes,
            "focus": intent.requested_focus,
            "coach_prompt_excluded": intent.explicit_exclusions,
        },
        "suggested_title": _title(intent),
        "duration_minutes": intent.duration_minutes,
        "safety_summary": _safety_summary(safety_context),
        "candidate_exercises": [
            _candidate_payload(candidate, decisions.get(candidate.exercise.id))
            for candidate in top
        ],
    }


def _candidate_payload(
    candidate: ExerciseCandidate, decision: SafetyDecision | None
) -> dict:
    exercise = candidate.exercise
    needs_caveat = bool(
        decision
        and any(
            r.rule_id in {"injury_contraindicated_pattern", "injury_region_stress"}
            for r in decision.reasons
        )
    )
    return {
        "id": exercise.id,
        "name": exercise.name,
        "muscle_groups": exercise.muscle_groups,
        "movement_patterns": exercise.movement_patterns,
        "equipment_required": exercise.equipment_required,
        "is_reps": exercise.is_reps,
        "is_duration": exercise.is_duration,
        "is_unilateral": exercise.is_unilateral,
        "rank_score": candidate.score,
        "rank_reasons": candidate.rank_reasons,
        "needs_rom_caveat": needs_caveat,
    }


def _safety_summary(context: SafetyContext) -> dict:
    """Context, not authority. Stated so the model can explain, not decide."""
    return {
        "available_equipment": sorted(context.available_equipment),
        "active_injuries": [
            {
                "name": injury["injury_name"],
                "condition": injury["condition_label"],
                "severity": injury.get("severity"),
                "status": injury.get("status"),
                "avoid_patterns": injury.get("contraindicated_patterns", []),
            }
            for injury in context.injuries
        ],
        "note": (
            "This summary is for phrasing only. Exercise eligibility was already "
            "decided by graph traversal; the candidate list is the authority."
        ),
    }


_DURATION_TOKENS = re.compile(r"\b\d+\s*-?\s*(?:minute|minutes|min|mins)?\b", re.I)


def _title(intent: WorkoutIntent) -> str:
    """Build a title without echoing the duration twice."""
    focus = "Full Body"
    if intent.requested_focus:
        cleaned = _DURATION_TOKENS.sub("", intent.requested_focus[0]).strip(" -")
        focus = cleaned.replace("-", " ").title() if cleaned else "Full Body"
    return f"{intent.duration_minutes}-Minute {focus} Session"
