"""Read-only graph explorer contracts.

The explorer is an *application feature*, not a database console. That
distinction drives every decision in this module:

* Raw Neo4j ``Node`` / ``Relationship`` objects never cross the boundary. What
  crosses is this normalized shape, identical whichever backend served it.
* Node properties are **allowlisted per kind**. Serialising whatever the graph
  happens to hold would leak ingestion keys today and member data tomorrow.
* There is no query field anywhere in these models. The API controls the shape
  of every traversal; the client chooses a node and a depth, never a query.

Ids are the graph's own node keys (``AnatomicalRegion:knee``). Canonical
resolver ids (``anatomy:knee``) are accepted as aliases so deep links from the
rest of the app work, but the key is what the graph actually holds.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.ontology import ConceptGrounding

#: Node kinds the explorer will surface. Taken from `app.graph.model`, not
#: invented for display: a category that does not exist in the graph cannot be
#: browsed in a viewer whose purpose is to show what the graph contains.
ExplorerNodeKind = Literal[
    "Exercise",
    "Muscle",
    "AnatomicalRegion",
    "MovementPattern",
    "MovementFamily",
    "Equipment",
    "InjuryCondition",
    "OntologyConcept",
    "Member",
    "Goal",
    "Preference",
    "Injury",
]

#: Node kinds the explorer will traverse **at all**.
#:
#: This is a privacy boundary, not a display preference. The member graph also
#: holds LabResult, DEXAResult, BiomarkerObservation, ChatMessage, CoachBrief,
#: AdherenceObservation, WorkoutSession and ChurnSignal nodes. None of them
#: explain how the clinical and exercise graphs connect, and all of them are
#: member health data, so the explorer cannot reach them: they are absent from
#: search, absent from every neighborhood, and absent from the legend.
#:
#: Membership here is the single gate. A node kind added to the graph later is
#: invisible to the explorer until it is deliberately listed.
EXPLORABLE_KINDS: frozenset[str] = frozenset(
    {
        "Exercise",
        "Muscle",
        "AnatomicalRegion",
        "MovementPattern",
        "MovementFamily",
        "Equipment",
        "InjuryCondition",
        "OntologyConcept",
        "Member",
        "Goal",
        "Preference",
        "Injury",
    }
)

#: Properties safe to expose, per node kind. Anything absent from this table is
#: dropped, so a new ingestion field cannot silently become public.
PROPERTY_ALLOWLIST: dict[str, tuple[str, ...]] = {
    "Exercise": (
        "id", "name", "priority_tier", "is_unilateral", "side",
        "loaded_body_side", "is_reps", "is_duration", "supports_weight",
        "estimated_rep_duration", "has_anatomy_data",
    ),
    "Muscle": ("id", "name", "ontology_source", "ontology_code", "ontology_term"),
    "AnatomicalRegion": (
        "id", "name", "unmapped", "ontology_source", "ontology_code",
        "ontology_term", "ontology_status", "mapping_predicate", "mapping_version",
    ),
    "MovementPattern": ("id", "name"),
    "MovementFamily": ("id", "name", "note"),
    "Equipment": ("id", "name"),
    "InjuryCondition": (
        "id", "name", "contraindication_note", "ontology_source",
        "ontology_code", "ontology_term", "ontology_status", "mapping_predicate",
    ),
    "OntologyConcept": ("id", "name", "source", "code", "uri", "status", "version"),
    # Member-side nodes are exposed at label level only. Names and ids are
    # enough to explain how member context joins the clinical graph; clinical
    # notes, chat and labs have no business in a graph viewer.
    "Member": ("id", "name", "tier"),
    "Goal": ("id", "name", "priority"),
    "Preference": ("id", "name"),
    "Injury": ("id", "name", "status", "severity", "body_side"),
}

#: Relationship semantics rendered in the legend. Definitions match
#: ARCHITECTURE.md rather than being restated loosely here.
RELATIONSHIP_GLOSSARY: dict[str, str] = {
    "TARGETS": "Exercise trains this muscle group.",
    "STRESSES": "Exercise places meaningful load on this anatomical region.",
    "REQUIRES": "Exercise cannot be performed without this equipment.",
    "HAS_PATTERN": "Exercise belongs to this movement pattern.",
    "IN_FAMILY": "Movement pattern belongs to this movement family.",
    "PART_OF": "Anatomical hierarchy: this region is part of the region it points to.",
    "AFFECTS": "Clinical condition affects this anatomical region.",
    "CONTRAINDICATES": "Clinical condition conflicts with this movement pattern.",
    "BILATERAL_PAIR": "Contralateral variant of the same exercise.",
    "MAPS_TO": "Recorded member injury maps to this clinical condition.",
    "HAS_INJURY": "Member has this recorded injury.",
    "HAS_EQUIPMENT": "Member has this equipment available.",
    "HAS_GOAL": "Member holds this training goal.",
    "HAS_PREFERENCE": "Member preference. Affects ranking only, never safety.",
    "DISLIKES": "Member dislikes this. Ranking only - never a safety exclusion.",
    "SKOS_EXACT_MATCH": (
        "Local concept denotes the same thing as the published ontology concept."
    ),
    "SKOS_CLOSE_MATCH": (
        "Local concept is a coarser product grouping overlapping the published concept."
    ),
    "SKOS_BROAD_MATCH": (
        "The published concept is broader; ours is a narrower part of it."
    ),
}


class GraphNodeView(BaseModel):
    id: str
    """The graph's own node key, e.g. ``AnatomicalRegion:knee``."""
    label: str
    kind: str
    properties: dict[str, str | int | float | bool] = Field(default_factory=dict)
    #: Present only where Phase 1 recorded a verified published mapping.
    ontology_grounding: ConceptGrounding | None = None
    #: Total edges on this node in the full graph, so the UI can say how much is
    #: not being shown without loading it.
    degree: int = 0


class GraphEdgeView(BaseModel):
    id: str
    source: str
    target: str
    relationship: str
    #: Relative to the node the neighborhood was expanded from.
    direction: Literal["outgoing", "incoming"] = "outgoing"
    properties: dict[str, str] = Field(default_factory=dict)


class GraphSubgraph(BaseModel):
    root_id: str
    nodes: list[GraphNodeView] = Field(default_factory=list)
    edges: list[GraphEdgeView] = Field(default_factory=list)
    depth: int = 1
    truncated: bool = False
    #: How many neighbours were reachable but not returned. Reported so the UI
    #: can say "additional neighbours not displayed" rather than silently lying
    #: about the shape of the graph.
    omitted_count: int = 0


class GraphSearchHit(BaseModel):
    id: str
    label: str
    kind: str
    #: The resolver-style canonical id where one exists, for deep linking.
    canonical_id: str | None = None
    match: Literal["label", "alias", "id", "substring"] = "label"
    score: float = 0.0
    degree: int = 0


class GraphSearchResponse(BaseModel):
    query: str
    hits: list[GraphSearchHit] = Field(default_factory=list)
    count: int = 0
    truncated: bool = False


class GraphStatsResponse(BaseModel):
    """Counts computed from the seeded graph, never from the brief."""

    graph_backend: str
    node_count: int
    edge_count: int
    nodes_by_kind: dict[str, int] = Field(default_factory=dict)
    edges_by_relationship: dict[str, int] = Field(default_factory=dict)
    ontology_mappings: int = 0


class RelationshipGlossaryEntry(BaseModel):
    relationship: str
    description: str
    count: int = 0


class GraphLegendResponse(BaseModel):
    node_kinds: list[str] = Field(default_factory=list)
    relationships: list[RelationshipGlossaryEntry] = Field(default_factory=list)
