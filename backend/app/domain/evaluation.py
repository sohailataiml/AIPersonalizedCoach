"""Offline evaluation contracts.

Evaluation answers *"does the system behave correctly across known scenarios?"*.
Tracing answers *"what happened during this particular request?"*. The dashboard
shows both and never conflates them, which is why they are separate models.

Every metric carries its **numerator and denominator**. A bare "100%" hides the
only thing that makes it meaningful - whether it was measured over 48 cases or
2 - so the ratio is the primary value and the percentage is derived from it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field

from app.domain.graph_trace import GraphTraversal

EvaluationCategory = Literal[
    "concept_resolution",
    "safety",
    "equipment",
    "exclusion",
    "longitudinal",
    "adjustment",
    "validation",
    "copilot_mcp",
]

CASE_CATEGORY_LABEL: dict[EvaluationCategory, str] = {
    "concept_resolution": "Concept resolution",
    "safety": "Safety",
    "equipment": "Equipment",
    "exclusion": "Explicit exclusions",
    "longitudinal": "Longitudinal",
    "adjustment": "Adjustment",
    "validation": "Workout validation",
    "copilot_mcp": "Copilot / MCP",
}


class GraphEvidence(BaseModel):
    """The graph evidence behind a safety-related expectation.

    ``traversals`` carries the **same** ``GraphTraversal`` objects the coach UI
    renders, so the dashboard reuses the existing path viewer instead of
    growing a second provenance renderer that could drift from it.
    """

    exercise: str
    decision: str
    rule_ids: list[str] = Field(default_factory=list)
    rendered_paths: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    traversals: list[GraphTraversal] = Field(default_factory=list)


class CaseResult(BaseModel):
    case_id: str
    category: EvaluationCategory
    name: str
    input_summary: str
    expected: str
    actual: str
    passed: bool
    latency_ms: float = Field(ge=0)
    #: Non-fatal observations - e.g. a case that passed but with a near-miss.
    notes: list[str] = Field(default_factory=list)
    evidence: list[GraphEvidence] = Field(default_factory=list)
    #: True when this case specifically probes the post-generation gate and an
    #: unsafe exercise survived it. First-class because it is the one number
    #: that must be zero.
    unsafe_escape: bool = False


class Metric(BaseModel):
    key: str
    label: str
    numerator: int
    denominator: int
    #: Lower is better for e.g. unsafe escapes, so the dashboard cannot assume
    #: a high ratio is good.
    higher_is_better: bool = True
    detail: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def value(self) -> float | None:
        """Ratio in [0, 1], or ``None`` when nothing was measured.

        ``None`` rather than 0.0: "we ran no cases" and "every case failed" are
        different facts and must not render the same.
        """
        if self.denominator == 0:
            return None
        return round(self.numerator / self.denominator, 4)


class Invariant(BaseModel):
    """A system property, and whether this run actually demonstrated it.

    ``holds`` is computed from case results. ``proven_by`` names the cases that
    demonstrated it, so a green tick can always be traced to executed evidence
    rather than to an author's confidence.
    """

    key: str
    statement: str
    holds: bool
    proven_by: list[str] = Field(default_factory=list)
    failed_by: list[str] = Field(default_factory=list)
    detail: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def evidence_count(self) -> int:
        return len(self.proven_by) + len(self.failed_by)


class LatencySummary(BaseModel):
    p50_ms: float | None = None
    p95_ms: float | None = None
    max_ms: float | None = None
    total_ms: float = 0.0


class EvaluationRun(BaseModel):
    run_id: str
    started_at: str
    duration_ms: float = 0.0
    graph_backend: str
    llm_provider: str

    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    unsafe_escapes: int = 0

    metrics: list[Metric] = Field(default_factory=list)
    invariants: list[Invariant] = Field(default_factory=list)
    results: list[CaseResult] = Field(default_factory=list)
    latency: LatencySummary = Field(default_factory=LatencySummary)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> Literal["pass", "fail"]:
        """A run fails if any case failed or any unsafe exercise escaped.

        Deliberately not an average. Categories measure different things, and a
        single blended percentage would let a safety escape hide behind a good
        resolver score.
        """
        return "pass" if self.failed_cases == 0 and self.unsafe_escapes == 0 else "fail"

    def metric(self, key: str) -> Metric | None:
        return next((m for m in self.metrics if m.key == key), None)


class EvaluationSummary(BaseModel):
    """Compact row for the history table - no per-case detail."""

    run_id: str
    started_at: str
    status: Literal["pass", "fail"]
    total_cases: int
    passed_cases: int
    failed_cases: int
    unsafe_escapes: int
    p95_ms: float | None = None
    duration_ms: float = 0.0


class EvaluationHistory(BaseModel):
    runs: list[EvaluationSummary] = Field(default_factory=list)
    count: int = 0
