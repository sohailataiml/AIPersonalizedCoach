"""Which MCP tool answers which coach question, and what may be said about it.

Two responsibilities, both deliberately outside the model:

**Planning.** A bounded plan of MCP tool calls is derived from the question. The
routing itself is deterministic keyword matching, which matters for more than
offline support: tool *selection* for a safety question must not silently drift
because a model felt creative. A real provider can refine a plan (see
``service.py``), but it can never remove the safety tool from one.

**Enforcement.** ``SafetyVerdictGuard`` compares the final prose against the
authoritative verdicts that came back. A system prompt asking a model not to
contradict a tool is a request; this is a check. If the graph said *excluded*
and the sentence says *safe*, the sentence loses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from app.copilot.mcp_gateway import ToolCall, ToolResult

#: Tools whose result is an authoritative safety verdict. A question that routes
#: to one of these may never be answered from model judgement alone.
SAFETY_TOOLS = frozenset(
    {
        "evaluate_exercise_safety",
        "get_exercise_provenance",
        "get_safe_exercise_candidates",
        "evaluate_workout_request",
    }
)

#: Ceiling on tool calls per request. Plans are built up-front rather than
#: iteratively, so this is a hard bound and not a hopeful limit.
MAX_TOOL_CALLS = 4

_WHY_REMOVED = re.compile(
    r"\bwhy\b.*\b(remov|exclud|drop|filter|left out|not includ|missing|took out)",
    re.I,
)
_IS_IT_SAFE = re.compile(
    r"\b(can|could|should|is|are|may)\b.*\b(do|perform|safe|ok|okay|fine|handle|"
    r"train|attempt)\b|\bsafe (for|to)\b|\bcontraindicat|\baggravat",
    re.I,
)
_ALTERNATIVES = re.compile(
    r"\b(alternative|option|instead|swap|replace|substitut|suggest|recommend|"
    r"what (?:else|can she do))\b",
    re.I,
)
_WORKOUT_SHAPE = re.compile(
    r"\b(workout|session|plan|programme|program|routine)\b", re.I
)
_FOCUS_HINT = re.compile(
    r"\b(quad|hamstring|glute|calf|calves|chest|back|shoulder|arm|core|"
    r"upper body|lower body|full body|push|pull|hinge|squat)\w*\b",
    re.I,
)
_METRIC_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("adherence", ("adherence", "consistency", "completion", "compliance", "showing up")),
    ("sleep", ("sleep", "sleeping", "rest", "bedtime")),
    ("weight", ("weight", "weigh", "body mass", "kg")),
)

#: Below this the phrase is not confidently an exercise name, so no
#: exercise-specific tool is planned - better to answer generally than to
#: authoritatively evaluate the wrong exercise.
NAME_MATCH_FLOOR = 72


@dataclass
class ToolPlan:
    calls: list[ToolCall]
    reason: str

    @property
    def touches_safety(self) -> bool:
        return any(c.name in SAFETY_TOOLS for c in self.calls)


def _match_exercise(message: str, catalog: dict[str, str]) -> str | None:
    """Best-effort exercise id for a name mentioned in the question."""
    if not catalog:
        return None
    names = list(catalog)
    best = process.extractOne(message, names, scorer=fuzz.partial_ratio)
    if best and best[1] >= NAME_MATCH_FLOOR:
        return catalog[best[0]]
    return None


def _focus_terms(message: str) -> list[str]:
    seen: list[str] = []
    for match in _FOCUS_HINT.finditer(message):
        term = match.group(0).lower()
        if term not in seen:
            seen.append(term)
    return seen


def plan_tools(message: str, member_id: str, catalog: dict[str, str]) -> ToolPlan:
    """Deterministically choose the MCP tools that answer this question."""
    text = message.strip()

    # 1. "Why was X removed?" - a provenance question, and specifically a
    #    question about a decision that has already been made.
    if _WHY_REMOVED.search(text):
        exercise_id = _match_exercise(text, catalog)
        if exercise_id:
            return ToolPlan(
                calls=[
                    ToolCall(
                        "get_exercise_provenance",
                        {"member_id": member_id, "exercise_id": exercise_id},
                    )
                ],
                reason="explains an existing exclusion with real graph evidence",
            )
        return ToolPlan(
            calls=[
                ToolCall(
                    "evaluate_workout_request",
                    {"member_id": member_id, "prompt": text},
                )
            ],
            reason="no specific exercise named; evaluates the request as a whole",
        )

    # 2. "Can she do X?" - an authoritative single-exercise safety question.
    exercise_id = _match_exercise(text, catalog)
    if exercise_id and _IS_IT_SAFE.search(text):
        return ToolPlan(
            calls=[
                ToolCall(
                    "evaluate_exercise_safety",
                    {"member_id": member_id, "exercise_id": exercise_id},
                ),
                ToolCall(
                    "get_exercise_provenance",
                    {"member_id": member_id, "exercise_id": exercise_id},
                ),
            ],
            reason="authoritative verdict plus the evidence behind it",
        )

    # 3. Reshaping a whole session under a constraint.
    if _WORKOUT_SHAPE.search(text) and (
        _FOCUS_HINT.search(text) or _IS_IT_SAFE.search(text)
    ):
        calls = [
            ToolCall(
                "evaluate_workout_request", {"member_id": member_id, "prompt": text}
            )
        ]
        focus = _focus_terms(text)
        if focus:
            calls.append(
                ToolCall(
                    "get_safe_exercise_candidates",
                    {"member_id": member_id, "focus": focus, "limit": 10},
                )
            )
        return ToolPlan(calls=calls, reason="evaluates the request and offers safe options")

    # 4. Asking for alternatives / options.
    if _ALTERNATIVES.search(text) or (_FOCUS_HINT.search(text) and "safe" in text.lower()):
        return ToolPlan(
            calls=[
                ToolCall(
                    "get_safe_exercise_candidates",
                    {
                        "member_id": member_id,
                        "focus": _focus_terms(text) or None,
                        "limit": 10,
                    },
                )
            ],
            reason="only graph-approved candidates may be suggested",
        )

    # 5. A metric trend question.
    lowered = text.lower()
    for metric, keywords in _METRIC_HINTS:
        if any(keyword in lowered for keyword in keywords):
            return ToolPlan(
                calls=[
                    ToolCall(
                        "get_member_metric_trend",
                        {"member_id": member_id, "metric": metric},
                    )
                ],
                reason=f"deterministic {metric} arithmetic",
            )

    # 6. Anything else about the member.
    return ToolPlan(
        calls=[ToolCall("get_member_context", {"member_id": member_id})],
        reason="general member question",
    )


# --- enforcement -------------------------------------------------------------

_AFFIRMS_SAFE = re.compile(
    r"\b(is|are|should be|would be|looks|seems|'s)\s+(perfectly\s+|totally\s+|"
    r"completely\s+)?(safe|fine|ok|okay|good to go|no problem)\b"
    r"|\b(can|could|should)\s+(definitely\s+|certainly\s+)?(do|perform|go ahead)\b"
    r"|\bno (issue|problem|concern)s?\b"
    r"|\bcleared\b|\bgo ahead\b",
    re.I,
)


@dataclass
class SafetyVerdict:
    exercise_name: str
    status: str

    @property
    def is_excluded(self) -> bool:
        return self.status == "excluded"


class SafetyVerdictGuard:
    """Stops a model contradicting an authoritative exclusion.

    The failure this exists to prevent is narrow and serious: the graph excludes
    an exercise, the tool result says so, and the generated sentence still reads
    "yes, that's fine". A prompt instruction reduces that risk; it does not
    remove it. This is the check that does.
    """

    @staticmethod
    def verdicts(results: list[ToolResult]) -> list[SafetyVerdict]:
        found: list[SafetyVerdict] = []
        for result in results:
            if not result.ok or result.name not in SAFETY_TOOLS:
                continue
            payload = result.payload
            status = payload.get("status")
            name = payload.get("exercise_name")
            if isinstance(status, str) and isinstance(name, str):
                found.append(SafetyVerdict(exercise_name=name, status=status))
        return found

    @classmethod
    def enforce(cls, answer: str, results: list[ToolResult]) -> tuple[str, bool]:
        """Return (answer, was_corrected)."""
        excluded = [v for v in cls.verdicts(results) if v.is_excluded]
        if not excluded:
            return answer, False
        if not _AFFIRMS_SAFE.search(answer or ""):
            return answer, False

        names = ", ".join(sorted({v.exercise_name for v in excluded}))
        corrected = (
            f"{names} is excluded for this member by the deterministic safety "
            f"engine, so I can't present it as safe. The exclusion comes from "
            f"graph traversal over her recorded injuries and available "
            f"equipment, not from my judgement. See the evidence below for the "
            f"exact rule and path that produced it."
        )
        return corrected, True
