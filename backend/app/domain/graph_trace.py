"""Typed graph-reasoning representation for the UI.

This is a *projection* of evidence the deterministic safety engine already
produced - it adds no new reasoning and runs no additional queries. Every node
and edge here comes from a ``GraphPath`` that a safety rule actually walked
while reaching its decision.

Two rules govern this module:

1. **Nothing is invented.** If the engine did not traverse a relationship, it
   does not appear. Where a decision rests on something that is genuinely not a
   graph edge - equipment *absence*, which is a set difference - it is carried
   as a ``fact`` on the traversal rather than drawn as a fake relationship.
2. **The LLM never touches it.** Traces are built before composition and are
   re-checked against the same ``SafetyDecision`` objects the post-generation
   gate uses, so a trace can never describe a decision the engine did not make.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.ontology import ConceptGrounding
from app.domain.safety import EdgeDirection, NodeKind, SafetyStatus

ConstraintType = Literal[
    "injury_anatomy",
    "contraindication",
    "equipment",
    "explicit_exclusion",
    "preference_ranking",
    "data_gap",
]

EvidenceSource = Literal["graph_traversal", "deterministic_set_operation"]
"""Set operations (e.g. required-equipment minus available-equipment) are
deterministic but are not graph walks. Labelling them separately keeps the
"this came from the graph" claim precise."""

PathKind = Literal[
    "member_context", "anatomy_hierarchy", "exercise_structure", "set_operation"
]
"""Which half of the reasoning a path belongs to.

Classified here, from the node *kinds* the engine already recorded, so the UI
never has to infer it - inferring a path's role from edge names or reason text
would be exactly the frontend-invented structure this module exists to prevent.

* ``member_context``  - walks the member's own graph
  (Jordan -HAS_INJURY-> Left Knee -MAPS_TO-> PFPS -AFFECTS-> Patellofemoral Joint)
* ``anatomy_hierarchy`` - walks PART_OF between regions
  (Patellofemoral Joint -PART_OF-> Knee). Given its own kind because this is the
  hop the whole design rests on: the injury sits at a sub-structure while the
  catalog annotates the joint above it.
* ``exercise_structure`` - walks the catalog
  (Static Jump -HAS_PATTERN-> cardio - plyometric)
* ``set_operation``   - no edges were walked; the finding is a deterministic
  set difference or a data gap, stated as facts.
"""


class GraphTraceNode(BaseModel):
    id: str
    label: str
    type: NodeKind
    properties: dict[str, str] = Field(default_factory=dict)


class GraphTraceEdge(BaseModel):
    source_id: str
    target_id: str
    relationship: str
    direction: EdgeDirection = "outgoing"
    rule_id: str | None = None


class GraphTraversal(BaseModel):
    """One evidence path behind one decision about one exercise."""

    id: str
    constraint_type: ConstraintType
    exercise_id: str
    exercise_name: str
    decision: SafetyStatus
    reason: str
    rule_id: str | None = None
    source: EvidenceSource = "graph_traversal"
    path_kind: PathKind = "exercise_structure"
    nodes: list[GraphTraceNode] = Field(default_factory=list)
    edges: list[GraphTraceEdge] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    source_concept: str | None = None
    """The resolved coach phrase that introduced this constraint, when one did."""


class PromptConcept(BaseModel):
    """A resolver result, restated for the graph-reasoning view."""

    source_text: str
    canonical_id: str | None
    label: str | None
    concept_type: str | None
    method: str
    confidence: float
    resolved: bool
    # Optional and additive. Present only where the local concept carries a
    # verified published mapping; equipment and movement families legitimately
    # have none, and the UI renders nothing rather than an empty mapping.
    grounding: ConceptGrounding | None = None


class RuleCategoryCount(BaseModel):
    constraint_type: ConstraintType
    label: str
    exercises_affected: int
    traversals: int


class GraphReasoningSummary(BaseModel):
    """Counts, taken from the safety decisions rather than recomputed.

    These buckets are deliberately *not* presented as a partition. An exercise
    can be down-ranked and still be eligible and still be selected, so the UI
    labels each count for what it measures instead of implying they sum to the
    catalog total.
    """

    catalog_count: int
    excluded_count: int
    downranked_count: int
    eligible_count: int
    in_plan_count: int
    concepts_resolved: int
    concepts_unresolved: int
    traversal_count: int
    exercises_with_evidence: int
    counts_by_constraint: list[RuleCategoryCount] = Field(default_factory=list)
    note: str = (
        "Down-ranked exercises remain eligible and may appear in the plan; "
        "these counts describe overlapping sets, not a partition."
    )


class GraphReasoning(BaseModel):
    """The complete graph-reasoning payload attached to a workout response."""

    trace_id: str
    graph_backend: str
    summary: GraphReasoningSummary
    prompt_concepts: list[PromptConcept] = Field(default_factory=list)
    traversals: list[GraphTraversal] = Field(default_factory=list)
    member_facts: list[str] = Field(default_factory=list)

    def for_exercise(self, exercise_id: str) -> list[GraphTraversal]:
        return [t for t in self.traversals if t.exercise_id == exercise_id]
