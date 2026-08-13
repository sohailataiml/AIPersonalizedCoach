"""API request/response contracts.

Typed end to end: these models generate the OpenAPI schema the frontend client
is written against.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.copilot.mcp_narrator import SafetyEvidence
from app.copilot.service import ChartPayload, Citation, CopilotIntent, Grounding
from app.domain.graph_trace import GraphReasoning, GraphTraversal
from app.domain.member import Goal, Injury, MemberSummary
from app.domain.ontology import ConceptGrounding
from app.domain.resolution import ResolvedConcept
from app.domain.trajectory import MemberTrajectory
from app.domain.workout import GeneratedWorkout, PostValidationReport
from app.provenance.builder import ProvenanceItem
from app.provenance.diff import AdjustmentDiff


class GenerateWorkoutRequest(BaseModel):
    member_id: str
    prompt: str = Field(min_length=1, max_length=2000)
    duration_minutes: int = Field(default=45, ge=10, le=120)


class SafetySummary(BaseModel):
    catalog_total: int
    eligible: int
    excluded: int
    downranked: int
    in_plan: int
    post_validation_passed: bool
    post_validation_rejections: int
    post_validation_replacements: int


class GenerateWorkoutResponse(BaseModel):
    request_id: str
    workout: GeneratedWorkout
    resolved_concepts: list[ResolvedConcept] = Field(default_factory=list)
    unresolved_concepts: list[ResolvedConcept] = Field(default_factory=list)
    filtered_exercises: list[ProvenanceItem] = Field(default_factory=list)
    provenance: list[ProvenanceItem] = Field(default_factory=list)
    member_facts: list[str] = Field(default_factory=list)
    safety: SafetySummary
    post_validation: PostValidationReport
    timings_ms: dict[str, float] = Field(default_factory=dict)
    generator: str = "stub"
    graph_backend: str = "memory"
    # Additive and optional: existing consumers that ignore this field keep
    # working, and a client can fall back to `provenance` if it is absent.
    graph_reasoning: GraphReasoning | None = None
    # The deterministic longitudinal reading that personalized this plan.
    # Personalization only - it never established safety.
    trajectory: MemberTrajectory | None = None


class AdjustWorkoutRequest(BaseModel):
    """A coach adjustment to an already-generated plan.

    The previous plan is supplied as **ids only**. Nothing about it is fed to
    the model - it is used solely to compute the deterministic diff after the
    pipeline has re-run from scratch.
    """

    member_id: str
    base_prompt: str = Field(min_length=1, max_length=2000)
    adjustment: str = Field(min_length=1, max_length=500)
    duration_minutes: int = Field(default=45, ge=10, le=120)
    previous_exercise_ids: list[str] = Field(default_factory=list, max_length=100)


class AdjustWorkoutResponse(GenerateWorkoutResponse):
    """The regenerated plan, plus what changed and why.

    Extends the generate response rather than defining a parallel shape: an
    adjusted plan carries exactly the same provenance, graph reasoning and
    safety guarantees, because it went through exactly the same pipeline.
    """

    adjustment: str
    effective_prompt: str
    diff: AdjustmentDiff


class CopilotRequest(BaseModel):
    member_id: str
    message: str = Field(min_length=1, max_length=2000)


class CopilotChatResponse(BaseModel):
    """Four clearly separated layers, in increasing order of detail.

    ``answer`` is the only human-facing text. ``grounding`` says how it was
    obtained, ``safety_evidence`` is the compact structure the UI expands, and
    ``evidence`` holds the verbatim tool payloads for debugging and replay.
    """

    intent: CopilotIntent
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    chart: ChartPayload | None = None
    evidence: dict = Field(default_factory=dict)
    generator: str
    latency_ms: float
    # Optional so existing clients keep parsing responses unchanged.
    grounding: Grounding | None = None
    safety_evidence: SafetyEvidence | None = None


class MemberHistoryResponse(BaseModel):
    member_id: str
    sessions: list[dict] = Field(default_factory=list)
    chat: list[dict] = Field(default_factory=list)
    adherence: list[dict] = Field(default_factory=list)
    sleep: list[dict] = Field(default_factory=list)


class MemberSummaryResponse(MemberSummary):
    goals: list[Goal] = Field(default_factory=list)
    active_injuries: list[Injury] = Field(default_factory=list)
    morning_tasks: list[dict] = Field(default_factory=list)
    brief_date: str | None = None


class ExerciseProvenanceResponse(BaseModel):
    exercise_id: str
    name: str
    targets: list[str] = Field(default_factory=list)
    stresses: list[str] = Field(default_factory=list)
    anatomy_ancestors: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    families: list[str] = Field(default_factory=list)
    is_unilateral: bool = False
    side: str | None = None
    # The published-ontology grounding for the anatomy and muscles this
    # exercise touches. Additive and often partial: movement patterns and
    # equipment carry no external identifier, and that is stated rather than
    # papered over.
    grounding: list[ConceptGrounding] = Field(default_factory=list)


class GraphSafetyResponse(BaseModel):
    """One exercise's safety decision, for the explorer's Safety Reasoning mode.

    Deliberately thin: it carries the decision and the **same** ``GraphTraversal``
    objects the coach UI renders, so the explorer reuses ``DecisionPaths`` and
    contains no second interpretation of provenance. Safety is computed by the
    existing engine - the explorer only asks.
    """

    member_id: str
    member_name: str
    exercise_id: str
    exercise_name: str
    prompt: str
    decision: str
    rule_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    traversals: list[GraphTraversal] = Field(default_factory=list)
    score_adjustment: float = 0.0
    #: Longitudinal personalization is reported separately: it influences
    #: ranking, never eligibility, and merging it into the safety decision
    #: would blur exactly the boundary this project exists to keep sharp.
    longitudinal_adjustment: float = 0.0
    longitudinal_reasons: list[str] = Field(default_factory=list)
    eligible: bool = True


class HealthResponse(BaseModel):
    status: str
    graph_backend: str
    llm_provider: str
    graph_stats: dict[str, int] = Field(default_factory=dict)
    # Additive deployment facts for the Technical Details panel. Deliberately
    # no hostname, URI or credential - "which environment and is the graph
    # seeded" is what an operator needs; where it lives is not.
    environment: str = "local"
    graph_seeded: bool = True
    seed_version: str | None = None
    ontology_mappings: int = 0


class LivenessResponse(BaseModel):
    """Is the process running? Deliberately independent of the graph."""

    status: str = "alive"
    version: str | None = None


class ReadinessResponse(BaseModel):
    """Can the service actually serve?

    Reports state, never connection detail: no URI, no credential, no stack
    trace. ``problems`` carries verification messages (counts) and, at worst, a
    startup error already redacted to scheme/host/port.
    """

    status: str
    environment: str
    graph_backend: str
    graph_reachable: bool
    graph_seeded: bool
    seed_version: str | None = None
    mcp_enabled: bool = True
    problems: list[str] = Field(default_factory=list)
