"""HTTP routes."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, HTTPException

from app.agents.adjustment import adjust_workout
from app.agents.intent import parse_intent
from app.api.deps import get_services
from app.api.schemas import (
    AdjustWorkoutRequest,
    AdjustWorkoutResponse,
    CopilotChatResponse,
    CopilotRequest,
    ExerciseProvenanceResponse,
    GenerateWorkoutRequest,
    GenerateWorkoutResponse,
    GraphSafetyResponse,
    HealthResponse,
    MemberHistoryResponse,
    MemberSummaryResponse,
    SafetySummary,
)
from app.copilot import analytics
from app.domain.evaluation import EvaluationHistory, EvaluationRun
from app.domain.graph_explorer import (
    EXPLORABLE_KINDS,
    RELATIONSHIP_GLOSSARY,
    GraphLegendResponse,
    GraphNodeView,
    GraphSearchResponse,
    GraphStatsResponse,
    GraphSubgraph,
    RelationshipGlossaryEntry,
)
from app.domain.ontology import ConceptGrounding, OntologyGroundingReport
from app.domain.trace import AdjustmentTraceSummary, RequestTrace, TraceListResponse
from app.domain.workout import WorkoutRequest
from app.evaluation.artifacts import EvaluationArtifactStore
from app.member.trajectory import MemberTrajectoryService
from app.observability.collector import (
    build_copilot_trace,
    build_workflow_trace,
    graph_call_scope,
)
from app.ontology.grounding import build_grounding_report, to_concept_grounding
from app.ontology.loader import get_ontology
from app.provenance.graph_trace import build_graph_reasoning
from app.safety.ranking import rank_candidates
from app.safety.validator import UnsafePlanError

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    services = get_services()
    bootstrap = services.bootstrap
    stats = services.repository.stats()
    return HealthResponse(
        status="ok",
        graph_backend=services.backend,
        llm_provider=getattr(services.llm, "name", "unknown"),
        graph_stats=stats,
        environment=services.settings.environment,
        graph_seeded=bool(bootstrap and bootstrap.seeded),
        seed_version=bootstrap.seed_version if bootstrap else None,
        ontology_mappings=stats.get("node:OntologyConcept", 0),
    )


@router.post("/workouts/generate", response_model=GenerateWorkoutResponse)
async def generate_workout(payload: GenerateWorkoutRequest) -> GenerateWorkoutResponse:
    services = get_services()
    request_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()

    try:
        with graph_call_scope() as graph_calls:
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

    services.traces.record(
        build_workflow_trace(
            request_id=request_id,
            workflow="generate",
            member_id=payload.member_id,
            state=state,
            total_duration_ms=timings["total"],
            llm_provider=state.get("generator"),
            graph_query_count=graph_calls.count,
        )
    )

    return _workout_response(GenerateWorkoutResponse, state, request_id, timings, services)


def _workout_response(model, state, request_id: str, timings: dict, services, **extra):
    """Project workflow state onto a response model.

    Shared by generation and adjustment so an adjusted plan cannot drift from a
    generated one: both report the same provenance, the same safety summary and
    the same graph reasoning, because both ran the same pipeline.
    """
    provenance = state["provenance"]
    report = state["post_validation"]

    return model(
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
        trajectory=state.get("trajectory"),
        **extra,
    )


@router.post("/workouts/adjust", response_model=AdjustWorkoutResponse)
async def adjust_workout_route(payload: AdjustWorkoutRequest) -> AdjustWorkoutResponse:
    """Apply a coach adjustment by re-running the whole deterministic pipeline.

    The model never edits the previous plan. The adjustment becomes part of a
    new coach request, so every safety decision is re-derived from the graph -
    which is the only way "avoid anything that stresses her knee" can be
    answered by traversal rather than by the model's reading of the sentence.
    """
    services = get_services()

    try:
        with graph_call_scope() as graph_calls:
            outcome = await adjust_workout(
                services=services,
                member_id=payload.member_id,
                base_prompt=payload.base_prompt,
                adjustment=payload.adjustment,
                base_duration=payload.duration_minutes,
                previous_exercise_ids=payload.previous_exercise_ids,
            )
    except UnsafePlanError as exc:
        logger.warning("adjustment produced no safe plan: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    state = outcome["state"]
    diff = outcome["diff"]
    timings = dict(state.get("timings") or {})
    timings["total"] = outcome["elapsed_ms"]

    logger.info(
        "adjust request_id=%s member=%s removed=%d added=%d downranked=%d "
        "newly_excluded=%d total_ms=%.1f",
        outcome["request_id"],
        payload.member_id,
        diff.counts.get("removed", 0),
        diff.counts.get("added", 0),
        diff.counts.get("downranked", 0),
        diff.counts.get("newly_excluded", 0),
        timings["total"],
    )

    services.traces.record(
        build_workflow_trace(
            request_id=outcome["request_id"],
            workflow="adjust",
            member_id=payload.member_id,
            state=state,
            total_duration_ms=timings["total"],
            llm_provider=state.get("generator"),
            graph_query_count=graph_calls.count,
            adjustment=AdjustmentTraceSummary(
                # The instruction text is not recorded - only what it changed.
                removed_count=diff.counts.get("removed", 0),
                added_count=diff.counts.get("added", 0),
                downranked_count=diff.counts.get("downranked", 0),
                retained_count=diff.counts.get("retained", 0),
                newly_excluded_count=diff.counts.get("newly_excluded", 0),
                duration_minutes=outcome["duration_minutes"],
                baseline_rerun_ms=outcome.get("baseline_rerun_ms"),
            ),
        )
    )

    return _workout_response(
        AdjustWorkoutResponse,
        state,
        outcome["request_id"],
        timings,
        services,
        adjustment=payload.adjustment,
        effective_prompt=outcome["effective_prompt"],
        diff=diff,
    )


@router.post("/copilot/chat", response_model=CopilotChatResponse)
async def copilot_chat(payload: CopilotRequest) -> CopilotChatResponse:
    services = get_services()
    member = services.repository.get_member_context(payload.member_id)
    if member is None:
        raise HTTPException(status_code=404, detail=f"Unknown member {payload.member_id}")

    started = time.perf_counter()
    with graph_call_scope() as graph_calls:
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

    services.traces.record(
        build_copilot_trace(
            request_id=uuid.uuid4().hex[:12],
            member_id=payload.member_id,
            # The classified intent, never the coach's question.
            intent=response.intent,
            total_duration_ms=latency,
            grounding=grounding,
            generator=response.generator,
            graph_query_count=graph_calls.count,
        )
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

    # Grounding for the concepts this exercise actually touches, deduplicated by
    # local id. Regions come from the traversal (including the ancestors the
    # closure walks), muscles from the catalog's own labels.
    grounding: dict[str, ConceptGrounding] = {}
    region_ids = [*regions, *(a for r in regions for a in ontology.ancestors_of(r))]
    for local_id in [
        *(f"anatomy:{region}" for region in region_ids),
        *(f"muscle:{muscle}" for muscle in exercise.muscle_groups),
    ]:
        projected = to_concept_grounding(ontology.grounding_for(local_id))
        if projected is not None and local_id not in grounding:
            grounding[local_id] = projected

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
        grounding=list(grounding.values()),
    )


@router.get("/graph/stats")
def graph_stats() -> dict[str, int]:
    return get_services().repository.stats()


# --- knowledge graph explorer (read-only) ------------------------------------
#
# An application feature, not a database console. There is deliberately no
# endpoint here that accepts a query language: the client names a node and a
# depth, and the API owns the shape of every traversal. Nothing here writes,
# and no Bolt URI, credential or raw driver object crosses the boundary.


@router.get("/graph/search", response_model=GraphSearchResponse)
def graph_search(q: str, kinds: str | None = None, limit: int = 10) -> GraphSearchResponse:
    """Ranked node matches by label, id or alias.

    Distinct from concept *resolution*: the resolver must pick one canonical
    concept and refuse when unsure, because a wrong pick applies a wrong safety
    rule. Search has no such consequence, so it returns candidates and lets a
    human choose - and never auto-selects a weak match.
    """
    selected = [k for k in (kinds or "").split(",") if k] or None
    return get_services().repository.search_nodes(q, kinds=selected, limit=limit)


@router.get("/graph/nodes/{node_id}", response_model=GraphNodeView)
def graph_node(node_id: str) -> GraphNodeView:
    node = get_services().repository.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Unknown graph node {node_id}")
    return node


@router.get("/graph/nodes/{node_id}/neighborhood", response_model=GraphSubgraph)
def graph_neighborhood(
    node_id: str,
    depth: int = 1,
    relationships: str | None = None,
    kinds: str | None = None,
) -> GraphSubgraph:
    """Bounded expansion from one node. Depth and node count are clamped."""
    services = get_services()
    if services.repository.get_node(node_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown graph node {node_id}")

    return services.repository.get_neighborhood(
        node_id,
        depth=depth,
        relationship_types=[r for r in (relationships or "").split(",") if r] or None,
        node_kinds=[k for k in (kinds or "").split(",") if k] or None,
    )


@router.get("/graph/summary", response_model=GraphStatsResponse)
def graph_summary() -> GraphStatsResponse:
    """Counts computed from the seeded graph, never from the brief."""
    services = get_services()
    graph = services.repository.graph()

    # Counted over what the explorer can actually reach, so the summary
    # describes the browsable graph rather than advertising nodes the API
    # deliberately refuses to serve.
    explorable = {
        key for key, node in graph.nodes.items() if node.label in EXPLORABLE_KINDS
    }

    nodes_by_kind: dict[str, int] = {}
    for key in explorable:
        label = graph.nodes[key].label
        nodes_by_kind[label] = nodes_by_kind.get(label, 0) + 1

    edges_by_relationship: dict[str, int] = {}
    for edge in graph.edges:
        if edge.source in explorable and edge.target in explorable:
            edges_by_relationship[edge.type] = edges_by_relationship.get(edge.type, 0) + 1

    return GraphStatsResponse(
        graph_backend=services.backend,
        node_count=len(explorable),
        edge_count=sum(edges_by_relationship.values()),
        nodes_by_kind=dict(sorted(nodes_by_kind.items())),
        edges_by_relationship=dict(sorted(edges_by_relationship.items())),
        ontology_mappings=nodes_by_kind.get("OntologyConcept", 0),
    )


@router.get("/graph/legend", response_model=GraphLegendResponse)
def graph_legend() -> GraphLegendResponse:
    """Relationship semantics, with how often each actually occurs."""
    graph = get_services().repository.graph()
    explorable = {
        key for key, node in graph.nodes.items() if node.label in EXPLORABLE_KINDS
    }
    counts: dict[str, int] = {}
    for edge in graph.edges:
        if edge.source in explorable and edge.target in explorable:
            counts[edge.type] = counts.get(edge.type, 0) + 1

    return GraphLegendResponse(
        node_kinds=sorted(
            {graph.nodes[key].label for key in explorable}
        ),
        relationships=[
            RelationshipGlossaryEntry(
                relationship=relationship,
                description=RELATIONSHIP_GLOSSARY.get(
                    relationship, "Relationship present in the graph."
                ),
                count=count,
            )
            for relationship, count in sorted(counts.items())
        ],
    )


@router.get("/graph/safety/{exercise_id}", response_model=GraphSafetyResponse)
def graph_safety(
    exercise_id: str,
    member_id: str = "mbr_01HX9JORDAN",
    prompt: str = "Create a 45-minute lower-body workout. Her left knee is bothering her.",
) -> GraphSafetyResponse:
    """One exercise's safety decision, computed by the existing engine.

    The explorer derives no safety of its own. It calls the same
    ``SafetyEngine`` the workout pipeline calls and projects the result through
    the same ``build_graph_reasoning``, so the paths rendered here are the
    paths that produced the decision.
    """
    services = get_services()
    member = services.repository.get_member_context(member_id)
    if member is None:
        raise HTTPException(status_code=404, detail=f"Unknown member {member_id}")

    node = services.repository.get_node(exercise_id)
    resolved_id = node.properties.get("id") if node else exercise_id
    exercise = services.repository.get_exercise(str(resolved_id))
    if exercise is None:
        raise HTTPException(status_code=404, detail=f"Unknown exercise {exercise_id}")

    intent, resolved = parse_intent(prompt, 45, services.resolver)
    context = services.engine.build_context(member, intent, resolved)
    decision = services.engine.evaluate(exercise, context)

    trajectory_service = services.trajectory or MemberTrajectoryService(services.ontology)
    trajectory = trajectory_service.analyze(member)
    candidates = rank_candidates(
        services.repository.list_exercises(),
        {decision.exercise_id: decision},
        member,
        intent,
        resolved,
        services.ontology,
        trajectory=trajectory,
    )
    candidate = next((c for c in candidates if c.exercise.id == exercise.id), None)

    reasoning = build_graph_reasoning(
        trace_id=uuid.uuid4().hex[:12],
        graph_backend=services.backend,
        decisions={decision.exercise_id: decision},
        candidates=[],
        resolved_concepts=resolved,
        member_facts=[],
        in_plan_count=0,
        ontology=services.ontology,
    )

    return GraphSafetyResponse(
        member_id=member.profile.id,
        member_name=member.profile.name,
        exercise_id=exercise.id,
        exercise_name=exercise.name,
        prompt=prompt,
        decision=decision.status,
        rule_ids=[r.rule_id for r in decision.reasons],
        reasons=decision.reason_messages(),
        traversals=reasoning.traversals,
        score_adjustment=decision.score_adjustment,
        longitudinal_adjustment=candidate.longitudinal_adjustment if candidate else 0.0,
        longitudinal_reasons=list(candidate.longitudinal_reasons) if candidate else [],
        eligible=not decision.is_excluded,
    )


# --- system quality (developer / operator surface) ---------------------------
#
# Read-only. These serve the System Quality dashboard, which answers "how is the
# system performing overall?" - deliberately separate from the coach surface,
# which answers "what happened for this workout?".


@router.get("/system/evaluations/latest", response_model=EvaluationRun | None)
def latest_evaluation() -> EvaluationRun | None:
    """The most recent evaluation artifact, or null if none has been run."""
    return EvaluationArtifactStore().latest()


@router.get("/system/evaluations", response_model=EvaluationHistory)
def evaluation_history(limit: int = 10) -> EvaluationHistory:
    return EvaluationArtifactStore().history(limit=max(1, min(limit, 50)))


@router.get("/system/evaluations/{run_id}", response_model=EvaluationRun)
def evaluation_run(run_id: str) -> EvaluationRun:
    try:
        run = EvaluationArtifactStore().get(run_id)
    except ValueError as exc:
        # Run ids become file names, so a malformed one is rejected outright
        # rather than being allowed anywhere near a path join.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=404, detail=f"Unknown evaluation run {run_id}")
    return run


@router.get("/system/traces", response_model=TraceListResponse)
def recent_traces(limit: int = 25) -> TraceListResponse:
    services = get_services()
    traces = services.traces.recent(limit=max(1, min(limit, 100)))
    return TraceListResponse(
        traces=traces, count=len(traces), capacity=services.traces.capacity
    )


@router.get("/system/traces/{request_id}", response_model=RequestTrace)
def trace_detail(request_id: str) -> RequestTrace:
    trace = get_services().traces.get(request_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"Unknown request {request_id}")
    return trace


@router.get("/ontology/grounding", response_model=OntologyGroundingReport)
def ontology_grounding() -> OntologyGroundingReport:
    """The full mapping set: what is grounded in a published ontology, and what is not.

    Deliberately exposes both halves. The unmapped register is what makes the
    mapped half auditable - a reviewer can see every concept that was
    considered and the reason no identifier was recorded, rather than having to
    infer it from absence.
    """
    return build_grounding_report(get_ontology())
