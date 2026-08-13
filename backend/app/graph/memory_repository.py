"""In-memory GraphRepository.

Every method here is a genuine traversal over the property graph built by the
ingestion modules - adjacency lookups and PART_OF walks, not ad-hoc filtering of
the source JSON. That is what makes the safety decisions defensible and what the
Neo4j backend mirrors in Cypher.
"""

from __future__ import annotations

from pathlib import Path

from app.domain.exercise import Exercise
from app.domain.graph_explorer import (
    GraphNodeView,
    GraphSearchResponse,
    GraphSubgraph,
)
from app.domain.member import MemberContext
from app.domain.safety import GraphPath
from app.graph import model as m
from app.graph.explorer import GraphExplorer
from app.graph.model import KnowledgeGraph
from app.ingestion.exercises import ingest_exercise_graph, load_exercises
from app.ingestion.member import (
    build_exercise_name_index,
    ingest_member_graph,
    load_member_context,
)
from app.ontology.loader import Ontology, get_ontology


class InMemoryGraphRepository:
    """Builds and serves both subgraphs from the supplied JSON files."""

    def __init__(
        self,
        exercises: list[Exercise],
        member_contexts: dict[str, MemberContext],
        ontology: Ontology,
        graph: KnowledgeGraph,
    ) -> None:
        self._exercises = exercises
        self._exercises_by_id = {e.id: e for e in exercises}
        self._members = member_contexts
        self._ontology = ontology
        self._graph = graph
        self._explorer_cache: GraphExplorer | None = None

    # --- construction ----------------------------------------------------

    @classmethod
    def from_files(
        cls,
        exercises_path: Path,
        member_context_path: Path,
        ontology: Ontology | None = None,
    ) -> InMemoryGraphRepository:
        ontology = ontology or get_ontology()
        graph = KnowledgeGraph()

        exercises = load_exercises(exercises_path)
        ingest_exercise_graph(graph, exercises, ontology)

        context = load_member_context(member_context_path)
        ingest_member_graph(
            graph, context, ontology, exercise_name_index=build_exercise_name_index(exercises)
        )

        return cls(exercises, {context.profile.id: context}, ontology, graph)

    backend_name = "memory"

    # --- catalog ---------------------------------------------------------

    def list_exercises(self) -> list[Exercise]:
        return list(self._exercises)

    def get_exercise(self, exercise_id: str) -> Exercise | None:
        return self._exercises_by_id.get(exercise_id)

    # --- member ----------------------------------------------------------

    def get_member_context(self, member_id: str) -> MemberContext | None:
        if member_id in self._members:
            return self._members[member_id]
        # Convenience for demos: a single-member dataset resolves any id.
        if len(self._members) == 1:
            return next(iter(self._members.values()))
        return None

    def member_equipment(self, member_id: str) -> set[str]:
        mkey = self._member_key(member_id)
        if mkey is None:
            return set()
        return {node.name for node in self._graph.neighbors(mkey, m.HAS_EQUIPMENT)}

    def _member_key(self, member_id: str) -> str | None:
        key = m.member_key(member_id)
        if key in self._graph.nodes:
            return key
        members = self._graph.nodes_with_label(m.MEMBER)
        return members[0].key if len(members) == 1 else None

    # --- exercise edges --------------------------------------------------

    def exercise_required_equipment(self, exercise_id: str) -> list[str]:
        return [n.name for n in self._graph.neighbors(m.exercise_key(exercise_id), m.REQUIRES)]

    def exercise_patterns(self, exercise_id: str) -> list[str]:
        return [n.name for n in self._graph.neighbors(m.exercise_key(exercise_id), m.HAS_PATTERN)]

    def exercise_stressed_regions(self, exercise_id: str) -> list[str]:
        return [
            n.id for n in self._graph.neighbors(m.exercise_key(exercise_id), m.STRESSES)
        ]

    def stresses_path(self, exercise_id: str, region_id: str) -> GraphPath | None:
        ekey = m.exercise_key(exercise_id)
        for edge in self._graph.out_edges(ekey, m.STRESSES):
            if self._graph.nodes[edge.target].id == region_id:
                return GraphPath(
                    nodes=[self._graph.display(ekey), self._graph.display(edge.target)],
                    edges=[m.STRESSES],
                    node_kinds=["Exercise", "AnatomicalRegion"],
                    edge_directions=["outgoing"],
                )
        return None

    def part_of_path(self, start_region: str, target_region: str) -> GraphPath | None:
        chain = self._graph.path_up(
            m.anatomy_key(start_region), m.anatomy_key(target_region), m.PART_OF
        )
        if chain is None:
            return None
        return GraphPath(
            nodes=[self._graph.display(k) for k in chain],
            edges=[m.PART_OF] * (len(chain) - 1),
            node_kinds=["AnatomicalRegion"] * len(chain),
            edge_directions=["outgoing"] * (len(chain) - 1),
        )

    # --- injuries --------------------------------------------------------

    def injury_affected_regions(self, member_id: str) -> list[dict]:
        mkey = self._member_key(member_id)
        if mkey is None:
            return []

        results: list[dict] = []
        for injury_node in self._graph.neighbors(mkey, m.HAS_INJURY):
            condition_nodes = self._graph.neighbors(injury_node.key, m.MAPS_TO)
            condition = condition_nodes[0] if condition_nodes else None

            if condition is not None:
                region_nodes = self._graph.neighbors(condition.key, m.AFFECTS)
                patterns = [
                    n.name for n in self._graph.neighbors(condition.key, m.CONTRAINDICATES)
                ]
            else:
                # Unmapped injury: fall back to the direct AFFECTS edge.
                region_nodes = self._graph.neighbors(injury_node.key, m.AFFECTS)
                patterns = []

            if not region_nodes:
                continue
            root = region_nodes[0]

            member_path = GraphPath(
                nodes=[
                    self._graph.display(mkey),
                    injury_node.name,
                    *([condition.name] if condition is not None else []),
                    root.name,
                ],
                edges=[
                    m.HAS_INJURY,
                    *([m.MAPS_TO] if condition is not None else []),
                    m.AFFECTS,
                ],
                node_kinds=[
                    "Member",
                    "Injury",
                    *(["InjuryCondition"] if condition is not None else []),
                    "AnatomicalRegion",
                ],
                edge_directions=["outgoing"] * (3 if condition is not None else 2),
            )

            results.append(
                {
                    "injury_id": injury_node.id,
                    "injury_name": injury_node.name,
                    "severity": injury_node.properties.get("severity"),
                    "status": injury_node.properties.get("status"),
                    "body_side": injury_node.properties.get("body_side"),
                    "notes": injury_node.properties.get("notes"),
                    "condition_id": condition.id if condition else None,
                    "condition_label": condition.name if condition else None,
                    "root_region": root.id,
                    "root_region_label": root.name,
                    "closure": self._region_closure(root.id),
                    "contraindicated_patterns": patterns,
                    "member_path": member_path,
                }
            )
        return results

    def _region_closure(self, region_id: str) -> set[str]:
        """Anatomical closure by walking PART_OF in both directions.

        Ancestors matter most for this dataset: the injury sits at the
        patellofemoral joint while the catalog annotates exercises at "knee".
        """
        key = m.anatomy_key(region_id)
        closure = {region_id}
        for ancestor in self._graph.walk_up(key, m.PART_OF):
            closure.add(self._graph.nodes[ancestor].id)

        frontier = [key]
        seen = {key}
        while frontier:
            current = frontier.pop()
            for edge in self._graph.in_edges(current, m.PART_OF):
                if edge.source in seen:
                    continue
                seen.add(edge.source)
                closure.add(self._graph.nodes[edge.source].id)
                frontier.append(edge.source)
        return closure

    # --- movement families -----------------------------------------------

    def patterns_in_family(self, family_id: str) -> list[str]:
        fkey = m.family_key(family_id)
        return [n.name for n in self._graph.inbound(fkey, m.IN_FAMILY)]

    def exercises_with_pattern(self, pattern: str) -> list[str]:
        pkey = m.pattern_key(pattern)
        return [n.id for n in self._graph.inbound(pkey, m.HAS_PATTERN)]

    # --- raw -------------------------------------------------------------

    def graph(self) -> KnowledgeGraph:
        return self._graph

    def ontology(self) -> Ontology:
        return self._ontology

    def stats(self) -> dict[str, int]:
        return self._graph.stats()

    # --- read-only exploration --------------------------------------------
    #
    # Served from the same projection every safety traversal walks, so the
    # explorer shows the graph the application actually reasons on.

    @property
    def _explorer(self) -> GraphExplorer:
        if self._explorer_cache is None:
            self._explorer_cache = GraphExplorer(self._graph, self._ontology)
        return self._explorer_cache

    def search_nodes(
        self, query: str, kinds: list[str] | None = None, limit: int = 10
    ) -> GraphSearchResponse:
        return self._explorer.search(query, kinds=kinds, limit=limit)

    def get_node(self, node_id: str) -> GraphNodeView | None:
        key = self._explorer.resolve_id(node_id)
        return self._explorer.node_view(key) if key else None

    def get_neighborhood(
        self,
        node_id: str,
        depth: int = 1,
        relationship_types: list[str] | None = None,
        node_kinds: list[str] | None = None,
    ) -> GraphSubgraph:
        key = self._explorer.resolve_id(node_id)
        if key is None:
            return GraphSubgraph(root_id=node_id, depth=depth)
        return self._explorer.neighborhood(
            key,
            depth=depth,
            relationship_types=relationship_types,
            node_kinds=node_kinds,
        )
