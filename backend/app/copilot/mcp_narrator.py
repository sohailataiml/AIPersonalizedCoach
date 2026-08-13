"""Deterministic prose for MCP tool results, plus a leak check.

Three jobs, all serving one rule: a structured tool payload must never reach a
coach *as* a payload.

**Narration.** Every MCP tool result can be rendered as short factual English
built only from fields the tool actually returned. Nothing is inferred and no
verdict is softened - the narrator reads ``status``, it never decides it. This
is what makes the offline path work: with no provider configured the coach
still gets sentences, and they are still evidence-backed.

**Leak detection.** Whatever the configured LLM returns is checked before it is
shown. A provider that echoes its own evidence back (the offline stub did
exactly that, which is the bug this module was written for) is caught here and
replaced with the narration above. The visible answer degrades to deterministic
prose, never to a serialized dict.

**Evidence projection.** ``build_safety_evidence`` produces the small, display
ready structure the UI expands under "view evidence" - decision, rule ids,
reason messages and *rendered* graph paths. The UI therefore never has to open
a raw payload to show what happened, which keeps interpretation of safety logic
on this side of the wire.

Nothing here decides, ranks or filters anything. It reads authoritative results
and phrases them.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.copilot.mcp_gateway import ToolResult

#: Longest a narrated clause list gets before it is truncated. Coaches read
#: these in a chat bubble; the full detail lives in the evidence expansion.
MAX_REASONS = 3
MAX_NAMED_EXAMPLES = 4
MAX_GRAPH_PATHS = 4


# --- display-ready evidence --------------------------------------------------


class EvidenceReason(BaseModel):
    rule_id: str
    message: str


class SafetyEvidence(BaseModel):
    """Compact projection of an authoritative verdict, for the UI expansion.

    Deliberately not the raw tool payload: rendered strings only, no ids the
    coach cannot act on, no nested objects for the frontend to interpret.
    """

    exercise_name: str
    decision: str = Field(description="allowed | downranked | excluded")
    reasons: list[EvidenceReason] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    graph_paths: list[str] = Field(
        default_factory=list,
        description="Already-rendered traversals. Never reconstructed from prose.",
    )
    evidence_note: str | None = None


# --- leak detection ----------------------------------------------------------

#: Markers of a serialized payload rather than prose. Deliberately narrow: each
#: one is something a sentence about training would not contain by accident.
_PAYLOAD_MARKERS = (
    "{'",
    "'}",
    '{"',
    '"}',
    "': ",
    '": ',
    "member_id",
    "exercise_id",
    "graph_paths",
    "rule_ids",
    "structured_content",
    "is_excluded",
)


def looks_like_raw_payload(text: str) -> bool:
    """True when a model handed back its evidence instead of a summary."""
    if not text:
        return False
    stripped = text.strip()
    if stripped.startswith(("{", "[")):
        return True
    return any(marker in stripped for marker in _PAYLOAD_MARKERS)


# --- narration ---------------------------------------------------------------


def _sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    return text if text.endswith((".", "!", "?")) else text + "."


def _join_names(names: list[str]) -> str:
    shown = names[:MAX_NAMED_EXAMPLES]
    joined = ", ".join(shown)
    remaining = len(names) - len(shown)
    return f"{joined} and {remaining} more" if remaining > 0 else joined


def _reason_messages(payload: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for reason in payload.get("reasons") or []:
        if isinstance(reason, dict):
            message = reason.get("message")
            if isinstance(message, str) and message not in out:
                out.append(message)
    return out


def _format_value(value: Any, unit: str | None) -> str:
    if value is None:
        return "n/a"
    if unit == "%":
        return f"{value}%"
    return f"{value} {unit}" if unit else str(value)


def _narrate_exercise_safety(payload: dict[str, Any], name: str) -> str:
    exercise = payload.get("exercise_name", "That exercise")
    status = payload.get("status", "unknown")
    reasons = _reason_messages(payload)[:MAX_REASONS]
    missing = payload.get("missing_equipment") or []

    if status == "excluded":
        parts = [
            f"No - {exercise} is excluded for {name} by the deterministic safety engine"
        ]
        if reasons:
            parts.append(" ".join(_sentence(r) for r in reasons))
        if missing:
            parts.append(f"Required equipment {name} does not have: {_join_names(missing)}")
        parts.append(
            "Ask for alternatives and I will only offer options that pass the same checks"
        )
        return " ".join(_sentence(p) for p in parts)

    if status == "downranked":
        parts = [f"{exercise} is allowed for {name}, but the engine ranks it down"]
        if reasons:
            parts.append(" ".join(_sentence(r) for r in reasons))
        return " ".join(_sentence(p) for p in parts)

    parts = [f"Yes - {exercise} passes every safety check for {name}"]
    if reasons:
        parts.append(" ".join(_sentence(r) for r in reasons))
    return " ".join(_sentence(p) for p in parts)


def _narrate_provenance(payload: dict[str, Any], name: str) -> str:
    exercise = payload.get("exercise_name", "That exercise")
    status = payload.get("status", "unknown")
    reasons = _reason_messages(payload)[:MAX_REASONS]

    verb = {
        "excluded": "was removed from consideration",
        "downranked": "was ranked down",
    }.get(status, "was kept")

    parts = [f"{exercise} {verb} for {name} by graph traversal"]
    if reasons:
        parts.append(" ".join(_sentence(r) for r in reasons))
    note = payload.get("evidence_note")
    if note and not payload.get("has_graph_path", True):
        parts.append(str(note))
    return " ".join(_sentence(p) for p in parts)


def _narrate_metric_trend(payload: dict[str, Any], name: str) -> str:
    metric = str(payload.get("metric", "that metric")).replace("_", " ")
    count = payload.get("count", 0)
    if not count:
        return _sentence(f"There are no {metric} observations recorded for {name}")

    unit = payload.get("unit")
    first = _format_value(payload.get("first_value"), unit)
    latest = _format_value(payload.get("latest_value"), unit)
    average = _format_value(payload.get("average_value"), unit)
    direction = str(payload.get("direction", "stable")).replace("_", " ")

    return _sentence(
        f"{name}'s {metric} moved from {first} to {latest} across {count} "
        f"observations ({direction}), averaging {average}"
    )


def _narrate_safe_candidates(payload: dict[str, Any], name: str) -> str:
    eligible = payload.get("eligible_count", 0)
    catalog = payload.get("catalog_count", 0)
    excluded = payload.get("excluded_count", 0)
    names = [
        c.get("name", "")
        for c in (payload.get("eligible_candidates") or [])
        if isinstance(c, dict) and c.get("name")
    ]

    if not eligible:
        return _sentence(
            f"No exercise in the {catalog}-item catalogue satisfies those "
            f"constraints for {name} once safety filtering is applied"
        )

    parts = [
        f"{eligible} of {catalog} catalogue exercises are safe for {name} here, "
        f"with {excluded} excluded outright"
    ]
    if names:
        parts.append(f"Best-ranked options: {_join_names(names)}")
    return " ".join(_sentence(p) for p in parts)


def _narrate_workout_request(payload: dict[str, Any], name: str) -> str:
    summary = payload.get("safety_summary") or {}
    catalog = summary.get("catalog_count", 0)
    excluded = summary.get("excluded_count", 0)
    eligible = summary.get("eligible_count", 0)
    downranked = summary.get("downranked_count", 0)

    excluded_names = [
        e.get("name", "")
        for e in (payload.get("excluded") or [])
        if isinstance(e, dict) and e.get("name")
    ]

    parts = [
        f"For that request, {eligible} of {catalog} exercises are eligible for "
        f"{name}, with {excluded} excluded and {downranked} ranked down"
    ]
    if excluded_names:
        parts.append(f"Excluded here: {_join_names(excluded_names)}")
    return " ".join(_sentence(p) for p in parts)


def _narrate_member_context(payload: dict[str, Any], name: str) -> str:
    parts: list[str] = []
    age, tier = payload.get("age"), payload.get("tier")
    if age and tier:
        parts.append(f"{name} is a {age}-year-old {tier} member")
    else:
        parts.append(f"{name} is on record")

    injuries = [
        i.get("region", "")
        for i in (payload.get("injuries") or [])
        if isinstance(i, dict) and i.get("region")
    ]
    parts.append(
        f"Active injury: {_join_names(injuries)}" if injuries else "No active injuries recorded"
    )

    adherence = payload.get("adherence") or {}
    if adherence.get("has_data"):
        parts.append(
            f"Latest adherence {adherence.get('latest')}% ({adherence.get('direction')})"
        )
    equipment = payload.get("equipment_available") or []
    if equipment:
        parts.append(f"Equipment: {_join_names(equipment)}")
    return " ".join(_sentence(p) for p in parts)


def _narrate_concepts(payload: dict[str, Any], name: str) -> str:
    resolved = [
        f"'{c.get('source_text')}' as {c.get('label')}"
        for c in (payload.get("concepts") or [])
        if isinstance(c, dict) and c.get("label")
    ]
    unresolved = [
        f"'{c.get('source_text')}'"
        for c in (payload.get("unresolved") or [])
        if isinstance(c, dict) and c.get("source_text")
    ]
    parts: list[str] = []
    if resolved:
        parts.append(f"Recognised {_join_names(resolved)}")
    if unresolved:
        parts.append(f"Could not match {_join_names(unresolved)} to the ontology")
    return " ".join(_sentence(p) for p in parts) if parts else ""


_NARRATORS = {
    "evaluate_exercise_safety": _narrate_exercise_safety,
    "get_exercise_provenance": _narrate_provenance,
    "get_member_metric_trend": _narrate_metric_trend,
    "get_safe_exercise_candidates": _narrate_safe_candidates,
    "evaluate_workout_request": _narrate_workout_request,
    "get_member_context": _narrate_member_context,
    "resolve_coach_concepts": _narrate_concepts,
}

#: Narration order. A direct verdict leads; supporting context follows.
_PRIORITY = (
    "evaluate_exercise_safety",
    "get_exercise_provenance",
    "evaluate_workout_request",
    "get_safe_exercise_candidates",
    "get_member_metric_trend",
    "resolve_coach_concepts",
    "get_member_context",
)


def narrate(results: list[ToolResult], member_name: str) -> str:
    """Render authoritative tool results as concise coach-facing prose."""
    usable = [r for r in results if r.ok and r.name in _NARRATORS]
    if not usable:
        return (
            "Safety evidence was retrieved, but there was nothing in it to "
            "summarise for this question."
        )

    ordered = sorted(
        usable,
        key=lambda r: _PRIORITY.index(r.name) if r.name in _PRIORITY else len(_PRIORITY),
    )

    # "Can she do X?" plans both the verdict and its provenance for the same
    # exercise. Narrating both repeats the same reason messages, so the
    # provenance result contributes its graph paths to the evidence panel only.
    verdict_exercises = {
        r.payload.get("exercise_id")
        for r in ordered
        if r.name == "evaluate_exercise_safety"
    }

    chunks: list[str] = []
    for result in ordered:
        if (
            result.name == "get_exercise_provenance"
            and result.payload.get("exercise_id") in verdict_exercises
        ):
            continue
        text = _NARRATORS[result.name](result.payload, member_name)
        if text:
            chunks.append(text)

    narrative = " ".join(chunks).strip()
    return narrative or (
        "Safety evidence was retrieved, but there was nothing in it to "
        "summarise for this question."
    )


# --- evidence projection -----------------------------------------------------

_EVIDENCE_SOURCES = ("evaluate_exercise_safety", "get_exercise_provenance")


def build_safety_evidence(results: list[ToolResult]) -> SafetyEvidence | None:
    """Merge the verdict and its provenance into one display-ready object."""
    relevant = [r for r in results if r.ok and r.name in _EVIDENCE_SOURCES]
    if not relevant:
        return None

    exercise_name = ""
    decision = ""
    reasons: list[EvidenceReason] = []
    rule_ids: list[str] = []
    graph_paths: list[str] = []
    note: str | None = None

    for result in relevant:
        payload = result.payload
        exercise_name = exercise_name or str(payload.get("exercise_name") or "")
        decision = decision or str(payload.get("status") or "")

        for reason in payload.get("reasons") or []:
            if not isinstance(reason, dict):
                continue
            message = reason.get("message")
            rule_id = reason.get("rule_id", "")
            if isinstance(message, str) and not any(r.message == message for r in reasons):
                reasons.append(EvidenceReason(rule_id=str(rule_id), message=message))
            # Reason-level evidence is already a rendered traversal string.
            for line in reason.get("evidence") or []:
                if isinstance(line, str) and line not in graph_paths:
                    graph_paths.append(line)

        for rule_id in payload.get("rule_ids") or []:
            if isinstance(rule_id, str) and rule_id not in rule_ids:
                rule_ids.append(rule_id)

        for path in payload.get("graph_paths") or []:
            rendered = path.get("rendered") if isinstance(path, dict) else None
            if isinstance(rendered, str) and rendered not in graph_paths:
                graph_paths.append(rendered)

        if not payload.get("has_graph_path", True) and payload.get("evidence_note"):
            note = str(payload["evidence_note"])

    if not exercise_name:
        return None

    return SafetyEvidence(
        exercise_name=exercise_name,
        decision=decision or "unknown",
        reasons=reasons[:MAX_REASONS],
        rule_ids=rule_ids,
        graph_paths=graph_paths[:MAX_GRAPH_PATHS],
        evidence_note=note,
    )


__all__ = [
    "EvidenceReason",
    "SafetyEvidence",
    "build_safety_evidence",
    "looks_like_raw_payload",
    "narrate",
]
