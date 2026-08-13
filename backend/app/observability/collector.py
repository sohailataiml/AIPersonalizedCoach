"""Builds traces from work that already happened.

The architectural choice worth stating: traces are assembled **after** a run,
from the state the workflow already produced, rather than by scattering
instrumentation through the domain services.

That buys the property this layer must have - it cannot influence a decision,
because it runs once every decision is final. `SafetyEngine`, the ranker and the
validator contain no tracing code at all, and a test asserts that deleting the
trace still leaves all 50 safety decisions identical.

The one exception is the graph-call counter, which has to observe calls as they
happen. It is a pass-through proxy that only increments an integer.
"""

from __future__ import annotations

import contextvars
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.domain.trace import (
    NODE_ZONE,
    AdjustmentTraceSummary,
    McpTraceSummary,
    NodeSpan,
    RequestTrace,
    ResolutionTraceSummary,
    SafetyTraceSummary,
    WorkflowKind,
)

#: Request-scoped repository call counter. A ContextVar rather than a global so
#: concurrent requests cannot contaminate each other's counts.
_graph_calls: contextvars.ContextVar[Counter | None] = contextvars.ContextVar(
    "graph_calls", default=None
)

#: Repository methods that represent a real graph read. Construction helpers and
#: stats are excluded so the number means "queries this request made".
COUNTED_REPOSITORY_METHODS = frozenset(
    {
        "list_exercises",
        "get_exercise",
        "get_member_context",
        "member_equipment",
        "exercise_required_equipment",
        "exercise_patterns",
        "exercise_stressed_regions",
        "injury_affected_regions",
        "part_of_path",
        "stresses_path",
        "patterns_in_family",
        "exercises_with_pattern",
        "exercise_provenance",
    }
)


class graph_call_scope:  # noqa: N801 - used as a context manager, not a type
    """Count repository calls made inside the block.

    ``scope.count`` is ``None`` when no instrumented repository is installed,
    which the trace reports as absent rather than as zero.
    """

    def __init__(self) -> None:
        self._token: contextvars.Token | None = None
        self._counter: Counter = Counter()

    def __enter__(self) -> graph_call_scope:
        self._token = _graph_calls.set(self._counter)
        return self

    def __exit__(self, *exc: object) -> None:
        if self._token is not None:
            _graph_calls.reset(self._token)

    @property
    def count(self) -> int:
        return sum(self._counter.values())

    @property
    def by_method(self) -> dict[str, int]:
        return dict(self._counter)


class InstrumentedGraphRepository:
    """Counting pass-through over a ``GraphRepository``.

    Delegates everything untouched and increments a counter when a scope is
    active. It holds no state that a query could read, so it cannot change a
    result - it is the only piece of tracing that has to sit in the call path,
    and it is deliberately this thin.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._inner, name)
        if name not in COUNTED_REPOSITORY_METHODS or not callable(attribute):
            return attribute

        def counted(*args: Any, **kwargs: Any) -> Any:
            counter = _graph_calls.get()
            if counter is not None:
                counter[name] += 1
            return attribute(*args, **kwargs)

        return counted

    @property
    def inner(self) -> Any:
        return self._inner


# --- trace construction ------------------------------------------------------


def _spans(timings: dict[str, float]) -> list[NodeSpan]:
    """Workflow node timings, in execution order, zoned.

    ``total`` is excluded: it is the whole request, not a node, and rendering it
    beside the nodes would double-count in the waterfall.
    """
    return [
        NodeSpan(
            name=name,
            duration_ms=max(0.0, float(duration)),
            zone=NODE_ZONE.get(name, "deterministic"),
        )
        for name, duration in timings.items()
        if name != "total"
    ]


def _resolution_summary(concepts: list[Any]) -> ResolutionTraceSummary:
    counts: Counter = Counter()
    resolved = 0
    for concept in concepts:
        counts[concept.method] += 1
        if concept.is_resolved:
            resolved += 1
    return ResolutionTraceSummary(
        resolved_count=resolved,
        unresolved_count=len(concepts) - resolved,
        method_counts=dict(counts),
    )


def _safety_summary(state: dict) -> SafetyTraceSummary:
    decisions = state.get("safety_decisions") or {}
    provenance = state.get("provenance")
    report = state.get("post_validation")

    rules: Counter = Counter()
    for decision in decisions.values():
        for reason in decision.reasons:
            rules[reason.rule_id] += 1

    counts = provenance.counts if provenance else {}
    return SafetyTraceSummary(
        catalog_count=counts.get("catalog_total", len(decisions)),
        excluded_count=counts.get(
            "excluded", sum(1 for d in decisions.values() if d.is_excluded)
        ),
        downranked_count=counts.get(
            "downranked", sum(1 for d in decisions.values() if d.status == "downranked")
        ),
        eligible_count=counts.get("eligible", len(state.get("eligible_exercises") or [])),
        in_plan_count=counts.get("in_plan", 0),
        rules_fired=sorted(rules),
        rule_fire_count=sum(rules.values()),
        validation_corrections=len(report.rejected) if report else 0,
        validation_passed=report.passed if report else True,
        hallucinated_ids=len(report.hallucinated_ids) if report else 0,
    )


def build_workflow_trace(
    *,
    request_id: str,
    workflow: WorkflowKind,
    member_id: str,
    state: dict,
    total_duration_ms: float,
    llm_provider: str | None = None,
    graph_query_count: int | None = None,
    adjustment: AdjustmentTraceSummary | None = None,
) -> RequestTrace:
    """Assemble a trace from finished workflow state."""
    timings = dict(state.get("timings") or {})

    return RequestTrace(
        request_id=request_id,
        workflow=workflow,
        member_id=member_id,
        total_duration_ms=max(0.0, total_duration_ms),
        started_at=datetime.now(UTC).isoformat(timespec="seconds"),
        spans=_spans(timings),
        resolution=_resolution_summary(state.get("resolved_concepts") or []),
        safety=_safety_summary(state),
        adjustment=adjustment,
        graph_query_count=graph_query_count,
        llm_provider=llm_provider,
        llm_latency_ms=timings.get("compose_workout_llm"),
    )


def build_copilot_trace(
    *,
    request_id: str,
    member_id: str,
    intent: str,
    total_duration_ms: float,
    grounding: Any | None,
    generator: str | None,
    tool_duration_ms: float | None = None,
    graph_query_count: int | None = None,
) -> RequestTrace:
    """Assemble a Copilot trace.

    The coach's question never enters the trace - only its classified intent.
    Tool *names* are recorded; tool payloads are not.
    """
    mcp = McpTraceSummary(
        intent=intent,
        mode=grounding.mode if grounding else "fallback",
        tools_planned=list(grounding.tools_used) if grounding else [],
        tools_called=list(grounding.tools_used) if grounding else [],
        tool_duration_ms=tool_duration_ms,
        authoritative_safety=bool(grounding and grounding.authoritative_safety),
        safety_corrected=bool(grounding and grounding.safety_corrected),
        generator=generator,
    )

    return RequestTrace(
        request_id=request_id,
        workflow="copilot",
        member_id=member_id,
        total_duration_ms=max(0.0, total_duration_ms),
        started_at=datetime.now(UTC).isoformat(timespec="seconds"),
        spans=[
            NodeSpan(
                name="mcp_tool_calls",
                duration_ms=max(0.0, tool_duration_ms or 0.0),
                zone="mcp",
            )
        ]
        if tool_duration_ms is not None
        else [],
        mcp=mcp,
        graph_query_count=graph_query_count,
        llm_provider=generator,
    )
