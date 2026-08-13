"""Read-only exploration over the property-graph projection.

Both backends share this implementation because both hold the identical
``KnowledgeGraph`` projection - the same object the safety engine traverses.
That is what makes the explorer honest: it browses the graph the application
actually reasons on, not a copy assembled for display.

The Neo4j backend additionally verifies its store agrees (see
``Neo4jGraphRepository.search_nodes``), so a drift between the projection and
what was seeded would surface rather than hide.

Three limits are enforced here rather than left to callers:

* search results are capped;
* neighborhood depth is clamped to ``MAX_DEPTH``;
* node count is capped, and truncation is *reported* rather than applied
  silently - a viewer that quietly drops neighbours misrepresents the graph.
"""

from __future__ import annotations

from app.domain.graph_explorer import (
    EXPLORABLE_KINDS,
    PROPERTY_ALLOWLIST,
    GraphEdgeView,
    GraphNodeView,
    GraphSearchHit,
    GraphSearchResponse,
    GraphSubgraph,
)
from app.graph import model as m
from app.graph.model import Edge, KnowledgeGraph
from app.ontology.grounding import to_concept_grounding
from app.ontology.loader import Ontology

DEFAULT_SEARCH_LIMIT = 10
MAX_SEARCH_LIMIT = 50
MAX_DEPTH = 2
MAX_NODES = 150

#: Resolver-style prefixes -> graph node labels, so a deep link built from a
#: canonical concept id (``anatomy:knee``) finds the node it names.
CANONICAL_PREFIX_TO_LABEL: dict[str, str] = {
    "anatomy": m.ANATOMICAL_REGION,
    "injury": m.INJURY_CONDITION,
    "equipment": m.EQUIPMENT,
    "exercise": m.EXERCISE,
    "muscle": m.MUSCLE,
    "movement_pattern": m.MOVEMENT_PATTERN,
    "movement_family": m.MOVEMENT_FAMILY,
    "member": m.MEMBER,
}

#: Inverse, for reporting a canonical id alongside a search hit.
LABEL_TO_CANONICAL_PREFIX = {
    label: prefix for prefix, label in CANONICAL_PREFIX_TO_LABEL.items()
}


class GraphExplorer:
    """Search and neighborhood traversal over one ``KnowledgeGraph``."""

    def __init__(self, graph: KnowledgeGraph, ontology: Ontology) -> None:
        self._graph = graph
        self._ontology = ontology

    # --- id handling ------------------------------------------------------

    def resolve_id(self, node_id: str) -> str | None:
        """Accept a graph key or a canonical concept id; return the graph key.

        Deep links elsewhere in the app are built from resolver ids, so the
        explorer accepts both rather than forcing every caller to know the
        graph's key format.
        """
        if not node_id:
            return None
        if node_id in self._graph.nodes:
            return node_id if self._explorable(node_id) else None

        prefix, _, identifier = node_id.partition(":")
        label = CANONICAL_PREFIX_TO_LABEL.get(prefix)
        if label and identifier:
            for candidate in (f"{label}:{identifier}", f"{label}:{m.slug(identifier)}"):
                if candidate in self._graph.nodes and self._explorable(candidate):
                    return candidate

        # Last resort: a bare id that is unique across the graph.
        matches = [
            key
            for key, node in self._graph.nodes.items()
            if str(node.properties.get("id", "")) == node_id
            and node.label in EXPLORABLE_KINDS
        ]
        return matches[0] if len(matches) == 1 else None

    def canonical_id(self, key: str) -> str | None:
        node = self._graph.nodes.get(key)
        if node is None:
            return None
        prefix = LABEL_TO_CANONICAL_PREFIX.get(node.label)
        return f"{prefix}:{node.properties.get('id')}" if prefix else None

    # --- search -----------------------------------------------------------

    def search(
        self,
        query: str,
        kinds: list[str] | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> GraphSearchResponse:
        """Rank matches by how directly they name the concept.

        Deliberately *not* concept resolution. The resolver must choose exactly
        one canonical concept and refuse when unsure, because a wrong choice
        applies a wrong safety rule. Search has no such consequence, so it
        returns several candidates and lets a human pick - and never
        auto-selects a weak match on the caller's behalf.
        """
        needle = (query or "").strip().lower()
        capped = max(1, min(limit, MAX_SEARCH_LIMIT))
        if not needle:
            return GraphSearchResponse(query=query, hits=[], count=0)

        allowed = set(kinds) if kinds else None
        scored: list[tuple[float, str, GraphSearchHit]] = []

        for key, node in self._graph.nodes.items():
            # The privacy gate first: unexplorable kinds are invisible here.
            if node.label not in EXPLORABLE_KINDS:
                continue
            if allowed is not None and node.label not in allowed:
                continue

            name = str(node.properties.get("name") or node.name or "").lower()
            identifier = str(node.properties.get("id", "")).lower()
            aliases = [str(a).lower() for a in (node.properties.get("aliases") or [])]

            if name == needle:
                match, score = "label", 1.0
            elif identifier == needle or key.lower() == needle:
                match, score = "id", 0.95
            elif needle in aliases:
                match, score = "alias", 0.9
            elif needle in name:
                # Shorter names are the better match for a substring hit.
                match, score = "substring", 0.6 + 0.2 / max(1, len(name))
            elif any(needle in alias for alias in aliases):
                match, score = "alias", 0.55
            else:
                continue

            scored.append(
                (
                    score,
                    name,
                    GraphSearchHit(
                        id=key,
                        label=node.name,
                        kind=node.label,
                        canonical_id=self.canonical_id(key),
                        match=match,  # type: ignore[arg-type]
                        score=round(score, 3),
                        degree=self._degree(key),
                    ),
                )
            )

        scored.sort(key=lambda row: (-row[0], row[1]))
        hits = [hit for _, _, hit in scored[:capped]]
        return GraphSearchResponse(
            query=query,
            hits=hits,
            count=len(hits),
            truncated=len(scored) > capped,
        )

    # --- nodes and neighborhoods -----------------------------------------

    def node_view(self, key: str) -> GraphNodeView | None:
        node = self._graph.nodes.get(key)
        if node is None or node.label not in EXPLORABLE_KINDS:
            return None

        allowed = PROPERTY_ALLOWLIST.get(node.label, ("id", "name"))
        properties = {
            name: value
            for name, value in node.properties.items()
            if name in allowed and isinstance(value, str | int | float | bool)
        }

        return GraphNodeView(
            id=key,
            label=node.name,
            kind=node.label,
            properties=properties,
            ontology_grounding=self._grounding(key),
            degree=self._degree(key),
        )

    def neighborhood(
        self,
        key: str,
        depth: int = 1,
        relationship_types: list[str] | None = None,
        node_kinds: list[str] | None = None,
        max_nodes: int = MAX_NODES,
    ) -> GraphSubgraph:
        """Bounded breadth-first expansion from one node.

        Never a whole-graph scan: expansion starts at a named node and stops at
        ``depth`` hops or ``max_nodes``, whichever comes first.
        """
        clamped_depth = max(1, min(depth, MAX_DEPTH))
        cap = max(1, min(max_nodes, MAX_NODES))
        rel_filter = set(relationship_types) if relationship_types else None
        kind_filter = set(node_kinds) if node_kinds else None

        collected: dict[str, GraphNodeView] = {}
        edges: dict[str, GraphEdgeView] = {}
        omitted = 0

        root = self.node_view(key)
        if root is None:
            return GraphSubgraph(root_id=key, depth=clamped_depth)
        collected[key] = root

        frontier = [key]
        for _ in range(clamped_depth):
            next_frontier: list[str] = []
            for current in frontier:
                for edge, direction in self._incident(current):
                    if rel_filter is not None and edge.type not in rel_filter:
                        continue
                    other = edge.target if direction == "outgoing" else edge.source
                    neighbour = self._graph.nodes.get(other)
                    if neighbour is None or neighbour.label not in EXPLORABLE_KINDS:
                        continue
                    if kind_filter is not None and neighbour.label not in kind_filter:
                        continue

                    if other not in collected:
                        if len(collected) >= cap:
                            omitted += 1
                            continue
                        view = self.node_view(other)
                        if view is None:
                            continue
                        collected[other] = view
                        next_frontier.append(other)

                    edge_id = f"{edge.source}|{edge.type}|{edge.target}"
                    if edge_id not in edges:
                        edges[edge_id] = GraphEdgeView(
                            id=edge_id,
                            source=edge.source,
                            target=edge.target,
                            relationship=edge.type,
                            direction=direction,
                            properties={
                                name: str(value)
                                for name, value in edge.properties.items()
                                if name in {"predicate", "mapping_version", "source_label"}
                                and value is not None
                            },
                        )
            frontier = next_frontier
            if not frontier:
                break

        return GraphSubgraph(
            root_id=key,
            nodes=list(collected.values()),
            edges=list(edges.values()),
            depth=clamped_depth,
            truncated=omitted > 0,
            omitted_count=omitted,
        )

    # --- internals --------------------------------------------------------

    def _incident(self, key: str) -> list[tuple[Edge, str]]:
        """Every edge touching ``key``, with its direction relative to it."""
        out: list[tuple[Edge, str]] = []
        for edge in self._graph.edges:
            if edge.source == key:
                out.append((edge, "outgoing"))
            elif edge.target == key:
                out.append((edge, "incoming"))
        return out

    def _explorable(self, key: str) -> bool:
        node = self._graph.nodes.get(key)
        return node is not None and node.label in EXPLORABLE_KINDS

    def _degree(self, key: str) -> int:
        return sum(
            1
            for edge in self._graph.edges
            if key in (edge.source, edge.target)
            and self._explorable(edge.source)
            and self._explorable(edge.target)
        )

    def _grounding(self, key: str):
        """Reuse the Phase 1 mapping set rather than re-reading node properties."""
        canonical = self.canonical_id(key)
        if canonical is None:
            return None
        # Muscle canonical ids are keyed on the catalog label, which is the
        # graph node's name rather than its slug id.
        node = self._graph.nodes.get(key)
        if node is not None and node.label == m.MUSCLE:
            canonical = f"muscle:{node.properties.get('name', '')}"
        return to_concept_grounding(self._ontology.grounding_for(canonical))
