"""The graph boundary.

Safety logic depends on this Protocol, never on the Neo4j driver. That is what
makes the highest-risk module unit-testable without a database, and what lets
the same traversal run against either backend.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.exercise import Exercise
from app.domain.graph_explorer import (
    GraphNodeView,
    GraphSearchResponse,
    GraphSubgraph,
)
from app.domain.member import MemberContext
from app.domain.safety import GraphPath
from app.graph.model import KnowledgeGraph


@runtime_checkable
class GraphRepository(Protocol):
    """Domain-level queries the rest of the app is allowed to make."""

    def list_exercises(self) -> list[Exercise]:
        """Every exercise in the catalog."""
        ...

    def get_exercise(self, exercise_id: str) -> Exercise | None: ...

    def get_member_context(self, member_id: str) -> MemberContext | None: ...

    def member_equipment(self, member_id: str) -> set[str]:
        """Canonical equipment names available to the member."""
        ...

    def exercise_required_equipment(self, exercise_id: str) -> list[str]: ...

    def exercise_patterns(self, exercise_id: str) -> list[str]: ...

    def exercise_stressed_regions(self, exercise_id: str) -> list[str]:
        """Canonical anatomy ids this exercise loads (via STRESSES)."""
        ...

    def injury_affected_regions(self, member_id: str) -> list[dict]:
        """For each member injury: the condition, region, closure, and evidence.

        Returns dicts shaped as::

            {
              "injury_id": ..., "injury_name": ..., "severity": ...,
              "status": ..., "body_side": "left" | None,
              "condition_id": ..., "condition_label": ...,
              "root_region": "patellofemoral_joint",
              "closure": {"patellofemoral_joint", "knee", "lower_limb"},
              "contraindicated_patterns": [...],
              "member_path": GraphPath,
            }
        """
        ...

    def part_of_path(self, start_region: str, target_region: str) -> GraphPath | None:
        """Evidence path start -PART_OF-> ... -> target, if one exists."""
        ...

    def stresses_path(self, exercise_id: str, region_id: str) -> GraphPath | None:
        """Evidence path Exercise -STRESSES-> region."""
        ...

    def patterns_in_family(self, family_id: str) -> list[str]: ...

    def exercises_with_pattern(self, pattern: str) -> list[str]: ...

    def graph(self) -> KnowledgeGraph:
        """Raw graph access for the inspector endpoint and stats."""
        ...

    def stats(self) -> dict[str, int]: ...

    # --- read-only exploration --------------------------------------------
    #
    # Added for the Knowledge Graph Explorer. Deliberately shaped as three
    # narrow operations rather than a query interface: the caller names a node
    # and a depth, and can never express a traversal the API did not design.
    # There is no method here that accepts a query language, and none that
    # writes.

    def search_nodes(
        self, query: str, kinds: list[str] | None = None, limit: int = 10
    ) -> GraphSearchResponse:
        """Ranked node matches by label, id or alias. Never auto-selects."""
        ...

    def get_node(self, node_id: str) -> GraphNodeView | None:
        """One node, with allowlisted properties and its ontology grounding."""
        ...

    def get_neighborhood(
        self,
        node_id: str,
        depth: int = 1,
        relationship_types: list[str] | None = None,
        node_kinds: list[str] | None = None,
    ) -> GraphSubgraph:
        """Bounded expansion from one node. Depth and size are clamped."""
        ...
