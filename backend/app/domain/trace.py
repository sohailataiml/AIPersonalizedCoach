"""Execution-trace contracts.

A trace answers *"what happened during this particular request?"* — as distinct
from evaluation, which answers *"does the system behave correctly across known
scenarios?"*.

Privacy is a design constraint, not a later cleanup. These models carry ids,
durations and aggregate counts. They deliberately cannot carry a member payload,
a chat transcript, a lab result, a prompt body or an MCP protocol payload:
there is no field for any of them, so no future caller can accidentally add one
by passing the wrong argument. Tests assert their absence from serialized
output.

The synthetic dataset here would survive being logged. The point is to design
the layer as though it would not.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WorkflowKind = Literal["generate", "adjust", "copilot", "evaluation"]
SpanStatus = Literal["ok", "error", "skipped"]
Zone = Literal["deterministic", "generative", "mcp"]

#: Which architectural zone each workflow node belongs to. Drives the
#: deterministic/generative split in the dashboard, and is stated here rather
#: than inferred from a node name in the UI.
NODE_ZONE: dict[str, Zone] = {
    "load_member": "deterministic",
    "parse_intent_and_resolve": "deterministic",
    "analyze_longitudinal_context": "deterministic",
    "evaluate_safety": "deterministic",
    "rank_candidates": "deterministic",
    "compose_workout_llm": "generative",
    "validate_workout": "deterministic",
    "build_provenance": "deterministic",
    "baseline_rerun": "deterministic",
}

#: The node after which only graph-approved candidates continue.
SAFE_CANDIDATE_BOUNDARY = "rank_candidates"


class NodeSpan(BaseModel):
    name: str
    duration_ms: float = Field(ge=0)
    zone: Zone = "deterministic"
    status: SpanStatus = "ok"


class SafetyTraceSummary(BaseModel):
    """Aggregate counts, taken from the decisions the engine already produced."""

    catalog_count: int = 0
    excluded_count: int = 0
    downranked_count: int = 0
    eligible_count: int = 0
    in_plan_count: int = 0
    rules_fired: list[str] = Field(default_factory=list)
    rule_fire_count: int = 0
    validation_corrections: int = 0
    validation_passed: bool = True
    hallucinated_ids: int = 0


class ResolutionTraceSummary(BaseModel):
    resolved_count: int = 0
    unresolved_count: int = 0
    #: method -> count, e.g. {"alias": 3, "fuzzy": 1}. Methods, never phrases.
    method_counts: dict[str, int] = Field(default_factory=dict)


class AdjustmentTraceSummary(BaseModel):
    """What an adjustment changed. The instruction text is not recorded."""

    removed_count: int = 0
    added_count: int = 0
    downranked_count: int = 0
    retained_count: int = 0
    newly_excluded_count: int = 0
    duration_minutes: int | None = None
    baseline_rerun_ms: float | None = None


class McpTraceSummary(BaseModel):
    """Copilot / MCP behaviour.

    ``intent`` is the classified category, never the coach's question. Tool
    *names* are recorded; tool payloads are not.
    """

    intent: str | None = None
    mode: Literal["mcp", "fallback"] | None = None
    tools_planned: list[str] = Field(default_factory=list)
    tools_called: list[str] = Field(default_factory=list)
    tool_duration_ms: float | None = None
    authoritative_safety: bool = False
    safety_corrected: bool = False
    generator: str | None = None


class RequestTrace(BaseModel):
    request_id: str
    workflow: WorkflowKind
    member_id: str | None = None
    total_duration_ms: float = Field(default=0.0, ge=0)
    started_at: str | None = None
    status: Literal["ok", "error"] = "ok"
    error_kind: str | None = None

    spans: list[NodeSpan] = Field(default_factory=list)
    resolution: ResolutionTraceSummary | None = None
    safety: SafetyTraceSummary | None = None
    adjustment: AdjustmentTraceSummary | None = None
    mcp: McpTraceSummary | None = None

    #: Repository calls made while this request was in flight. ``None`` when no
    #: counter was installed - reported as absent rather than as zero.
    graph_query_count: int | None = None
    llm_provider: str | None = None
    llm_latency_ms: float | None = None
    #: Providers that report usage populate these. The offline stub does not,
    #: and absent is the honest value.
    llm_input_tokens: int | None = None
    llm_output_tokens: int | None = None

    def zone_totals(self) -> dict[str, float]:
        """Milliseconds spent in each architectural zone."""
        totals: dict[str, float] = {}
        for span in self.spans:
            totals[span.zone] = round(totals.get(span.zone, 0.0) + span.duration_ms, 2)
        return totals


class TraceListResponse(BaseModel):
    traces: list[RequestTrace] = Field(default_factory=list)
    count: int = 0
    capacity: int = 0
