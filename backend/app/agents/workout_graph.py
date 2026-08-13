"""The workout generation workflow, orchestrated with LangGraph.

    load_member -> parse_intent -> resolve_concepts -> analyze_longitudinal_context
                -> evaluate_safety -> rank_candidates -> compose_workout
                -> validate_workout -> build_provenance

Only ``compose_workout`` touches the LLM. The rest are ordinary deterministic
functions, and they are modelled as explicit nodes rather than hidden inside one
another so the execution graph shows exactly where generative work happens and
where it does not. No node is dressed up as an "agent" for its own sake.

Note that ``resolve_concepts`` shares a node with ``parse_intent``: intent
parsing already routes every span through the resolver, so a separate node would
be theatre. The state still exposes ``resolved_concepts`` as its own field.

``analyze_longitudinal_context`` sits *before* ``evaluate_safety`` in the graph
because it describes the member, not the request - but the ordering is
presentational, not a dependency. The safety engine never receives the
trajectory. Only ``rank_candidates`` and ``compose_workout`` read it, which is
what keeps the priority order honest:

    hard safety > equipment > explicit exclusions > longitudinal > preferences
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.agents.intent import parse_intent
from app.agents.workout_planner import compose_workout_draft
from app.domain.exercise import ExerciseCandidate
from app.domain.graph_trace import GraphReasoning
from app.domain.member import MemberContext
from app.domain.resolution import ResolvedConcept
from app.domain.safety import SafetyDecision
from app.domain.trajectory import MemberTrajectory
from app.domain.workout import (
    GeneratedWorkout,
    LLMWorkoutDraft,
    PostValidationReport,
    WorkoutIntent,
    WorkoutRequest,
)
from app.graph.repository import GraphRepository
from app.llm.base import LLMClient
from app.member.trajectory import MemberTrajectoryService
from app.ontology.loader import Ontology
from app.provenance.builder import ProvenanceBundle, build_provenance
from app.provenance.graph_trace import build_graph_reasoning
from app.safety.engine import SafetyContext, SafetyEngine
from app.safety.ranking import rank_candidates
from app.safety.validator import validate_and_repair

logger = logging.getLogger(__name__)


class WorkoutState(TypedDict, total=False):
    request: WorkoutRequest
    member_context: MemberContext
    intent: WorkoutIntent
    resolved_concepts: list[ResolvedConcept]
    trajectory: MemberTrajectory
    safety_context: SafetyContext
    safety_decisions: dict[str, SafetyDecision]
    eligible_exercises: list[ExerciseCandidate]
    draft: LLMWorkoutDraft
    generated_workout: GeneratedWorkout
    post_validation: PostValidationReport
    provenance: ProvenanceBundle
    graph_reasoning: GraphReasoning
    timings: dict[str, float]
    generator: str
    errors: list[str]


class WorkoutWorkflow:
    def __init__(
        self,
        repository: GraphRepository,
        ontology: Ontology,
        resolver,
        engine: SafetyEngine,
        llm: LLMClient,
        trajectory_service: MemberTrajectoryService | None = None,
    ) -> None:
        self._repo = repository
        self._ontology = ontology
        self._resolver = resolver
        self._engine = engine
        self._llm = llm
        # One shared longitudinal service. The composition root passes the same
        # instance to the Copilot and the MCP tools, so a trend can never differ
        # depending on which surface asked. The default keeps direct
        # construction (tests, scripts) working.
        self._trajectory_service = trajectory_service or MemberTrajectoryService(ontology)
        self._graph = self._build()

    def _build(self):
        builder = StateGraph(WorkoutState)
        builder.add_node("load_member", self._load_member)
        builder.add_node("parse_intent", self._parse_intent)
        builder.add_node("analyze_longitudinal_context", self._analyze_longitudinal_context)
        builder.add_node("evaluate_safety", self._evaluate_safety)
        builder.add_node("rank_candidates", self._rank_candidates)
        builder.add_node("compose_workout", self._compose_workout)
        builder.add_node("validate_workout", self._validate_workout)
        builder.add_node("build_provenance", self._build_provenance)

        builder.set_entry_point("load_member")
        builder.add_edge("load_member", "parse_intent")
        builder.add_edge("parse_intent", "analyze_longitudinal_context")
        builder.add_edge("analyze_longitudinal_context", "evaluate_safety")
        builder.add_edge("evaluate_safety", "rank_candidates")
        builder.add_edge("rank_candidates", "compose_workout")
        builder.add_edge("compose_workout", "validate_workout")
        builder.add_edge("validate_workout", "build_provenance")
        builder.add_edge("build_provenance", END)
        return builder.compile()

    async def run(self, request: WorkoutRequest) -> WorkoutState:
        state: WorkoutState = {"request": request, "timings": {}, "errors": []}
        return await self._graph.ainvoke(state)  # type: ignore[return-value]

    # --- nodes ------------------------------------------------------------

    def _load_member(self, state: WorkoutState) -> dict[str, Any]:
        started = time.perf_counter()
        request = state["request"]
        member = self._repo.get_member_context(request.member_id)
        if member is None:
            raise ValueError(f"Unknown member: {request.member_id}")
        return {
            "member_context": member,
            "timings": _timed(state, "load_member", started),
        }

    def _parse_intent(self, state: WorkoutState) -> dict[str, Any]:
        started = time.perf_counter()
        request = state["request"]
        intent, resolved = parse_intent(
            request.prompt, request.duration_minutes, self._resolver
        )
        return {
            "intent": intent,
            "resolved_concepts": resolved,
            "timings": _timed(state, "parse_intent_and_resolve", started),
        }

    def _analyze_longitudinal_context(self, state: WorkoutState) -> dict[str, Any]:
        """Deterministic trajectory analysis. No LLM, no safety authority."""
        started = time.perf_counter()
        trajectory = self._trajectory_service.analyze(state["member_context"])
        return {
            "trajectory": trajectory,
            "timings": _timed(state, "analyze_longitudinal_context", started),
        }

    def _evaluate_safety(self, state: WorkoutState) -> dict[str, Any]:
        started = time.perf_counter()
        context = self._engine.build_context(
            state["member_context"], state["intent"], state["resolved_concepts"]
        )
        decisions = {d.exercise_id: d for d in self._engine.evaluate_all(context)}
        return {
            "safety_context": context,
            "safety_decisions": decisions,
            "timings": _timed(state, "evaluate_safety", started),
        }

    def _rank_candidates(self, state: WorkoutState) -> dict[str, Any]:
        started = time.perf_counter()
        candidates = rank_candidates(
            self._repo.list_exercises(),
            state["safety_decisions"],
            state["member_context"],
            state["intent"],
            state["resolved_concepts"],
            self._ontology,
            trajectory=state.get("trajectory"),
        )
        return {
            "eligible_exercises": candidates,
            "timings": _timed(state, "rank_candidates", started),
        }

    async def _compose_workout(self, state: WorkoutState) -> dict[str, Any]:
        started = time.perf_counter()
        draft = await compose_workout_draft(
            llm=self._llm,
            member=state["member_context"],
            intent=state["intent"],
            candidates=state["eligible_exercises"],
            safety_context=state["safety_context"],
            decisions=state["safety_decisions"],
            trajectory=state.get("trajectory"),
        )
        return {
            "draft": draft,
            "generator": getattr(self._llm, "name", "unknown"),
            "timings": _timed(state, "compose_workout_llm", started),
        }

    def _validate_workout(self, state: WorkoutState) -> dict[str, Any]:
        started = time.perf_counter()
        workout, report = validate_and_repair(
            state["draft"],
            state["safety_decisions"],
            state["eligible_exercises"],
            state["intent"].duration_minutes,
        )
        if not report.passed:
            logger.warning(
                "post_validation_corrections rejected=%d replaced=%d hallucinated=%d",
                len(report.rejected),
                len(report.replacements),
                len(report.hallucinated_ids),
            )
        return {
            "generated_workout": workout,
            "post_validation": report,
            "timings": _timed(state, "validate_workout", started),
        }

    def _build_provenance(self, state: WorkoutState) -> dict[str, Any]:
        started = time.perf_counter()
        bundle = build_provenance(
            state["generated_workout"],
            state["safety_decisions"],
            state["eligible_exercises"],
            state["safety_context"],
            state["post_validation"],
            trajectory=state.get("trajectory"),
        )

        # Built from the SAME decision objects the provenance bundle uses, so
        # the trace can never describe a decision the engine did not make.
        reasoning = build_graph_reasoning(
            trace_id=uuid.uuid4().hex[:12],
            graph_backend=getattr(self._repo, "backend_name", "memory"),
            decisions=state["safety_decisions"],
            candidates=state["eligible_exercises"],
            resolved_concepts=state["resolved_concepts"],
            member_facts=bundle.member_facts,
            in_plan_count=bundle.counts.get("in_plan", 0),
            ontology=self._ontology,
        )

        return {
            "provenance": bundle,
            "graph_reasoning": reasoning,
            "timings": _timed(state, "build_provenance", started),
        }


def _timed(state: WorkoutState, label: str, started: float) -> dict[str, float]:
    timings = dict(state.get("timings") or {})
    timings[label] = round((time.perf_counter() - started) * 1000, 2)
    return timings
