"""Neo4j-backed GraphRepository.

Ingestion writes the *same* ``KnowledgeGraph`` projection the in-memory backend
builds, so the two cannot drift apart semantically. Queries then re-implement
the traversals in Cypher (see ``queries.py``), which is what makes the graph
reasoning inspectable in the Neo4j browser during review.

Nodes carry a generic ``:GraphNode`` label plus a ``label`` property. That keeps
the writer schema-agnostic without requiring APOC to be installed; the
domain label is still queryable and is applied as a second label where possible.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from neo4j import Driver, GraphDatabase

from app.domain.exercise import Exercise
from app.domain.member import MemberContext
from app.domain.safety import GraphPath
from app.graph import model as m
from app.graph import queries as q
from app.graph.model import KnowledgeGraph
from app.ingestion.exercises import ingest_exercise_graph, load_exercises
from app.ingestion.member import (
    build_exercise_name_index,
    ingest_member_graph,
    load_member_context,
)
from app.ontology.loader import Ontology, get_ontology

logger = logging.getLogger(__name__)

BATCH = 500


class Neo4jGraphRepository:
    def __init__(
        self,
        driver: Driver,
        database: str,
        exercises: list[Exercise],
        member_contexts: dict[str, MemberContext],
        ontology: Ontology,
        projection: KnowledgeGraph,
    ) -> None:
        self._driver = driver
        self._database = database
        self._exercises = exercises
        self._exercises_by_id = {e.id: e for e in exercises}
        self._members = member_contexts
        self._ontology = ontology
        self._projection = projection

    # --- construction ----------------------------------------------------

    @classmethod
    def connect(
        cls,
        uri: str,
        user: str,
        password: str,
        database: str,
        exercises_path: Path,
        member_context_path: Path,
        ontology: Ontology | None = None,
    ) -> Neo4jGraphRepository:
        ontology = ontology or get_ontology()
        projection = KnowledgeGraph()

        exercises = load_exercises(exercises_path)
        ingest_exercise_graph(projection, exercises, ontology)
        context = load_member_context(member_context_path)
        ingest_member_graph(
            projection,
            context,
            ontology,
            exercise_name_index=build_exercise_name_index(exercises),
        )

        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        return cls(
            driver, database, exercises, {context.profile.id: context}, ontology, projection
        )

    def close(self) -> None:
        self._driver.close()

    # --- seeding ---------------------------------------------------------

    def seed(self, wipe: bool = True) -> dict[str, int]:
        """Write the projection to Neo4j. Idempotent when ``wipe`` is True."""
        with self._driver.session(database=self._database) as session:
            if wipe:
                session.run(q.WIPE)
            for statement in q.CONSTRAINTS:
                try:
                    session.run(statement)
                except Exception as exc:  # pragma: no cover - server-version dependent
                    logger.debug("constraint skipped: %s", exc)

            nodes = [
                {
                    "key": node.key,
                    "label": node.label,
                    "properties": _clean(node.properties | {"key": node.key}),
                }
                for node in self._projection.nodes.values()
            ]
            for chunk in _chunks(nodes, BATCH):
                session.run(q.MERGE_NODE_FALLBACK, rows=chunk)

            # Apply the domain label as a real Neo4j label for browsability.
            for label in {node.label for node in self._projection.nodes.values()}:
                session.run(
                    f"MATCH (n:GraphNode {{label: $label}}) SET n:`{label}`", label=label
                )

            edges_by_type: dict[str, list[dict[str, Any]]] = {}
            for edge in self._projection.edges:
                edges_by_type.setdefault(edge.type, []).append(
                    {
                        "source": edge.source,
                        "target": edge.target,
                        "properties": _clean(edge.properties),
                    }
                )
            for rel_type, rows in edges_by_type.items():
                statement = (
                    "UNWIND $rows AS row "
                    "MATCH (a:GraphNode {key: row.source}) "
                    "MATCH (b:GraphNode {key: row.target}) "
                    f"MERGE (a)-[r:`{rel_type}`]->(b) "
                    "SET r += row.properties"
                )
                for chunk in _chunks(rows, BATCH):
                    session.run(statement, rows=chunk)

        return self.stats()

    backend_name = "neo4j"

    # --- reads -----------------------------------------------------------

    def _read(self, statement: str, **params: Any) -> list[dict[str, Any]]:
        with self._driver.session(database=self._database) as session:
            return [record.data() for record in session.run(statement, **params)]

    def list_exercises(self) -> list[Exercise]:
        # Served from the validated projection: the catalog is immutable at
        # runtime and Pydantic models are the contract the app is typed against.
        return list(self._exercises)

    def get_exercise(self, exercise_id: str) -> Exercise | None:
        return self._exercises_by_id.get(exercise_id)

    def get_member_context(self, member_id: str) -> MemberContext | None:
        if member_id in self._members:
            return self._members[member_id]
        return next(iter(self._members.values()), None) if len(self._members) == 1 else None

    def member_equipment(self, member_id: str) -> set[str]:
        rows = self._read(q.MEMBER_EQUIPMENT, member_key=m.member_key(member_id))
        return {row["name"] for row in rows if row.get("name")}

    def exercise_required_equipment(self, exercise_id: str) -> list[str]:
        rows = self._read(
            q.EXERCISE_REQUIRED_EQUIPMENT, exercise_key=m.exercise_key(exercise_id)
        )
        return [row["name"] for row in rows if row.get("name")]

    def exercise_patterns(self, exercise_id: str) -> list[str]:
        rows = self._read(q.EXERCISE_PATTERNS, exercise_key=m.exercise_key(exercise_id))
        return [row["name"] for row in rows if row.get("name")]

    def exercise_stressed_regions(self, exercise_id: str) -> list[str]:
        rows = self._read(
            q.EXERCISE_STRESSED_REGIONS, exercise_key=m.exercise_key(exercise_id)
        )
        return [row["id"] for row in rows if row.get("id")]

    def stresses_path(self, exercise_id: str, region_id: str) -> GraphPath | None:
        rows = self._read(
            q.STRESSES_PATH, exercise_key=m.exercise_key(exercise_id), region_id=region_id
        )
        if not rows:
            return None
        return GraphPath(
            nodes=[rows[0]["exercise"], rows[0]["region"]],
            edges=[m.STRESSES],
            node_kinds=["Exercise", "AnatomicalRegion"],
            edge_directions=["outgoing"],
        )

    def part_of_path(self, start_region: str, target_region: str) -> GraphPath | None:
        if start_region == target_region:
            node = self._projection.nodes.get(m.anatomy_key(start_region))
            return GraphPath(
                nodes=[node.name if node else start_region],
                edges=[],
                node_kinds=["AnatomicalRegion"],
            )
        rows = self._read(
            q.PART_OF_PATH,
            start_key=m.anatomy_key(start_region),
            target_key=m.anatomy_key(target_region),
        )
        if not rows:
            return None
        names = rows[0]["names"]
        return GraphPath(
            nodes=names,
            edges=[m.PART_OF] * (len(names) - 1),
            node_kinds=["AnatomicalRegion"] * len(names),
            edge_directions=["outgoing"] * (len(names) - 1),
        )

    def injury_affected_regions(self, member_id: str) -> list[dict]:
        rows = self._read(q.INJURY_AFFECTED_REGIONS, member_key=m.member_key(member_id))
        results: list[dict] = []
        member_name = self.get_member_context(member_id)
        display = member_name.profile.name if member_name else member_id

        for row in rows:
            root = row.get("root_region")
            if not root:
                continue
            nodes = [display, row["injury_name"]]
            edges = [m.HAS_INJURY]
            kinds: list[str] = ["Member", "Injury"]
            if row.get("condition_label"):
                nodes.append(row["condition_label"])
                edges.append(m.MAPS_TO)
                kinds.append("InjuryCondition")
            nodes.append(row.get("root_region_label") or root)
            edges.append(m.AFFECTS)
            kinds.append("AnatomicalRegion")

            results.append(
                {
                    "injury_id": row["injury_id"],
                    "injury_name": row["injury_name"],
                    "severity": row.get("severity"),
                    "status": row.get("status"),
                    "body_side": row.get("body_side"),
                    "notes": row.get("notes"),
                    "condition_id": row.get("condition_id"),
                    "condition_label": row.get("condition_label"),
                    "root_region": root,
                    "root_region_label": row.get("root_region_label"),
                    "closure": self._closure(root),
                    "contraindicated_patterns": [
                        p for p in (row.get("contraindicated_patterns") or []) if p
                    ],
                    "member_path": GraphPath(
                        nodes=nodes,
                        edges=edges,
                        node_kinds=kinds,  # type: ignore[arg-type]
                        edge_directions=["outgoing"] * len(edges),
                    ),
                }
            )
        return results

    def _closure(self, region_id: str) -> set[str]:
        rows = self._read(q.ANATOMICAL_CLOSURE, region_key=m.anatomy_key(region_id))
        return {row["id"] for row in rows if row.get("id")}

    def patterns_in_family(self, family_id: str) -> list[str]:
        rows = self._read(q.PATTERNS_IN_FAMILY, family_key=m.family_key(family_id))
        return [row["name"] for row in rows if row.get("name")]

    def exercises_with_pattern(self, pattern: str) -> list[str]:
        rows = self._read(q.EXERCISES_WITH_PATTERN, pattern_key=m.pattern_key(pattern))
        return [row["id"] for row in rows if row.get("id")]

    def exercise_provenance(self, exercise_id: str) -> dict[str, Any]:
        rows = self._read(q.EXERCISE_PROVENANCE, exercise_key=m.exercise_key(exercise_id))
        return rows[0] if rows else {}

    def graph(self) -> KnowledgeGraph:
        return self._projection

    def ontology(self) -> Ontology:
        return self._ontology

    def stats(self) -> dict[str, int]:
        try:
            rows = self._read(q.GRAPH_STATS)
            return {row["key"]: row["count"] for row in rows}
        except Exception as exc:  # pragma: no cover
            logger.warning("stats query failed, using projection: %s", exc)
            return self._projection.stats()


def _clean(properties: dict[str, Any]) -> dict[str, Any]:
    """Neo4j accepts only primitives and homogeneous lists of primitives."""
    cleaned: dict[str, Any] = {}
    for key, value in properties.items():
        if value is None:
            continue
        if isinstance(value, str | int | float | bool):
            cleaned[key] = value
        elif isinstance(value, list):
            flat = [v for v in value if isinstance(v, str | int | float | bool)]
            if flat:
                cleaned[key] = flat
        elif isinstance(value, dict):
            continue  # nested structures live in the API layer, not the graph
    return cleaned


def _chunks(rows: list, size: int):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]
