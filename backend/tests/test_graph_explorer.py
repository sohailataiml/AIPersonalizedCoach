"""Knowledge Graph Explorer tests.

Two properties, in order of how much damage a failure would do:

1. **It is not a database console.** No endpoint accepts a query language, none
   writes, and no credential or raw driver object crosses the boundary. Several
   tests here exist purely to fail if someone later adds one.
2. **It shows the real graph.** Nodes, edges, relationship names and ontology
   grounding all come from the graph the safety engine traverses — never from a
   shape invented for display.

The Neo4j parity tests run against a live container when one is reachable and
skip otherwise, so the suite stays runnable with no Docker.
"""

from __future__ import annotations

import json

import pytest

from app.domain.graph_explorer import (
    EXPLORABLE_KINDS,
    PROPERTY_ALLOWLIST,
    RELATIONSHIP_GLOSSARY,
)
from app.graph import model as graph_model
from app.graph.explorer import MAX_DEPTH, MAX_NODES, MAX_SEARCH_LIMIT
from app.ontology.loader import get_ontology

from .conftest import MEMBER_ID

KNEE = "AnatomicalRegion:knee"


def _exercise_id(repository, name: str) -> str:
    hit = next(
        h
        for h in repository.search_nodes(name, kinds=["Exercise"], limit=5).hits
        if h.label == name
    )
    return hit.id


# --- search ------------------------------------------------------------------


class TestSearch:
    def test_exact_label_ranks_first(self, repository):
        hits = repository.search_nodes("knee").hits
        assert hits[0].id == KNEE
        assert hits[0].kind == "AnatomicalRegion"
        assert hits[0].match == "label"

    def test_partial_match_is_found_and_labelled(self, repository):
        hits = repository.search_nodes("patellofem").hits
        assert hits
        assert any("Patellofemoral" in hit.label for hit in hits)
        assert all(hit.match in {"label", "alias", "id", "substring"} for hit in hits)

    def test_alias_search_reaches_the_canonical_concept(self, repository):
        hits = repository.search_nodes("runners knee").hits
        assert any(hit.id == "InjuryCondition:patellofemoral_pain_syndrome" for hit in hits)

    def test_exercise_search_by_name(self, repository):
        hits = repository.search_nodes("Static Jump").hits
        assert hits[0].kind == "Exercise"
        assert hits[0].label == "Static Jump"

    def test_no_result_returns_empty_rather_than_a_guess(self, repository):
        result = repository.search_nodes("zorblatt machine")
        assert result.hits == []
        assert result.count == 0

    def test_empty_query_returns_nothing(self, repository):
        assert repository.search_nodes("   ").hits == []

    def test_search_can_be_restricted_by_kind(self, repository):
        hits = repository.search_nodes("knee", kinds=["Exercise"]).hits
        assert all(hit.kind == "Exercise" for hit in hits)

    def test_search_is_capped_and_reports_truncation(self, repository):
        result = repository.search_nodes("a", limit=3)
        assert len(result.hits) <= 3
        if result.truncated:
            assert len(result.hits) == 3

    def test_the_limit_cannot_be_raised_past_the_cap(self, repository):
        result = repository.search_nodes("a", limit=10_000)
        assert len(result.hits) <= MAX_SEARCH_LIMIT

    def test_hits_expose_a_canonical_id_for_deep_linking(self, repository):
        hit = repository.search_nodes("knee").hits[0]
        assert hit.canonical_id == "anatomy:knee"


# --- node detail -------------------------------------------------------------


class TestNodeDetail:
    def test_a_node_can_be_fetched_by_graph_key(self, repository):
        node = repository.get_node(KNEE)
        assert node is not None
        assert node.kind == "AnatomicalRegion"
        assert node.label == "Knee"

    def test_a_node_can_be_fetched_by_canonical_id(self, repository):
        """Deep links elsewhere in the app are built from resolver ids."""
        assert repository.get_node("anatomy:knee") == repository.get_node(KNEE)

    def test_an_unknown_node_is_none_not_an_error(self, repository):
        assert repository.get_node("AnatomicalRegion:nope") is None
        assert repository.get_node("") is None

    def test_ontology_grounding_comes_from_the_verified_mapping_set(self, repository):
        node = repository.get_node("anatomy:knee")
        assert node.ontology_grounding is not None
        assert node.ontology_grounding.ontology_code == "72696002"
        assert node.ontology_grounding.mapping_relation == "exactMatch"

    def test_an_unmapped_concept_reports_no_grounding(self, repository):
        """Equipment is deliberately ungrounded - that is a decision, not a gap."""
        node = repository.get_node("equipment:dumbbell")
        assert node is not None
        assert node.ontology_grounding is None

    def test_degree_reflects_the_whole_graph_not_the_loaded_slice(self, repository):
        node = repository.get_node(KNEE)
        edges = sum(
            1 for e in repository.graph().edges if KNEE in (e.source, e.target)
        )
        assert node.degree == edges


class TestPropertyAllowlist:
    def test_only_allowlisted_properties_are_exposed(self, repository):
        for key in list(repository.graph().nodes)[:80]:
            node = repository.get_node(key)
            if node is None:
                continue
            allowed = set(PROPERTY_ALLOWLIST.get(node.kind, ("id", "name")))
            assert set(node.properties) <= allowed, node.kind

    def test_ingestion_internals_never_leak(self, repository):
        """`aliases` and `bilateral_pair_id` are ingestion detail, not content."""
        for key in (KNEE, "InjuryCondition:patellofemoral_pain_syndrome"):
            node = repository.get_node(key)
            assert "aliases" not in node.properties
            assert "bilateral_pair_id" not in node.properties

    def test_member_nodes_expose_no_clinical_free_text(self, repository):
        """A graph viewer has no business showing notes, chat or labs."""
        member_keys = [
            key
            for key, node in repository.graph().nodes.items()
            if node.label in {"Member", "Injury", "Goal", "Preference"}
        ]
        assert member_keys
        for key in member_keys:
            node = repository.get_node(key)
            assert "notes" not in node.properties
            assert "snomedct_hint" not in node.properties


# --- neighborhood ------------------------------------------------------------


class TestNeighborhood:
    def test_one_hop_returns_the_root_and_its_neighbours(self, repository):
        subgraph = repository.get_neighborhood(KNEE, depth=1)
        assert subgraph.root_id == KNEE
        assert subgraph.depth == 1
        assert any(node.id == KNEE for node in subgraph.nodes)
        assert len(subgraph.nodes) > 1
        assert subgraph.edges

    def test_two_hops_returns_strictly_more(self, repository):
        one = repository.get_neighborhood(KNEE, depth=1)
        two = repository.get_neighborhood(KNEE, depth=2)
        assert len(two.nodes) > len(one.nodes)
        assert two.depth == 2

    def test_depth_beyond_the_maximum_is_clamped_not_rejected(self, repository):
        subgraph = repository.get_neighborhood(KNEE, depth=99)
        assert subgraph.depth == MAX_DEPTH

    def test_depth_below_one_is_clamped(self, repository):
        assert repository.get_neighborhood(KNEE, depth=0).depth == 1

    def test_an_unknown_root_yields_an_empty_subgraph(self, repository):
        subgraph = repository.get_neighborhood("AnatomicalRegion:nope")
        assert subgraph.nodes == []
        assert subgraph.edges == []

    def test_anatomy_hierarchy_is_returned(self, repository):
        subgraph = repository.get_neighborhood(KNEE, depth=1)
        part_of = [e for e in subgraph.edges if e.relationship == graph_model.PART_OF]
        assert part_of
        labels = {n.id: n.label for n in subgraph.nodes}
        assert any(
            labels.get(e.source) == "Knee" and labels.get(e.target) == "Lower Limb"
            for e in part_of
        )

    def test_exercise_stresses_and_patterns_are_returned(self, repository):
        jump = _exercise_id(repository, "Static Jump")
        subgraph = repository.get_neighborhood(jump, depth=1)
        relationships = {edge.relationship for edge in subgraph.edges}

        assert graph_model.STRESSES in relationships
        assert graph_model.HAS_PATTERN in relationships
        assert graph_model.TARGETS in relationships

    def test_equipment_requires_is_returned(self, repository):
        goblet = _exercise_id(repository, "Dumbbell Goblet Split Squat")
        subgraph = repository.get_neighborhood(goblet, depth=1)
        assert graph_model.REQUIRES in {e.relationship for e in subgraph.edges}

    def test_condition_affects_and_contraindicates_are_returned(self, repository):
        subgraph = repository.get_neighborhood(
            "InjuryCondition:patellofemoral_pain_syndrome", depth=1
        )
        relationships = {edge.relationship for edge in subgraph.edges}
        assert graph_model.AFFECTS in relationships
        assert graph_model.CONTRAINDICATES in relationships

    def test_skos_mappings_are_returned(self, repository):
        subgraph = repository.get_neighborhood(KNEE, depth=1)
        assert graph_model.SKOS_EXACT_MATCH in {
            edge.relationship for edge in subgraph.edges
        }
        ontology_nodes = [n for n in subgraph.nodes if n.kind == "OntologyConcept"]
        assert ontology_nodes
        assert ontology_nodes[0].properties.get("code") == "72696002"

    def test_member_context_joins_the_clinical_graph(self, repository):
        member_key = graph_model.member_key(MEMBER_ID)
        subgraph = repository.get_neighborhood(member_key, depth=2)
        relationships = {edge.relationship for edge in subgraph.edges}

        assert graph_model.HAS_INJURY in relationships
        assert graph_model.MAPS_TO in relationships

    def test_relationship_filtering_applies(self, repository):
        subgraph = repository.get_neighborhood(
            KNEE, depth=1, relationship_types=[graph_model.PART_OF]
        )
        assert {e.relationship for e in subgraph.edges} == {graph_model.PART_OF}

    def test_node_kind_filtering_applies(self, repository):
        subgraph = repository.get_neighborhood(
            KNEE, depth=1, node_kinds=["OntologyConcept"]
        )
        kinds = {n.kind for n in subgraph.nodes if n.id != KNEE}
        assert kinds <= {"OntologyConcept"}

    def test_the_node_cap_is_enforced(self, repository):
        subgraph = repository.get_neighborhood(KNEE, depth=2)
        assert len(subgraph.nodes) <= MAX_NODES

    def test_truncation_is_reported_rather_than_silent(self, repository, ontology):
        """A viewer that silently drops neighbours misrepresents the graph."""
        from app.graph.explorer import GraphExplorer

        explorer = GraphExplorer(repository.graph(), ontology)
        subgraph = explorer.neighborhood(KNEE, depth=2, max_nodes=5)

        assert len(subgraph.nodes) <= 5
        assert subgraph.truncated is True
        assert subgraph.omitted_count > 0

    def test_edges_never_reference_an_absent_node(self, repository):
        subgraph = repository.get_neighborhood(KNEE, depth=2)
        present = {node.id for node in subgraph.nodes}
        for edge in subgraph.edges:
            assert edge.source in present
            assert edge.target in present

    def test_relationships_are_real_graph_relationship_types(self, repository):
        declared = {
            value
            for name, value in vars(graph_model).items()
            if name.isupper() and isinstance(value, str) and name == value
        }
        subgraph = repository.get_neighborhood(KNEE, depth=2)
        assert {e.relationship for e in subgraph.edges} <= declared

    def test_no_fabricated_absence_relationship_exists(self, repository):
        """Equipment absence stays a set-operation fact, as Phase 3 established."""
        relationships = {edge.type for edge in repository.graph().edges}
        assert "DOES_NOT_HAVE" not in relationships


# --- serialization -----------------------------------------------------------


class TestSerialization:
    def test_no_raw_driver_object_can_serialize(self, repository):
        subgraph = repository.get_neighborhood(KNEE, depth=1)
        payload = json.loads(subgraph.model_dump_json())

        assert set(payload) == {
            "root_id", "nodes", "edges", "depth", "truncated", "omitted_count",
        }
        for node in payload["nodes"]:
            assert set(node) == {
                "id", "label", "kind", "properties", "ontology_grounding", "degree",
            }

    def test_no_credential_or_connection_detail_appears(self, repository):
        payload = repository.get_neighborhood(KNEE, depth=2).model_dump_json().lower()
        for secret in ("bolt://", "neo4j://", "password", "credential", "cypher"):
            assert secret not in payload

    def test_the_glossary_covers_every_reachable_relationship(self, repository):
        """Anything the explorer can show must be explained in the legend."""
        graph = repository.graph()
        explorable = {
            key for key, node in graph.nodes.items() if node.label in EXPLORABLE_KINDS
        }
        used = {
            edge.type
            for edge in graph.edges
            if edge.source in explorable and edge.target in explorable
        }
        missing = used - set(RELATIONSHIP_GLOSSARY)
        assert missing == set(), f"undocumented relationships: {missing}"


class TestPrivacyGate:
    """Member health data is unreachable, not merely unrendered."""

    HIDDEN_KINDS = (
        "LabResult",
        "DEXAResult",
        "BiomarkerObservation",
        "ChatMessage",
        "CoachBrief",
        "ChurnSignal",
        "AdherenceObservation",
        "WorkoutSession",
        "ExercisePerformance",
    )

    def test_the_graph_really_holds_the_hidden_kinds(self, repository):
        """Guards the premise: this test is meaningless if they are absent."""
        present = {node.label for node in repository.graph().nodes.values()}
        assert set(self.HIDDEN_KINDS) & present

    def test_hidden_kinds_are_absent_from_search(self, repository):
        for term in ("lab", "sleep", "brief", "churn", "session", "weight"):
            for hit in repository.search_nodes(term, limit=50).hits:
                assert hit.kind not in self.HIDDEN_KINDS

    def test_hidden_nodes_cannot_be_addressed_directly(self, repository):
        hidden = [
            key
            for key, node in repository.graph().nodes.items()
            if node.label in self.HIDDEN_KINDS
        ]
        assert hidden
        for key in hidden[:20]:
            assert repository.get_node(key) is None
            assert repository.get_neighborhood(key).nodes == []

    def test_hidden_nodes_never_appear_as_neighbours(self, repository):
        member = graph_model.member_key(MEMBER_ID)
        subgraph = repository.get_neighborhood(member, depth=2)
        assert subgraph.nodes
        for node in subgraph.nodes:
            assert node.kind not in self.HIDDEN_KINDS
            assert node.kind in EXPLORABLE_KINDS

    def test_the_member_neighborhood_still_explains_the_clinical_join(
        self, repository
    ):
        """The gate must not remove the thing the explorer exists to show."""
        subgraph = repository.get_neighborhood(
            graph_model.member_key(MEMBER_ID), depth=2
        )
        relationships = {edge.relationship for edge in subgraph.edges}
        assert graph_model.HAS_INJURY in relationships
        assert graph_model.HAS_EQUIPMENT in relationships


# --- HTTP surface ------------------------------------------------------------


class TestExplorerEndpoints:
    @pytest.fixture
    def client(self, monkeypatch):
        from fastapi.testclient import TestClient

        import app.mcp.server as mcp_server_module
        from app.main import create_app

        monkeypatch.setattr(mcp_server_module, "_asgi_app", None)
        with TestClient(create_app()) as client:
            yield client

    def test_search_node_and_neighborhood_are_served(self, client):
        search = client.get("/api/graph/search", params={"q": "knee"})
        assert search.status_code == 200
        assert search.json()["hits"][0]["kind"] == "AnatomicalRegion"

        node = client.get("/api/graph/nodes/anatomy:knee")
        assert node.status_code == 200
        assert node.json()["ontology_grounding"]["ontology_code"] == "72696002"

        neighborhood = client.get(
            "/api/graph/nodes/anatomy:knee/neighborhood", params={"depth": 1}
        )
        assert neighborhood.status_code == 200
        assert neighborhood.json()["nodes"]

    def test_unknown_nodes_are_404_not_a_stack_trace(self, client):
        assert client.get("/api/graph/nodes/nope").status_code == 404
        assert client.get("/api/graph/nodes/nope/neighborhood").status_code == 404

    def test_summary_counts_come_from_the_seeded_graph(self, client):
        summary = client.get("/api/graph/summary").json()
        assert summary["node_count"] > 0
        assert summary["nodes_by_kind"]["Exercise"] == 50
        assert summary["ontology_mappings"] == 29
        assert summary["graph_backend"] in {"memory", "neo4j"}

    def test_the_backend_identifier_is_reported_without_connection_detail(self, client):
        payload = client.get("/api/graph/summary").text.lower()
        assert "bolt" not in payload and "password" not in payload

    def test_legend_describes_the_relationships_present(self, client):
        legend = client.get("/api/graph/legend").json()
        relationships = {row["relationship"] for row in legend["relationships"]}
        assert graph_model.PART_OF in relationships
        assert all(row["description"] for row in legend["relationships"])

    def test_safety_mode_reuses_the_engine_verdict(self, client):
        jump = client.get(
            "/api/graph/search", params={"q": "Static Jump", "kinds": "Exercise"}
        ).json()["hits"][0]

        safety = client.get(f"/api/graph/safety/{jump['id']}").json()
        assert safety["decision"] == "excluded"
        assert "injury_contraindicated_pattern" in safety["rule_ids"]
        # Same traversal model the coach UI renders - no second provenance shape.
        assert safety["traversals"]
        assert {t["path_kind"] for t in safety["traversals"]} <= {
            "member_context", "anatomy_hierarchy", "exercise_structure", "set_operation",
        }

    def test_safety_mode_reports_longitudinal_influence_separately(self, client):
        walkout = client.get(
            "/api/graph/search",
            params={"q": "One-Kettlebell Hamstring Walkout", "kinds": "Exercise"},
        ).json()["hits"][0]

        safety = client.get(f"/api/graph/safety/{walkout['id']}").json()
        assert "longitudinal_adjustment" in safety
        assert safety["eligible"] is True


class TestNoArbitraryQuerySurface:
    """The explorer must not become a database console.

    These tests exist to fail loudly if a query endpoint is ever added.
    """

    @pytest.fixture
    def app(self, monkeypatch):
        import app.mcp.server as mcp_server_module
        from app.main import create_app

        monkeypatch.setattr(mcp_server_module, "_asgi_app", None)
        return create_app()

    def test_no_route_accepts_a_query_language(self, app):
        forbidden = ("cypher", "query", "sql", "gremlin", "bolt", "console", "admin")
        for route in app.routes:
            path = getattr(route, "path", "").lower()
            assert not any(word in path for word in forbidden), path

    def test_no_graph_route_permits_a_write_method(self, app):
        for route in app.routes:
            path = getattr(route, "path", "")
            if not path.startswith("/api/graph"):
                continue
            methods = getattr(route, "methods", set()) or set()
            assert methods <= {"GET", "HEAD", "OPTIONS"}, path

    def test_explorer_repository_methods_are_read_only(self, repository):
        for name in ("search_nodes", "get_node", "get_neighborhood"):
            assert hasattr(repository, name)
        for forbidden in ("create_node", "delete_node", "run_cypher", "execute"):
            assert not hasattr(repository, forbidden)

    def test_no_write_verb_appears_in_the_explorer_cypher(self):
        from app.graph import queries

        explorer_statements = [
            value
            for name, value in vars(queries).items()
            if name.startswith("EXPLORER_") and isinstance(value, str)
        ]
        assert explorer_statements
        for statement in explorer_statements:
            upper = statement.upper()
            for verb in ("CREATE", "MERGE", "SET ", "DELETE", "REMOVE", "DROP", "CALL "):
                assert verb not in upper, statement


# --- Memory / Neo4j parity ---------------------------------------------------


def _neo4j_repository():
    """Connect to a local Neo4j, or return None so the test skips.

    The suite must stay runnable with no Docker, so an unreachable database is
    a skip rather than a failure - but when one *is* running, these are the
    tests that prove the explorer is not quietly memory-only.
    """
    try:
        from app.core.config import get_settings
        from app.graph.neo4j_repository import Neo4jGraphRepository

        settings = get_settings()
        return Neo4jGraphRepository.connect(
            settings.neo4j_uri,
            settings.neo4j_user,
            settings.neo4j_password,
            settings.neo4j_database,
            settings.exercises_path,
            settings.member_context_path,
            get_ontology(),
        )
    except Exception:  # noqa: BLE001 - absence of a database is not a failure
        return None


@pytest.fixture(scope="module")
def neo4j_repository():
    repository = _neo4j_repository()
    if repository is None:
        pytest.skip("Neo4j is not reachable; parity tests skipped")
    try:
        yield repository
    finally:
        close = getattr(repository, "close", None)
        if callable(close):
            close()


class TestBackendParity:
    """The explorer must describe the same graph on either backend.

    Neo4j serves the *topology* from real Cypher while the projection supplies
    the typed view, so a drift between what was seeded and what the application
    reasons on would surface here rather than hide.
    """

    @pytest.mark.parametrize("query", ["knee", "Static Jump", "dumbbell", "plyometric"])
    def test_search_returns_the_same_nodes(self, repository, neo4j_repository, query):
        memory = {hit.id for hit in repository.search_nodes(query, limit=20).hits}
        neo4j = {hit.id for hit in neo4j_repository.search_nodes(query, limit=20).hits}
        assert memory == neo4j

    def test_node_detail_matches(self, repository, neo4j_repository):
        for node_id in ("anatomy:knee", "InjuryCondition:patellofemoral_pain_syndrome"):
            assert repository.get_node(node_id) == neo4j_repository.get_node(node_id)

    @pytest.mark.parametrize("depth", [1, 2])
    def test_anatomy_neighborhood_matches(self, repository, neo4j_repository, depth):
        memory = repository.get_neighborhood(KNEE, depth=depth)
        neo4j = neo4j_repository.get_neighborhood(KNEE, depth=depth)

        assert {n.id for n in memory.nodes} == {n.id for n in neo4j.nodes}
        assert {(e.source, e.relationship, e.target) for e in memory.edges} == {
            (e.source, e.relationship, e.target) for e in neo4j.edges
        }

    def test_exercise_neighborhood_matches(self, repository, neo4j_repository):
        jump = _exercise_id(repository, "Static Jump")
        memory = repository.get_neighborhood(jump, depth=1)
        neo4j = neo4j_repository.get_neighborhood(jump, depth=1)

        assert {n.id for n in memory.nodes} == {n.id for n in neo4j.nodes}
        assert {e.relationship for e in memory.edges} == {
            e.relationship for e in neo4j.edges
        }

    def test_ontology_mapping_neighborhood_matches(self, repository, neo4j_repository):
        memory = repository.get_neighborhood(KNEE, depth=1)
        neo4j = neo4j_repository.get_neighborhood(KNEE, depth=1)

        def skos(subgraph):
            return {
                (e.source, e.relationship, e.target)
                for e in subgraph.edges
                if e.relationship.startswith("SKOS_")
            }

        assert skos(memory) == skos(neo4j)
        assert skos(memory)

    def test_the_privacy_gate_holds_on_neo4j_too(self, neo4j_repository):
        for term in ("lab", "sleep", "brief", "churn"):
            for hit in neo4j_repository.search_nodes(term, limit=50).hits:
                assert hit.kind in EXPLORABLE_KINDS

    def test_neo4j_reports_its_own_backend_name(self, neo4j_repository):
        assert neo4j_repository.backend_name == "neo4j"
