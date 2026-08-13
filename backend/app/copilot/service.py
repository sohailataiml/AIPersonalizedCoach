"""Coach AI Copilot.

Retrieval order is strict and is the whole point:

    classify intent -> query the member graph for that slice -> compute
    deterministic analytics -> hand a *compact* evidence object to the LLM ->
    return a grounded answer plus a chart payload built in Python.

The member JSON is never dumped wholesale into a prompt. Each intent retrieves
only the slice it needs, which keeps token usage low and, more importantly,
means the model cannot "answer" from data the coach did not ask about.

Every answer carries citations naming the member-graph fields it came from. When
the graph has no data for a question, we say so instead of letting the model
improvise - the failure mode we care most about is a confident invented fact.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.copilot import analytics
from app.copilot.mcp_gateway import McpGateway, McpUnavailableError, ToolResult
from app.copilot.mcp_narrator import (
    SafetyEvidence,
    build_safety_evidence,
    looks_like_raw_payload,
    narrate,
)
from app.copilot.tool_router import (
    MAX_TOOL_CALLS,
    SAFETY_TOOLS,
    SafetyVerdictGuard,
    plan_tools,
)
from app.domain.member import MemberContext
from app.llm.base import LLMClient, LLMError

logger = logging.getLogger(__name__)


def _citation_detail(result: ToolResult) -> str:
    """A short, honest description of what a tool actually returned."""
    payload = result.payload
    if "status" in payload and "exercise_name" in payload:
        return f"{payload['exercise_name']}: {payload['status']} (deterministic)"
    if "metric" in payload:
        return f"{payload.get('count', 0)} observations of {payload['metric']}"
    if "eligible_count" in payload:
        return (
            f"{payload.get('eligible_count', 0)} eligible of "
            f"{payload.get('catalog_count', 0)} after graph filtering"
        )
    return "graph-derived result"

CopilotIntent = Literal[
    "SHOW_BRIEF",
    "ADHERENCE_TREND",
    "SLEEP_WEEK",
    "WHAT_CHANGED",
    "CHURN_RISK",
    "MESSAGE_PATTERN",
    "WORKOUT_HISTORY",
    "LABS",
    "GENERAL_MEMBER_QA",
]

SYSTEM_PROMPT = """You are a coaching assistant summarizing ONE member's data for their coach.

RULES
1. Use only facts present in the <evidence> block. Never add numbers, dates or
   events that are not there.
2. If the evidence does not answer the question, say so plainly.
3. Be concise: 2-4 sentences, in the voice of a knowledgeable colleague.
4. Refer to the member by first name.
5. Do not give medical advice or diagnose."""


class ChartSeries(BaseModel):
    name: str
    values: list[float]


class ChartPayload(BaseModel):
    type: Literal["line", "bar"]
    title: str
    x: list[str]
    series: list[ChartSeries]
    y_label: str | None = None
    y_domain: list[float] | None = None


class Citation(BaseModel):
    source: str
    detail: str


class Grounding(BaseModel):
    """How this answer was obtained. Optional, so existing clients are unaffected."""

    mode: Literal["mcp", "fallback"] = "fallback"
    tools_used: list[str] = Field(default_factory=list)
    authoritative_safety: bool = False
    safety_corrected: bool = Field(
        default=False,
        description="True when a model claim was overridden by a graph verdict.",
    )


class CopilotResponse(BaseModel):
    intent: CopilotIntent
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    chart: ChartPayload | None = None
    #: The structured tool payloads, verbatim. Machine-readable detail for
    #: debugging and replay - never the source of the visible answer.
    evidence: dict = Field(default_factory=dict)
    grounded: bool = True
    generator: str = "stub"
    grounding: Grounding | None = None
    #: Display-ready projection of an authoritative verdict, so the UI can show
    #: what happened without opening `evidence`.
    safety_evidence: SafetyEvidence | None = None


# --- intent classification ---------------------------------------------------

_KEYWORDS: list[tuple[CopilotIntent, tuple[str, ...]]] = [
    ("SHOW_BRIEF", ("brief", "morning", "today", "summary for today", "what should i do")),
    ("ADHERENCE_TREND", ("adherence", "consistency", "completion", "compliance", "showing up")),
    ("SLEEP_WEEK", ("sleep", "rest", "sleeping", "bedtime")),
    ("WHAT_CHANGED", ("what changed", "since last week", "difference", "changed")),
    ("CHURN_RISK", ("churn", "risk", "cancel", "drop off", "dropping off", "disengag")),
    ("MESSAGE_PATTERN", ("message", "chat", "conversation", "said", "talking", "texts")),
    ("WORKOUT_HISTORY", ("workout", "session", "training history", "last workout", "rpe")),
    ("LABS", ("lab", "blood", "dexa", "ldl", "hdl", "body fat", "biomarker", "hrv", "resting hr")),
]


def classify(message: str) -> CopilotIntent:
    lowered = message.lower()
    # "What changed since last week" mentions several nouns; check it first.
    for intent, keywords in _KEYWORDS:
        if intent == "WHAT_CHANGED" and any(k in lowered for k in keywords):
            return intent
    for intent, keywords in _KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return intent
    return "GENERAL_MEMBER_QA"


# --- service -----------------------------------------------------------------


MCP_SYSTEM_PROMPT = """You are a coaching assistant summarizing tool results for a coach.

AUTHORITY
1. Safety results from the tools are authoritative. Never override, soften or
   re-argue an excluded or downranked decision.
2. Never invent member facts, numbers, or graph relationships. Use only the
   tool output supplied.
3. Summarize graph evidence when it explains a decision.
4. If the evidence does not answer the question, say so plainly.

STYLE
Concise: 2-4 sentences, in the voice of a knowledgeable colleague. Refer to the
member by first name. Do not give medical advice or diagnose."""


class CopilotService:
    """MCP-first, with the deterministic dispatcher retained as fallback.

    Normal path::

        question -> tool plan -> MCP client -> MCP server -> same services
                 -> authoritative result -> LLM phrases it -> guard checks it

    Fallback path (MCP unreachable) re-uses the original ``_retrieve``
    dispatcher, which calls the *same* domain services directly. That matters
    for safety questions specifically: a failure must degrade to the local
    deterministic engine, never to free-form model judgement.
    """

    def __init__(
        self,
        llm: LLMClient,
        gateway: McpGateway | None = None,
        catalog: dict[str, str] | None = None,
    ) -> None:
        self._llm = llm
        self._gateway = gateway
        self._catalog = catalog or {}

    # --- MCP-first entry point -------------------------------------------

    async def answer(self, member: MemberContext, message: str) -> CopilotResponse:
        if self._gateway is not None:
            try:
                return await self._answer_via_mcp(member, message)
            except McpUnavailableError as exc:
                logger.warning(
                    "mcp unavailable, falling back to deterministic dispatcher: %s", exc
                )
        return await self._answer_via_dispatcher(member, message)

    async def _answer_via_mcp(
        self, member: MemberContext, message: str
    ) -> CopilotResponse:
        assert self._gateway is not None
        member_id = member.profile.id
        intent = classify(message)

        plan = plan_tools(message, member_id, self._catalog)
        calls = plan.calls[:MAX_TOOL_CALLS]  # hard bound, plan is not iterative
        results = await self._gateway.call_many(calls)

        ok_results = [r for r in results if r.ok]
        if not ok_results:
            # Every tool errored. For a safety question this must not become a
            # model opinion, so fall through to the local deterministic path.
            raise McpUnavailableError("no MCP tool returned a usable result")

        evidence = {r.name: r.payload for r in ok_results}
        first_name = member.profile.name.split()[0]

        # Deterministic prose built from the authoritative payloads. It is the
        # scaffold the model phrases, the offline answer when no provider is
        # configured, and the replacement if a provider returns something
        # unusable. The structured results travel alongside it either way.
        narrative = narrate(ok_results, first_name)
        answer = await self._summarize(
            message,
            # `summary` is the convention every evidence block in this service
            # uses; a provider that can only echo evidence therefore echoes
            # sentences rather than payloads.
            {"summary": narrative, "tool_results": evidence},
            system=MCP_SYSTEM_PROMPT,
            fallback=narrative,
        )

        # Last line of defence against a payload reaching the coach. Cheap, and
        # it fails toward the deterministic narration rather than toward prose
        # nobody wrote.
        if not answer.strip() or looks_like_raw_payload(answer):
            logger.warning(
                "llm returned unusable prose for an MCP answer (generator=%s); "
                "using deterministic narration",
                getattr(self._llm, "name", "unknown"),
            )
            answer = narrative

        answer, corrected = SafetyVerdictGuard.enforce(answer, ok_results)

        citations = [
            Citation(source=f"MCP tool: {r.name}", detail=_citation_detail(r))
            for r in ok_results
        ]
        # Charts stay deterministic: built in Python from the member graph.
        _, _, chart = self._retrieve(intent, member, message)

        return CopilotResponse(
            intent=intent,
            answer=answer,
            citations=citations,
            chart=chart,
            evidence=evidence,
            safety_evidence=build_safety_evidence(ok_results),
            generator=getattr(self._llm, "name", "unknown"),
            grounding=Grounding(
                mode="mcp",
                tools_used=[r.name for r in results],
                authoritative_safety=plan.touches_safety
                and any(r.name in SAFETY_TOOLS and r.ok for r in results),
                safety_corrected=corrected,
            ),
        )

    # --- original deterministic dispatcher (fallback) ---------------------

    async def _answer_via_dispatcher(
        self, member: MemberContext, message: str
    ) -> CopilotResponse:
        intent = classify(message)
        evidence, citations, chart = self._retrieve(intent, member, message)

        if not evidence.get("has_data", True):
            # No data for this question: refuse rather than let the model fill in.
            return CopilotResponse(
                intent=intent,
                answer=evidence.get(
                    "summary", "I don't have that data for this member."
                ),
                citations=citations,
                chart=None,
                evidence=evidence,
                grounded=True,
                generator="deterministic",
                grounding=Grounding(mode="fallback", tools_used=[]),
            )

        answer = await self._summarize(message, evidence)
        return CopilotResponse(
            intent=intent,
            answer=answer,
            citations=citations,
            chart=chart,
            evidence=evidence,
            generator=getattr(self._llm, "name", "unknown"),
            grounding=Grounding(mode="fallback", tools_used=[]),
        )

    async def _summarize(
        self,
        message: str,
        evidence: dict,
        system: str = SYSTEM_PROMPT,
        fallback: str | None = None,
    ) -> str:
        try:
            return await self._llm.answer_grounded(
                system=system,
                user=message,
                evidence=json.dumps(evidence, indent=2, default=str),
            )
        except LLMError:
            # Degrade to the deterministic summary rather than failing the request.
            if fallback is not None:
                return fallback
            return str(evidence.get("summary", "Unable to generate a summary."))

    # --- retrieval per intent ------------------------------------------

    def _retrieve(
        self, intent: CopilotIntent, member: MemberContext, message: str
    ) -> tuple[dict, list[Citation], ChartPayload | None]:
        name = member.profile.name.split()[0]

        if intent == "ADHERENCE_TREND":
            return self._adherence(member, name)
        if intent == "SLEEP_WEEK":
            return self._sleep(member, name)
        if intent == "SHOW_BRIEF":
            return self._brief(member, name)
        if intent == "CHURN_RISK":
            return self._churn(member, name)
        if intent == "WHAT_CHANGED":
            return self._changed(member, name)
        if intent == "MESSAGE_PATTERN":
            return self._messages(member, name)
        if intent == "WORKOUT_HISTORY":
            return self._history(member, name)
        if intent == "LABS":
            return self._labs(member, name)
        return self._general(member, name)

    def _adherence(self, member, name):
        trend = analytics.adherence_trend(member)
        if not trend.has_data:
            return {"has_data": False, "summary": f"No adherence data recorded for {name}."}, [], None

        evidence = {
            "metric": "weekly_completion_pct",
            "weeks": trend.labels,
            "values": trend.values,
            "latest_pct": trend.latest,
            "first_pct": trend.first,
            "delta_pct": trend.delta,
            "direction": trend.direction,
            "average_pct": trend.average,
            "recorded_trend_label": member.adherence.trend,
            "summary": (
                f"{name}'s weekly completion went from {trend.first}% to {trend.latest}% "
                f"across {len(trend.values)} weeks ({trend.direction}, "
                f"{trend.delta:+.0f} points)."
            ),
        }
        chart = ChartPayload(
            type="line",
            title="Weekly adherence",
            x=[f"Week of {label}" for label in trend.labels],
            series=[ChartSeries(name="Completion %", values=trend.values)],
            y_label="%",
            y_domain=[0, 100],
        )
        citations = [
            Citation(
                source="Member graph: AdherenceObservation",
                detail=f"{len(trend.values)} weekly observations ({trend.labels[0]} to {trend.labels[-1]})",
            )
        ]
        return evidence, citations, chart

    def _sleep(self, member, name):
        trend = analytics.sleep_trend(member)
        if not trend.has_data:
            return {"has_data": False, "summary": f"No sleep data recorded for {name}."}, [], None

        goal = next((g for g in member.goals if "sleep" in g.text.lower()), None)
        evidence = {
            "metric": "sleep_hours_last_7_days",
            "values": trend.values,
            "average_hours": trend.average,
            "min_hours": min(trend.values),
            "max_hours": max(trend.values),
            "direction": trend.direction,
            "nights_below_7": sum(1 for v in trend.values if v < 7),
            "related_goal": goal.text if goal else None,
            "summary": (
                f"{name} averaged {trend.average}h over the last {len(trend.values)} nights "
                f"(range {min(trend.values)}-{max(trend.values)}h); "
                f"{sum(1 for v in trend.values if v < 7)} of {len(trend.values)} nights were under 7h."
            ),
        }
        chart = ChartPayload(
            type="bar",
            title="Sleep - last 7 nights",
            x=trend.labels,
            series=[ChartSeries(name="Hours", values=trend.values)],
            y_label="hours",
            y_domain=[0, 10],
        )
        citations = [
            Citation(
                source="Member graph: BiomarkerObservation (sleep_hours)",
                detail=f"{len(trend.values)} nightly values",
            )
        ]
        return evidence, citations, chart

    def _brief(self, member, name):
        brief = member.coach_brief
        sessions = analytics.session_stats(member)
        adherence = analytics.adherence_trend(member)

        evidence = {
            "generated_for": brief.generated_for,
            "morning_tasks": [
                {"type": task.type, "text": task.text} for task in brief.morning_tasks
            ],
            "churn_level": brief.churn_risk.level if brief.churn_risk else None,
            "last_completed_session": sessions.last_completed_title,
            "last_completed_date": sessions.last_completed_date,
            "adherence_latest_pct": adherence.latest,
            "active_injuries": [i.region for i in member.injuries],
            "summary": (
                f"Brief for {brief.generated_for}: "
                + " ".join(task.text for task in brief.morning_tasks)
            ),
        }
        citations = [
            Citation(
                source="Member graph: CoachBrief",
                detail=f"{len(brief.morning_tasks)} morning task(s) for {brief.generated_for}",
            )
        ]
        return evidence, citations, None

    def _churn(self, member, name):
        assessment = analytics.churn_assessment(member)
        adherence = analytics.adherence_trend(member)

        evidence = {
            "level": assessment.level,
            "reasons": assessment.reasons,
            "source": assessment.source,
            "supporting_metrics": assessment.supporting_metrics,
            "summary": (
                f"{name}'s churn risk is recorded as {assessment.level}. "
                + " ".join(assessment.reasons)
            ),
        }
        chart = None
        if adherence.has_data:
            chart = ChartPayload(
                type="line",
                title="Adherence (churn indicator)",
                x=[f"Week of {label}" for label in adherence.labels],
                series=[ChartSeries(name="Completion %", values=adherence.values)],
                y_label="%",
                y_domain=[0, 100],
            )
        citations = [
            Citation(
                source="Member graph: ChurnSignal",
                detail=f"level={assessment.level}, {len(assessment.reasons)} recorded reason(s)",
            )
        ]
        return evidence, citations, chart

    def _changed(self, member, name):
        change = analytics.what_changed(member)
        if not change.changes:
            return {"has_data": False, "summary": f"No recent changes recorded for {name}."}, [], None

        evidence = {
            "changes": change.changes,
            "adherence_delta_pct": change.adherence_delta,
            "weeks_compared": change.weeks_compared,
            "summary": " ".join(change.changes),
        }
        citations = [
            Citation(
                source="Member graph: AdherenceObservation + WorkoutSession",
                detail=f"{change.weeks_compared} weeks compared",
            )
        ]
        return evidence, citations, None

    def _messages(self, member, name):
        messages = member.chat_history
        if not messages:
            return {"has_data": False, "summary": f"No chat history for {name}."}, [], None

        ordered = sorted(messages, key=lambda m: m.ts, reverse=True)
        by_sender: dict[str, int] = {}
        for message in messages:
            by_sender[message.sender] = by_sender.get(message.sender, 0) + 1

        evidence = {
            "total_messages": len(messages),
            "by_sender": by_sender,
            "latest": [
                {"ts": m.ts, "from": m.sender, "text": m.text} for m in ordered[:4]
            ],
            "attachments": [
                {"ts": m.ts, "caption": a.caption, "type": a.type}
                for m in messages
                for a in m.attachments
            ],
            "summary": (
                f"{len(messages)} messages on record "
                f"({', '.join(f'{k}: {v}' for k, v in by_sender.items())}). "
                f"Most recent from {ordered[0].sender} on {ordered[0].ts[:10]}."
            ),
        }
        chart = ChartPayload(
            type="bar",
            title="Messages by sender",
            x=list(by_sender.keys()),
            series=[ChartSeries(name="Messages", values=[float(v) for v in by_sender.values()])],
            y_label="count",
        )
        citations = [
            Citation(
                source="Member graph: ChatMessage",
                detail=f"{len(messages)} messages, {len(evidence['attachments'])} attachment(s)",
            )
        ]
        return evidence, citations, chart

    def _history(self, member, name):
        sessions = analytics.session_stats(member)
        if not member.workout_history:
            return {"has_data": False, "summary": f"No workout history for {name}."}, [], None

        evidence = {
            "completed": sessions.completed,
            "planned": sessions.planned,
            "completion_rate_pct": sessions.completion_rate,
            "total_minutes": sessions.total_minutes,
            "average_rpe": sessions.average_rpe,
            "last_completed": sessions.last_completed_title,
            "last_completed_date": sessions.last_completed_date,
            "missed_dates": sessions.missed_dates,
            "sessions": [
                {
                    "date": s.date,
                    "title": s.title,
                    "completed": s.completed,
                    "duration_min": s.duration_min,
                    "rpe": s.rpe,
                    "exercises": [e.name for e in s.exercises],
                }
                for s in member.workout_history
            ],
            "summary": (
                f"{sessions.completed} of {sessions.planned} planned sessions completed "
                f"({sessions.completion_rate}%), averaging RPE {sessions.average_rpe}. "
                f"Most recent: {sessions.last_completed_title} on {sessions.last_completed_date}."
            ),
        }
        chart = ChartPayload(
            type="bar",
            title="Session duration",
            x=[s.date for s in member.workout_history],
            series=[
                ChartSeries(
                    name="Minutes",
                    values=[float(s.duration_min) for s in member.workout_history],
                )
            ],
            y_label="minutes",
        )
        citations = [
            Citation(
                source="Member graph: WorkoutSession",
                detail=f"{len(member.workout_history)} sessions on record",
            )
        ]
        return evidence, citations, chart

    def _labs(self, member, name):
        labs = member.labs
        bio = member.biomarkers
        if not labs.blood_panel and not labs.dexa_scan:
            return {"has_data": False, "summary": f"No lab results for {name}."}, [], None

        evidence = {
            "blood_panel": labs.blood_panel.model_dump(exclude_none=True)
            if labs.blood_panel
            else None,
            "dexa_scan": labs.dexa_scan.model_dump(exclude_none=True)
            if labs.dexa_scan
            else None,
            "resting_hr_bpm": bio.resting_hr_bpm,
            "hrv_ms": bio.hrv_ms,
            "summary": _labs_summary(name, labs, bio),
        }
        citations = [
            Citation(
                source="Member graph: LabResult + DEXAResult",
                detail=f"blood panel {labs.blood_panel.date if labs.blood_panel else 'n/a'}, "
                f"DEXA {labs.dexa_scan.date if labs.dexa_scan else 'n/a'}",
            )
        ]
        return evidence, citations, None

    def _general(self, member, name):
        """A compact profile slice - still not the whole member JSON."""
        adherence = analytics.adherence_trend(member)
        sessions = analytics.session_stats(member)

        evidence = {
            "profile": {
                "name": member.profile.name,
                "age": member.profile.age,
                "tier": member.profile.tier,
                "member_since": member.profile.member_since,
            },
            "goals": [g.text for g in sorted(member.goals, key=lambda g: g.priority)],
            "injuries": [
                {"region": i.region, "status": i.status, "severity": i.severity, "notes": i.notes}
                for i in member.injuries
            ],
            "equipment": member.equipment_available,
            "preferences": {
                "session_minutes": member.preferences.preferred_session_minutes,
                "days_per_week": member.preferences.training_days_per_week,
                "dislikes": member.preferences.dislikes,
            },
            "adherence_latest_pct": adherence.latest,
            "adherence_direction": adherence.direction,
            "last_session": sessions.last_completed_title,
            "summary": (
                f"{name} is a {member.profile.age}-year-old {member.profile.tier} member. "
                f"Latest adherence {adherence.latest}% ({adherence.direction}). "
                f"Active injury: {member.injuries[0].region if member.injuries else 'none'}."
            ),
        }
        citations = [
            Citation(source="Member graph: Member profile slice", detail="goals, injuries, preferences")
        ]
        return evidence, citations, None


def _labs_summary(name: str, labs, bio) -> str:
    parts: list[str] = []
    if labs.blood_panel:
        panel = labs.blood_panel
        parts.append(
            f"Blood panel ({panel.date}): LDL {panel.ldl_mg_dl}, HDL {panel.hdl_mg_dl}, "
            f"HbA1c {panel.hba1c_pct}%, vitamin D {panel.vitamin_d_ng_ml} ng/mL."
        )
    if labs.dexa_scan:
        dexa = labs.dexa_scan
        parts.append(
            f"DEXA ({dexa.date}): {dexa.body_fat_pct}% body fat, "
            f"{dexa.lean_mass_kg} kg lean mass."
        )
    if bio.resting_hr_bpm or bio.hrv_ms:
        parts.append(f"Resting HR {bio.resting_hr_bpm} bpm, HRV {bio.hrv_ms} ms.")
    return f"{name}: " + " ".join(parts)
