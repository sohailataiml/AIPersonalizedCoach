"""Deterministic safety contracts.

``SafetyDecision`` is the single source of truth about whether an exercise may
appear in a plan. It is produced only by graph traversal, and it is re-checked
after the LLM composes a workout.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SafetyStatus = Literal["allowed", "downranked", "excluded"]
DecisionSource = Literal["knowledge_graph", "llm_composition", "post_validation"]

RuleId = Literal[
    "equipment_unavailable",
    "explicit_exclusion",
    "injury_contraindicated_pattern",
    "injury_region_stress",
    "injury_side_specific",
    "unknown_anatomy",
    "preference_dislike",
    "goal_alignment",
    "history_recency",
]


NodeKind = Literal[
    "Member",
    "Injury",
    "InjuryCondition",
    "Exercise",
    "AnatomicalRegion",
    "Equipment",
    "MovementPattern",
    "MovementFamily",
    "Preference",
    "Muscle",
]

EdgeDirection = Literal["outgoing", "incoming"]


class GraphPath(BaseModel):
    """A concrete traversal used as evidence for a decision.

    ``nodes`` and ``edges`` interleave: nodes[0] -edges[0]-> nodes[1] ...

    ``node_kinds`` and ``edge_directions`` are parallel arrays carrying the
    *typing the engine already knew* at the moment it walked the path. They exist
    so the UI never has to guess a node's type from an edge name - a guess would
    be frontend-invented data, which is exactly what this evidence model exists
    to prevent.

    ``edge_directions`` matters because some evidence is read against the arrow:
    a contraindication path goes InjuryCondition -CONTRAINDICATES-> Pattern and
    then reaches the exercise via the *incoming* Exercise -HAS_PATTERN-> Pattern
    edge. Recording that keeps the rendering truthful about the real topology.

    ``facts`` carries deterministic, non-graph evidence - most importantly the
    member's available-equipment set. Equipment *absence* is a set difference,
    not a relationship, so it is stated as a fact rather than drawn as an edge.
    """

    nodes: list[str]
    edges: list[str]
    node_kinds: list[NodeKind] = Field(default_factory=list)
    edge_directions: list[EdgeDirection] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)

    def as_steps(self) -> list[str]:
        steps: list[str] = []
        for i, node in enumerate(self.nodes):
            steps.append(node)
            if i < len(self.edges):
                steps.append(f"-[{self.edges[i]}]->")
        return steps

    def render(self) -> str:
        return " ".join(self.as_steps())

    def kind_at(self, index: int) -> NodeKind | None:
        return self.node_kinds[index] if index < len(self.node_kinds) else None

    def direction_at(self, index: int) -> EdgeDirection:
        if index < len(self.edge_directions):
            return self.edge_directions[index]
        return "outgoing"


class SafetyReason(BaseModel):
    rule_id: RuleId
    message: str
    graph_paths: list[GraphPath] = Field(default_factory=list)


class SafetyDecision(BaseModel):
    exercise_id: str
    exercise_name: str
    status: SafetyStatus = "allowed"
    reasons: list[SafetyReason] = Field(default_factory=list)
    score_adjustment: float = 0.0
    decision_source: DecisionSource = "knowledge_graph"

    @property
    def is_excluded(self) -> bool:
        return self.status == "excluded"

    @property
    def graph_paths(self) -> list[GraphPath]:
        return [p for r in self.reasons for p in r.graph_paths]

    def reason_messages(self) -> list[str]:
        return [r.message for r in self.reasons]