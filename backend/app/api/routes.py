"""HTTP routes."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, HTTPException

from app.api.deps import get_services
from app.api.schemas import (
    CopilotChatResponse,
    CopilotRequest,
    ExerciseProvenanceResponse,
    GenerateWorkoutRequest,
    GenerateWorkoutResponse,
    HealthResponse,
    MemberHistoryResponse,
    MemberSummaryResponse,
    SafetySummary,
)
from app.copilot import analytics
from app.domain.workout import WorkoutRequest
from app.ontology.loader import get_ontology
from app.safety.validator import UnsafePlanError

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    services = get_services()
    return HealthResponse(
        status="ok",
        graph_backend=services.backend,
        llm_provider=getattr(services.llm, "name", "unknown"),
        graph_stats=services.repository.stats(),
    )


@router.post("/workouts/generate", response_model=GenerateWorkoutResponse)
async def generate_workout(payload: GenerateWorkoutRequest) -> GenerateWorkoutResponse:
    services = get_services()
    request_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()

    try:
        state = await services.workflow.run(
            WorkoutRequest(
                member_id=payload.member_id,
                prompt=payload.prompt,
                duration_minutes=payload.duration_minutes,
            )
        )
    except UnsafePlanError as exc:
        # Fail closed: better to return nothing than an unvalidated plan.
        logger.warning("request_id=%s unsafe plan: %s", request_id, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    provenance = state["provenance"]
    report = state["post_validation"]
    timings = dict(state.get("timings") or {})
    timings["total"] = round((time.perf_counter() - started) * 1000, 2)

    logger.info(
        "request_id=%s member=%s resolved=%d unresolved=%d eligible=%d excluded=%d "
        "in_plan=%d rejections=%d total_ms=%.1f",
        request_id,
        payload.member_id,
        len(provenance.resolved_concepts),
        len(provenance.unresolved_concepts),
        provenance.counts.get("eligible", 0),
        provenance.counts.get("excluded", 0),
        provenance.counts.get("in_plan", 0),
        len(report.rejected),
        timings["total"],
    )

    return GenerateWorkoutResponse(
        request_id=request_id,
        workout=state["generated_workout"],
        resolved_concepts=provenance.resolved_concepts,
        unresolved_concepts=provenance.unresolved_concepts,
        filtered_exercises=provenance.filtered,
        provenance=provenance.included,
        member_facts=provenance.member_facts,
        safety=SafetySummary(
            catalog_total=provenance.counts.get("catalog_total", 0),
            eligible=provenance.counts.get("eligible", 0),
            excluded=provenance.counts.get("excluded", 0),
            downranked=provenance.counts.get("downranked", 0),
            in_plan=provenance.counts.get("in_plan", 0),
            post_validation_passed=report.passed,
            post_validation_rejections=len(report.rejected),
            post_validation_replacements=len(report.replacements),
        ),
        post_validation=report,
        timings_ms=timings,
        generator=state.get("generator", "unknown"),
        graph_backend=services.backend,
        graph_reasoning=state.get("graph_reasoning"),
    )


@router.post("/copilot/chat", response_model=CopilotChatResponse)
async def copilot_chat(payload: CopilotRequest) -> CopilotChatResponse:
    services = get_services()
    member = services.repository.get_member_context(payload.member_id)
    if member is None:
        raise HTTPException(status_code=404, detail=f"Unknown member {payload.member_id}")

    started = time.perf_counter()
    response = await services.copilot.answer(member, payload.message)
    latency = round((time.perf_counter() - started) * 1000, 2)

    grounding = response.grounding
    logger.info(
        "copilot member=%s intent=%s chart=%s mode=%s tools=%s latency_ms=%.1f",
        payload.member_id,
        response.intent,
        bool(response.chart),
        grounding.mode if grounding else "fallback",
        ",".join(grounding.tools_used) if grounding else "",
        latency,
    )

    return CopilotChatResponse(
        intent=response.intent,
        answer=response.answer,
        citations=response.citations,
        chart=response.chart,
        evidence=response.evidence,
        generator=response.generator,
        latency_ms=latency,
        grounding=grounding,
        safety_evidence=response.safety_evidence,
    )


@router.get("/members/{member_id}", response_model=MemberSummaryResponse)
def member_summary(member_id: str) -> MemberSummaryResponse:
    services = get_services()
    member = services.repository.get_member_context(member_id)
    if member is None:
        raise HTTPException(status_code=404, detail=f"Unknown member {member_id}")

    adherence = analytics.adherence_trend(member)
    sleep = analytics.sleep_trend(member)
    goals = sorted(member.goals, key=lambda g: g.priority)
    churn = member.coach_brief.churn_risk

    return MemberSummaryResponse(
        id=member.profile.id,
        name=member.profile.name,
        tier=member.profile.tier,
        age=member.profile.age,
        primary_goal=goals[0].text if goals else None,
        goals=goals,
        active_injuries=member.injuries,
        equipment_available=member.equipment_available,
        latest_adherence_pct=adherence.latest,
        adherence_trend=adherence.direction,
        churn_risk_level=churn.level if churn else None,
        churn_risk_reasons=list(churn.reasons) if churn else [],
        avg_sleep_hours=sleep.average,
        preferred_session_minutes=member.preferences.preferred_session_minutes,
        morning_tasks=[t.model_dump() for t in member.coach_brief.morning_tasks],
        brief_date=member.coach_brief.generated_for,
    )


@router.get("/members/{member_id}/history", response_model=MemberHistoryResponse)
def member_history(member_id: str) -> MemberHistoryResponse:
    services = get_services()
    member = services.repository.get_member_context(member_id)
    if member is None:
        raise HTTPException(status_code=404, detail=f"Unknown member {member_id}")

    sleep = analytics.sleep_trend(member)
    return MemberHistoryResponse(
        member_id=member.profile.id,
        sessions=[
            {
                "date": s.date,
                "title": s.title,
                "completed": s.completed,
                "planned": s.planned,
                "duration_min": s.duration_min,
                "rpe": s.rpe,
                "exercises": [e.name for e in s.exercises],
            }
            for s in member.workout_history
        ],
        chat=[
            {
                "ts": m.ts,
                "from": m.sender,
                "text": m.text,
                "attachments": [a.model_dump() for a in m.attachments],
            }
            for m in member.chat_history
        ],
        adherence=[
            {"week_of": o.week_of, "pct": o.pct}
            for o in member.adherence.weekly_completion_pct
        ],
        sleep=[
            {"label": label, "hours": value}
            for label, value in zip(sleep.labels, sleep.values, strict=False)
        ],
    )


@router.get(
    "/graph/exercises/{exercise_id}/provenance",
    response_model=ExerciseProvenanceResponse,
)
def exercise_provenance(exercise_id: str) -> ExerciseProvenanceResponse:
    """Graph-inspector endpoint: what the graph knows about one exercise."""
    services = get_services()
    exercise = services.repository.get_exercise(exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail=f"Unknown exercise {exercise_id}")

    ontology = get_ontology()
    regions = services.repository.exercise_stressed_regions(exercise_id)

    ancestors: list[str] = []
    for region in regions:
        for ancestor in ontology.ancestors_of(region):
            concept = ontology.anatomy.get(ancestor)
            if concept and concept.label not in ancestors:
                ancestors.append(concept.label)

    patterns = services.repository.exercise_patterns(exercise_id)
    families: list[str] = []
    for pattern in patterns:
        family = ontology.family_for_pattern(pattern)
        if family and family.label not in families:
            families.append(family.label)

    return ExerciseProvenanceResponse(
        exercise_id=exercise.id,
        name=exercise.name,
        targets=exercise.muscle_groups,
        stresses=[
            ontology.anatomy[r].label if r in ontology.anatomy else r for r in regions
        ],
        anatomy_ancestors=ancestors,
        requires=services.repository.exercise_required_equipment(exercise_id),
        patterns=patterns,
        families=families,
        is_unilateral=exercise.is_unilateral,
        side=exercise.side,
    )


@router.get("/graph/stats")
def graph_stats() -> dict[str, int]:
    return get_services().repository.stats()
