"""MCP tool contracts.

These are deliberately *narrower* than the internal domain models. An MCP tool
result is read by a language model, and two failure modes matter:

* dumping raw internal objects wastes context and leaks fields the model has no
  business reasoning about (chat transcripts, ingestion keys);
* inventing a field the graph never supplied invites the model to answer from a
  plausible-looking null.

So every model here is a hand-picked projection, and absent data is represented
as ``None`` / an empty list rather than a filled-in default. ``has_data`` flags
exist where "we have no observations" is itself the answer.

The MCP SDK derives both the input and the output JSON Schema from these
annotations, so they are the published contract - not documentation about it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.graph_trace import GraphReasoning
from app.domain.resolution import ResolvedConcept
from app.domain.trajectory import MemberTrajectory

# --- tool 1: get_member_context ---------------------------------------------


class GoalView(BaseModel):
    id: str
    text: str
    priority: int
    target_date: str | None = None


class InjuryView(BaseModel):
    id: str
    region: str
    joint: str | None = None
    status: str | None = None
    severity: str | None = None
    since: str | None = None
    notes: str | None = None
    clinical_hint: str | None = Field(
        default=None,
        description="Source-supplied clinical code hint. Not a diagnosis.",
    )


class PreferencesView(BaseModel):
    preferred_session_minutes: int | None = None
    training_days_per_week: int | None = None
    preferred_days: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(
        default_factory=list,
        description="Affects ranking only. Never a safety exclusion.",
    )
    notes: str | None = None


class TrendView(BaseModel):
    has_data: bool
    labels: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)
    first: float | None = None
    latest: float | None = None
    delta: float | None = None
    average: float | None = None
    direction: str | None = None


class BiomarkerView(BaseModel):
    resting_hr_bpm: int | None = None
    hrv_ms: int | None = None
    body_fat_pct: float | None = None
    ldl_mg_dl: float | None = None
    hdl_mg_dl: float | None = None
    vitamin_d_ng_ml: float | None = None
    panel_date: str | None = None
    dexa_date: str | None = None


class CoachBriefView(BaseModel):
    generated_for: str | None = None
    morning_tasks: list[str] = Field(default_factory=list)


class ChurnView(BaseModel):
    level: str | None = None
    reasons: list[str] = Field(default_factory=list)


class MemberContextView(BaseModel):
    """Compact member view for AI reasoning. Projection, never a raw dump."""

    member_id: str
    name: str
    age: int | None = None
    sex: str | None = None
    tier: str | None = None
    member_since: str | None = None
    goals: list[GoalView] = Field(default_factory=list)
    preferences: PreferencesView
    injuries: list[InjuryView] = Field(default_factory=list)
    equipment_available: list[str] = Field(default_factory=list)
    adherence: TrendView
    sleep: TrendView
    biomarkers: BiomarkerView
    coach_brief: CoachBriefView
    churn: ChurnView
    sessions_recorded: int = 0
    # The same deterministic longitudinal reading the workout pipeline uses.
    # Present so an AI client cannot derive its own trend from the raw numbers
    # and disagree with the plan it is discussing. Optional so an older client
    # ignoring it keeps working.
    trajectory: MemberTrajectory | None = None
    safety_note: str = Field(
        default=(
            "Injuries and equipment here are context for explanation only. "
            "Exercise safety is decided by the deterministic graph engine via "
            "evaluate_workout_request - never inferred from this payload."
        )
    )


# --- tool 2: resolve_coach_concepts -----------------------------------------


class ConceptView(BaseModel):
    source_text: str
    canonical_id: str | None = None
    label: str | None = None
    concept_type: str | None = None
    method: str = Field(
        description="exact | alias | fuzzy | embedding | unresolved",
    )
    confidence: float
    resolved: bool
    alternatives: list[str] = Field(default_factory=list)

    @classmethod
    def of(cls, concept: ResolvedConcept) -> ConceptView:
        return cls(
            source_text=concept.source_text,
            canonical_id=concept.canonical_id,
            label=concept.label,
            concept_type=concept.concept_type,
            method=concept.method,
            confidence=concept.confidence,
            resolved=concept.is_resolved,
            alternatives=list(concept.alternatives),
        )


class ResolveConceptsResult(BaseModel):
    text: str
    concepts: list[ConceptView] = Field(default_factory=list)
    unresolved: list[ConceptView] = Field(
        default_factory=list,
        description=(
            "Phrases that cleared no threshold. Reported rather than dropped so a "
            "lost safety-relevant signal stays visible."
        ),
    )


# --- tool 7: evaluate_workout_request ---------------------------------------


class IntentView(BaseModel):
    duration_minutes: int
    requested_focus: list[str] = Field(default_factory=list)
    explicit_exclusions: list[str] = Field(default_factory=list)
    equipment_mentions: list[str] = Field(default_factory=list)
    injury_mentions: list[str] = Field(default_factory=list)
    equipment_is_restrictive: bool = False


class SafetySummaryView(BaseModel):
    catalog_count: int
    excluded_count: int
    downranked_count: int
    eligible_count: int


class CandidateView(BaseModel):
    exercise_id: str
    name: str
    score: float
    status: str
    equipment_required: list[str] = Field(default_factory=list)
    movement_patterns: list[str] = Field(default_factory=list)
    muscle_groups: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class ExcludedView(BaseModel):
    exercise_id: str
    name: str
    rule_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(
        default_factory=list,
        description="Rendered graph traversals that justify the exclusion.",
    )


class ProvenanceItemView(BaseModel):
    exercise_id: str
    exercise: str
    decision: str
    rule_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class WorkoutRequestEvaluation(BaseModel):
    """Read-only, deterministic pre-generation evaluation.

    This is the authoritative candidate set. It is produced entirely by intent
    parsing, concept resolution and graph traversal - no LLM participates, and
    no workout is composed. Plan composition remains solely
    ``POST /api/workouts/generate``.
    """

    member_id: str
    prompt: str
    intent: IntentView
    resolved_concepts: list[ConceptView] = Field(default_factory=list)
    unresolved_concepts: list[ConceptView] = Field(default_factory=list)
    member_evidence: list[str] = Field(default_factory=list)
    safety_summary: SafetySummaryView
    eligible_candidates: list[CandidateView] = Field(default_factory=list)
    downranked_candidates: list[CandidateView] = Field(default_factory=list)
    excluded: list[ExcludedView] = Field(default_factory=list)
    graph_reasoning: GraphReasoning
    provenance: list[ProvenanceItemView] = Field(default_factory=list)
    graph_backend: str
    composed_workout: None = Field(
        default=None,
        description=(
            "Always null. This tool never composes a plan; use the REST "
            "workout-generation endpoint for that."
        ),
    )


# --- tool 3: get_member_metric_trend ----------------------------------------


class ObservationView(BaseModel):
    label: str = Field(
        description=(
            "The observation's own label from the member graph - a real date for "
            "adherence and weight. Sleep is recorded as an unlabelled 7-night "
            "series, so its labels are positional ('Night 1'). No date is "
            "invented for it."
        )
    )
    value: float


class MetricTrendResult(BaseModel):
    member_id: str
    metric: str
    observations: list[ObservationView] = Field(default_factory=list)
    count: int = 0
    first_value: float | None = None
    latest_value: float | None = None
    average_value: float | None = None
    absolute_delta: float | None = None
    percent_delta: float | None = Field(
        default=None,
        description="Null when the baseline is zero, where a percentage is undefined.",
    )
    direction: str = Field(
        description="improving | declining | stable | insufficient_data",
    )
    unit: str | None = None
    computed_by: str = Field(
        default="deterministic_python",
        description="Arithmetic is computed in copilot.analytics, never by a model.",
    )
    # The shared longitudinal reading, attached so a client discussing a trend
    # sees the same derived state the workout pipeline personalized on. The
    # numbers above and the states here come from one service; a client must
    # never derive its own progression state from the observations.
    trajectory: MemberTrajectory | None = None


# --- tool 4: evaluate_exercise_safety ---------------------------------------


class InjuryEvidenceView(BaseModel):
    injury_name: str
    condition_label: str | None = None
    severity: str | None = None
    status: str | None = None
    body_side: str | None = None
    root_region: str | None = None
    affected_regions: list[str] = Field(default_factory=list)
    contraindicated_patterns: list[str] = Field(default_factory=list)


class SafetyReasonView(BaseModel):
    rule_id: str
    message: str
    evidence: list[str] = Field(default_factory=list)


class ExerciseSafetyResult(BaseModel):
    """Authoritative safety verdict for one exercise and one member."""

    member_id: str
    exercise_id: str
    exercise_name: str
    status: str = Field(description="allowed | downranked | excluded")
    is_excluded: bool
    score_adjustment: float = 0.0
    reasons: list[SafetyReasonView] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    injury_evidence: list[InjuryEvidenceView] = Field(default_factory=list)
    required_equipment: list[str] = Field(default_factory=list)
    member_available_equipment: list[str] = Field(default_factory=list)
    missing_equipment: list[str] = Field(default_factory=list)
    movement_patterns: list[str] = Field(default_factory=list)
    stressed_regions: list[str] = Field(default_factory=list)
    graph_evidence: list[str] = Field(default_factory=list)
    decision_source: str = "knowledge_graph"
    graph_backend: str
    authoritative: bool = Field(
        default=True,
        description=(
            "This verdict comes from the deterministic SafetyEngine. It must not "
            "be overridden, softened or re-argued by a model."
        ),
    )


# --- tool 5: get_exercise_provenance ----------------------------------------


class GraphPathView(BaseModel):
    nodes: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)
    node_kinds: list[str] = Field(default_factory=list)
    directions: list[str] = Field(default_factory=list)
    facts: list[str] = Field(
        default_factory=list,
        description=(
            "Deterministic non-graph evidence, e.g. an equipment set difference. "
            "Absence of a relationship is a fact, not an edge."
        ),
    )
    rendered: str


class ExerciseProvenanceResult(BaseModel):
    """Why the deterministic engine decided what it decided, with real evidence."""

    member_id: str
    exercise_id: str
    exercise_name: str
    status: str
    reasons: list[SafetyReasonView] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    member_evidence: list[str] = Field(default_factory=list)
    exercise_evidence: list[str] = Field(default_factory=list)
    graph_paths: list[GraphPathView] = Field(default_factory=list)
    has_graph_path: bool = Field(
        description=(
            "False when the decision rests on a deterministic set operation "
            "(e.g. missing equipment) rather than a traversal. No path is "
            "fabricated to fill the gap."
        )
    )
    evidence_note: str | None = Field(
        default=None,
        description="Stated explicitly when no exact traversal exists.",
    )
    equipment_evidence: list[str] = Field(default_factory=list)
    injury_evidence: list[InjuryEvidenceView] = Field(default_factory=list)
    anatomy_evidence: list[str] = Field(default_factory=list)
    graph_backend: str
    authoritative: bool = True


# --- tool 6: get_safe_exercise_candidates -----------------------------------


class SafeCandidatesResult(BaseModel):
    """A graph-approved candidate set. Excluded exercises can never appear."""

    member_id: str
    resolved_concepts: list[ConceptView] = Field(default_factory=list)
    unresolved_concepts: list[ConceptView] = Field(default_factory=list)
    applied_constraints: IntentView
    catalog_count: int
    excluded_count: int
    downranked_count: int
    eligible_count: int
    returned_count: int
    limit_applied: int | None = Field(
        default=None,
        description="Applied AFTER safety filtering and ranking, never before.",
    )
    eligible_candidates: list[CandidateView] = Field(default_factory=list)
    downranked_candidates: list[CandidateView] = Field(default_factory=list)
    graph_backend: str
    authoritative: bool = True
