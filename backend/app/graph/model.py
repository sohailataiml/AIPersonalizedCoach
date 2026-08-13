"""Property-graph primitives shared by the in-memory and Neo4j backends.

Both backends ingest into this same structure, which means the safety engine
traverses identical topology regardless of where the graph is stored. The
in-memory backend walks it directly; the Neo4j backend writes it out as nodes
and relationships and walks it again with Cypher.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

# --- node labels -------------------------------------------------------------
EXERCISE = "Exercise"
MUSCLE = "Muscle"
ANATOMICAL_REGION = "AnatomicalRegion"
MOVEMENT_PATTERN = "MovementPattern"
MOVEMENT_FAMILY = "MovementFamily"
EQUIPMENT = "Equipment"
INJURY_CONDITION = "InjuryCondition"
ONTOLOGY_CONCEPT = "OntologyConcept"

MEMBER = "Member"
GOAL = "Goal"
PREFERENCE = "Preference"
INJURY = "Injury"
WORKOUT_SESSION = "WorkoutSession"
EXERCISE_PERFORMANCE = "ExercisePerformance"
ADHERENCE_OBSERVATION = "AdherenceObservation"
BIOMARKER_OBSERVATION = "BiomarkerObservation"
LAB_RESULT = "LabResult"
DEXA_RESULT = "DEXAResult"
CHAT_MESSAGE = "ChatMessage"
COACH_BRIEF = "CoachBrief"
CHURN_SIGNAL = "ChurnSignal"

# --- relationship types ------------------------------------------------------
TARGETS = "TARGETS"
STRESSES = "STRESSES"
REQUIRES = "REQUIRES"
HAS_PATTERN = "HAS_PATTERN"
IN_FAMILY = "IN_FAMILY"
PART_OF = "PART_OF"
AFFECTS = "AFFECTS"
CONTRAINDICATES = "CONTRAINDICATES"
BILATERAL_PAIR = "BILATERAL_PAIR"
SKOS_EXACT_MATCH = "SKOS_EXACT_MATCH"
SKOS_CLOSE_MATCH = "SKOS_CLOSE_MATCH"
SKOS_BROAD_MATCH = "SKOS_BROAD_MATCH"

SKOS_RELATION_BY_PREDICATE = {
    "skos:exactMatch": SKOS_EXACT_MATCH,
    "skos:closeMatch": SKOS_CLOSE_MATCH,
    "skos:broadMatch": SKOS_BROAD_MATCH,
}
"""Mapping predicate -> relationship type.

Kept as an explicit table rather than a string transform so an unrecognised
predicate fails to find an edge type instead of silently minting a new
relationship the rest of the system does not know about.
"""

HAS_GOAL = "HAS_GOAL"
HAS_PREFERENCE = "HAS_PREFERENCE"
HAS_INJURY = "HAS_INJURY"
MAPS_TO = "MAPS_TO"
HAS_EQUIPMENT = "HAS_EQUIPMENT"
COMPLETED = "COMPLETED"
SCHEDULED = "SCHEDULED"
CONTAINS = "CONTAINS"
PERFORMED_EXERCISE = "PERFORMED_EXERCISE"
HAS_ADHERENCE = "HAS_ADHERENCE"
HAS_BIOMARKER = "HAS_BIOMARKER"
HAS_LAB_RESULT = "HAS_LAB_RESULT"
HAS_DEXA_RESULT = "HAS_DEXA_RESULT"
PARTICIPATED_IN = "PARTICIPATED_IN"
HAS_BRIEF = "HAS_BRIEF"
HAS_CHURN_SIGNAL = "HAS_CHURN_SIGNAL"
DISLIKES = "DISLIKES"


@dataclass
class Node:
    key: str
    """Stable unique key, e.g. ``AnatomicalRegion:knee``."""
    label: str
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return str(self.properties.get("id", self.key.split(":", 1)[-1]))

    @property
    def name(self) -> str:
        return str(self.properties.get("name") or self.properties.get("label") or self.id)


@dataclass
class Edge:
    source: str
    type: str
    target: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeGraph:
    """A small property graph with adjacency indexes for traversal."""

    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    _out: dict[tuple[str, str], list[Edge]] = field(default_factory=lambda: defaultdict(list))
    _in: dict[tuple[str, str], list[Edge]] = field(default_factory=lambda: defaultdict(list))

    # --- construction ----------------------------------------------------

    def add_node(self, key: str, label: str, **properties: Any) -> Node:
        existing = self.nodes.get(key)
        if existing is not None:
            existing.properties.update({k: v for k, v in properties.items() if v is not None})
            return existing
        node = Node(key=key, label=label, properties={k: v for k, v in properties.items()})
        self.nodes[key] = node
        return node

    def add_edge(self, source: str, rel_type: str, target: str, **properties: Any) -> Edge | None:
        """Add an edge. Silently ignores dangling endpoints.

        Dangling edges are a real condition in the supplied data: all 18
        ``bilateral_pair_id`` values reference exercises that are not part of
        the 50-row catalog. We record what we can and never crash on it.
        """
        if source not in self.nodes or target not in self.nodes:
            return None
        edge = Edge(source=source, type=rel_type, target=target, properties=dict(properties))
        self.edges.append(edge)
        self._out[(source, rel_type)].append(edge)
        self._in[(target, rel_type)].append(edge)
        return edge

    # --- traversal -------------------------------------------------------

    def out_edges(self, key: str, rel_type: str) -> list[Edge]:
        return list(self._out.get((key, rel_type), []))

    def in_edges(self, key: str, rel_type: str) -> list[Edge]:
        return list(self._in.get((key, rel_type), []))

    def neighbors(self, key: str, rel_type: str) -> list[Node]:
        return [self.nodes[e.target] for e in self.out_edges(key, rel_type)]

    def inbound(self, key: str, rel_type: str) -> list[Node]:
        return [self.nodes[e.source] for e in self.in_edges(key, rel_type)]

    def walk_up(self, key: str, rel_type: str) -> list[str]:
        """Follow ``rel_type`` upward, returning the chain of visited keys."""
        chain: list[str] = []
        seen = {key}
        current = key
        while True:
            outs = self.out_edges(current, rel_type)
            if not outs:
                return chain
            nxt = outs[0].target
            if nxt in seen:
                return chain
            seen.add(nxt)
            chain.append(nxt)
            current = nxt

    def path_up(self, start: str, target: str, rel_type: str) -> list[str] | None:
        """The chain start -> ... -> target following ``rel_type``, if reachable."""
        if start == target:
            return [start]
        chain = [start]
        for key in self.walk_up(start, rel_type):
            chain.append(key)
            if key == target:
                return chain
        return None

    def nodes_with_label(self, label: str) -> list[Node]:
        return [n for n in self.nodes.values() if n.label == label]

    def label_of(self, key: str) -> str:
        node = self.nodes.get(key)
        return node.label if node else "Unknown"

    def display(self, key: str) -> str:
        node = self.nodes.get(key)
        return node.name if node else key

    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for node in self.nodes.values():
            counts[f"node:{node.label}"] += 1
        for edge in self.edges:
            counts[f"edge:{edge.type}"] += 1
        return dict(sorted(counts.items()))


# --- key helpers -------------------------------------------------------------


def slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(value).strip().lower()).strip("_")


def exercise_key(exercise_id: str) -> str:
    return f"{EXERCISE}:{exercise_id}"


def anatomy_key(anatomy_id: str) -> str:
    return f"{ANATOMICAL_REGION}:{anatomy_id}"


def muscle_key(name: str) -> str:
    return f"{MUSCLE}:{slug(name)}"


def pattern_key(name: str) -> str:
    return f"{MOVEMENT_PATTERN}:{slug(name)}"


def family_key(name: str) -> str:
    return f"{MOVEMENT_FAMILY}:{slug(name)}"


def equipment_key(name: str) -> str:
    return f"{EQUIPMENT}:{slug(name)}"


def injury_condition_key(condition_id: str) -> str:
    return f"{INJURY_CONDITION}:{condition_id}"


def ontology_key(source: str, code: str) -> str:
    return f"{ONTOLOGY_CONCEPT}:{slug(source)}_{slug(code)}"


def member_key(member_id: str) -> str:
    return f"{MEMBER}:{member_id}"
