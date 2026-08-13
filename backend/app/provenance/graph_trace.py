"""Builds the graph-reasoning payload from real safety decisions.

This module is a pure projection. It runs no queries, makes no decisions, and
adds no relationships - it walks the ``SafetyDecision`` objects the engine
already produced and restates their ``GraphPath`` evidence in a typed shape the
UI can render without guessing.

Two consequences are deliberate:

* A traversal cannot exist for a decision the engine did not make, because the
  decisions are the only input.
* Counts are read from the same decision set the API reports, so the summary can
  never disagree with ``safety`` in the response.
"""

from __future__ import annotations

from app.domain.exercise import ExerciseCandidate
from app.domain.graph_trace import (
    ConstraintType,
    GraphReasoning,
    GraphReasoningSummary,
    GraphTraceEdge,
    GraphTraceNode,
    GraphTraversal,
    PromptConcept,
    RuleCategoryCount,
)
from app.domain.resolution import ResolvedConcept
from app.domain.safety import GraphPath, SafetyDecision, SafetyReason
from app.ontology.grounding import to_concept_grounding
from app.ontology.loader import Ontology

# Which constraint family each safety rule belongs to. Mirrors RuleId exactly;
# an unmapped rule falls back to "data_gap" rather than being silently dropped.
RULE_TO_CONSTRAINT: dict[str, ConstraintType] = {
    "injury_region_stress": "injury_anatomy",
    "injury_side_specific": "injury_anatomy",
    "injury_contraindicated_pattern": "contraindication",
    "equipment_unavailable": "equipment",
    "explicit_exclusion": "explicit_exclusion",
    "preference_dislike": "preference_ranking",
    "unknown_anatomy": "data_gap",
    "goal_alignment": "preference_ranking",
    "history_recency": "preference_ranking",
}

CONSTRAINT_LABEL: dict[ConstraintType, str] = {
    "injury_anatomy": "Injury / anatomy",
    "contraindication": "Contraindication",
    "equipment": "Equipment",
    "explicit_exclusion": "Explicit exclusion",
    "preference_ranking": "Preference / ranking",
    "data_gap": "Missing catalog data",
}

# Rules whose evidence is a deterministic set operation rather than a walk.
SET_OPERATION_RULES = {"equipment_unavailable", "unknown_anatomy"}


def build_graph_reasoning(
    *,
    trace_id: str,
    graph_backend: str,
    decisions: dict[str, SafetyDecision],
    candidates: list[ExerciseCandidate],
    resolved_concepts: list[ResolvedConcept],
    member_facts: list[str],
    in_plan_count: int,
    ontology: Ontology | None = None,
) -> GraphReasoning:
    """Project safety decisions into the UI's graph-reasoning payload.

    ``ontology`` is optional purely so this stays a pure projection: it is read
    only to attach the published-ontology grounding a concept already has. It
    contributes no reasoning and cannot change a decision.
    """
    traversals: list[GraphTraversal] = []

    for decision in decisions.values():
        for reason_index, reason in enumerate(decision.reasons):
            for path_index, path in enumerate(reason.graph_paths):
                traversal = _traversal_from_path(
                    decision=decision,
                    reason=reason,
                    path=path,
                    index=f"{reason_index}-{path_index}",
                )
                if traversal is not None:
                    traversals.append(traversal)

    return GraphReasoning(
        trace_id=trace_id,
        graph_backend=graph_backend,
        summary=_summarize(decisions, candidates, resolved_concepts, traversals, in_plan_count),
        prompt_concepts=[_prompt_concept(c, ontology) for c in resolved_concepts],
        traversals=traversals,
        member_facts=list(member_facts),
    )


def _traversal_from_path(
    *,
    decision: SafetyDecision,
    reason: SafetyReason,
    path: GraphPath,
    index: str,
) -> GraphTraversal | None:
    """Convert one evidence path into typed nodes and edges."""
    if not path.nodes and not path.facts:
        return None

    nodes: list[GraphTraceNode] = []
    for position, label in enumerate(path.nodes):
        kind = path.kind_at(position)
        nodes.append(
            GraphTraceNode(
                # Position-scoped id: the same label can legitimately appear in
                # two different paths for the same decision.
                id=f"{decision.exercise_id}:{index}:{position}",
                label=label,
                type=kind or "Exercise",
                properties={},
            )
        )

    edges: list[GraphTraceEdge] = []
    for position, relationship in enumerate(path.edges):
        if position + 1 >= len(nodes):
            break
        edges.append(
            GraphTraceEdge(
                source_id=nodes[position].id,
                target_id=nodes[position + 1].id,
                relationship=relationship,
                direction=path.direction_at(position),
                rule_id=reason.rule_id,
            )
        )

    constraint = RULE_TO_CONSTRAINT.get(reason.rule_id, "data_gap")
    source: str = (
        "deterministic_set_operation"
        if reason.rule_id in SET_OPERATION_RULES and not edges
        else "graph_traversal"
    )

    return GraphTraversal(
        id=f"{decision.exercise_id}:{index}",
        constraint_type=constraint,
        exercise_id=decision.exercise_id,
        exercise_name=decision.exercise_name,
        decision=decision.status,
        reason=reason.message,
        rule_id=reason.rule_id,
        source=source,  # type: ignore[arg-type]
        path_kind=_path_kind(nodes, edges),
        nodes=nodes,
        edges=edges,
        facts=list(path.facts),
        source_concept=_source_concept(path),
    )


#: Node kinds that only ever appear on a walk through the member's own graph.
MEMBER_NODE_KINDS = {"Member", "Injury", "Preference"}


def _path_kind(nodes: list[GraphTraceNode], edges: list[GraphTraceEdge]) -> str:
    """Classify a path from the node kinds the engine recorded.

    Done here rather than in the UI so the member/exercise split is backed by
    real typed data. A frontend deciding this from edge names or reason text
    would be inventing structure inside the one panel whose purpose is to show
    only what the graph holds.
    """
    if not edges:
        return "set_operation"
    if any(node.type in MEMBER_NODE_KINDS for node in nodes):
        return "member_context"
    if nodes and all(node.type == "AnatomicalRegion" for node in nodes):
        return "anatomy_hierarchy"
    return "exercise_structure"


def _source_concept(path: GraphPath) -> str | None:
    """Surface the coach phrase when the engine recorded one as a fact."""
    for fact in path.facts:
        if fact.startswith("Coach phrase ") or fact.startswith("Coach excluded "):
            return fact
    return None


def _summarize(
    decisions: dict[str, SafetyDecision],
    candidates: list[ExerciseCandidate],
    resolved_concepts: list[ResolvedConcept],
    traversals: list[GraphTraversal],
    in_plan_count: int,
) -> GraphReasoningSummary:
    by_constraint: dict[ConstraintType, set[str]] = {}
    traversal_counts: dict[ConstraintType, int] = {}

    for traversal in traversals:
        by_constraint.setdefault(traversal.constraint_type, set()).add(traversal.exercise_id)
        traversal_counts[traversal.constraint_type] = (
            traversal_counts.get(traversal.constraint_type, 0) + 1
        )

    counts = [
        RuleCategoryCount(
            constraint_type=constraint,
            label=CONSTRAINT_LABEL[constraint],
            exercises_affected=len(exercise_ids),
            traversals=traversal_counts.get(constraint, 0),
        )
        for constraint, exercise_ids in by_constraint.items()
    ]
    counts.sort(key=lambda row: -row.exercises_affected)

    return GraphReasoningSummary(
        catalog_count=len(decisions),
        excluded_count=sum(1 for d in decisions.values() if d.status == "excluded"),
        downranked_count=sum(1 for d in decisions.values() if d.status == "downranked"),
        eligible_count=len(candidates),
        in_plan_count=in_plan_count,
        concepts_resolved=sum(1 for c in resolved_concepts if c.is_resolved),
        concepts_unresolved=sum(1 for c in resolved_concepts if not c.is_resolved),
        traversal_count=len(traversals),
        exercises_with_evidence=len({t.exercise_id for t in traversals}),
        counts_by_constraint=counts,
    )


def _prompt_concept(concept: ResolvedConcept, ontology: Ontology | None) -> PromptConcept:
    """Restate one resolver result, with its ontology grounding if it has one.

    Grounding is attached only for a *resolved* concept: an unresolved phrase
    has no canonical id, so there is nothing to ground, and showing a mapping
    next to it would imply the phrase was understood when it was not.
    """
    grounding = None
    if ontology is not None and concept.is_resolved and concept.canonical_id:
        grounding = to_concept_grounding(ontology.grounding_for(concept.canonical_id))

    return PromptConcept(
        source_text=concept.source_text,
        canonical_id=concept.canonical_id,
        label=concept.label,
        concept_type=concept.concept_type,
        method=concept.method,
        confidence=concept.confidence,
        resolved=concept.is_resolved,
        grounding=grounding,
    )
