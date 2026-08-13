"""API request/response contracts.

Typed end to end: these models generate the OpenAPI schema the frontend client
is written against.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.copilot.mcp_narrator import SafetyEvidence
from app.copilot.service import ChartPayload, Citation, CopilotIntent, Grounding
from app.domain.graph_trace import GraphReasoning
from app.domain.member import Goal, Injury, MemberSummary
from app.domain.ontology import ConceptGrounding
from app.domain.resolution import ResolvedConcept
from app.domain.workout import GeneratedWorkout, PostValidationReport
from app.provenance.builder import ProvenanceItem


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


class HealthResponse(BaseModel):
    status: str
    graph_backend: str
    llm_provider: str
    graph_stats: dict[str, int] = Field(default_factory=dict)
