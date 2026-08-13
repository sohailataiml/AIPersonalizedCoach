"""Ontology-grounding tests.

The property these exist to protect:

    Grounding a local concept in a published ontology must add *interchange
    identity* and change *nothing else*. The local id stays authoritative, the
    safety engine behaves identically, and no external identifier is ever
    asserted without evidence.

The strongest tests here are the negative ones. It is easy to add SNOMED codes;
the failure mode that actually hurts is a code that looks authoritative in a
provenance trace while being wrong - which is exactly what happened in the
revision this work replaced, where five of eleven "verified" codes did not
survive contact with the terminology server.
"""

from __future__ import annotations

import re

import pytest

from app.agents.intent import parse_intent
from app.domain.ontology import ConceptGrounding
from app.graph import model as graph_model
from app.graph.memory_repository import InMemoryGraphRepository
from app.ontology.grounding import build_grounding_report, to_concept_grounding
from app.ontology.loader import ONTOLOGY_PATH, load_ontology
from app.provenance.graph_trace import build_graph_reasoning
from app.safety.ranking import rank_candidates

from .conftest import DATA

# Codes that a previous revision asserted and that do not survive verification.
# Three do not exist in SNOMED CT at all; two resolve to a protozoan and a
# plant. Pinned here so they can never be reintroduced by a copy-paste.
RETRACTED_CODES = {
    "202383002": "claimed Patellofemoral pain syndrome - no such SNOMED concept",
    "30989003": "claimed Arthralgia of knee - no such SNOMED concept",
    "122470009": "claimed Quadriceps femoris muscle - no such SNOMED concept",
    "68861009": "claimed Gluteal muscle structure - resolves to Hexamita, a protozoan",
    "81022004": "claimed Hamstring muscle structure - resolves to Vicia angustifolia, a plant",
}

VALID_RELATIONS = {"exactMatch", "closeMatch", "broadMatch"}


# --- the mapping set itself --------------------------------------------------


class TestMappingSet:
    def test_a_real_ontology_subset_exists(self, ontology):
        grounded = [g for g in ontology.groundings() if g.is_grounded]
        assert len(grounded) >= 20
        assert {g.source for g in grounded} == {"SNOMED_CT"}

    def test_every_grounding_carries_auditable_evidence(self, ontology):
        """A mapping without evidence is an assertion nobody can re-check."""
        for grounding in ontology.groundings():
            if not grounding.is_grounded:
                continue
            assert grounding.evidence, f"{grounding.local_id} has no evidence"
            assert grounding.version, f"{grounding.local_id} has no mapping version"
            assert grounding.term, f"{grounding.local_id} records no external term"

    def test_every_grounding_uses_a_known_skos_relation(self, ontology):
        for grounding in ontology.groundings():
            if grounding.is_grounded:
                assert grounding.relation in VALID_RELATIONS

    def test_declared_sources_resolve_to_dereferenceable_uris(self, ontology):
        for grounding in ontology.groundings():
            if not grounding.is_grounded:
                continue
            assert grounding.source in ontology.sources
            assert grounding.uri and grounding.uri.startswith("http")
            assert grounding.code in (grounding.uri or "")

    def test_retracted_codes_are_never_reintroduced(self, ontology):
        """The five fabricated identifiers must stay gone."""
        live = {g.code for g in ontology.groundings() if g.code}
        for code, why in RETRACTED_CODES.items():
            assert code not in live, f"{code} was reintroduced ({why})"

    def test_no_code_is_invented_for_an_unverifiable_source(self, ontology):
        """OPE and COPPER could not be resolved, so they must carry no codes.

        BioPortal's REST API needs an account key (HTTP 401) and OLS4 does not
        host OPE (HTTP 404). Recording an OPE identifier from this build would
        therefore be fabrication, however plausible the id looked.
        """
        for grounding in ontology.groundings():
            assert grounding.source not in {"OPE", "COPPER"}
            if not grounding.is_grounded:
                assert grounding.code is None

    def test_snomed_codes_are_numeric_identifiers(self, ontology):
        for grounding in ontology.groundings():
            if grounding.source == "SNOMED_CT":
                assert re.fullmatch(r"\d{6,18}", grounding.code or "")


# --- unmapped concepts degrade gracefully ------------------------------------


class TestUnmappedConcepts:
    def test_unmapped_concepts_are_registered_with_a_reason(self, ontology):
        unmapped = [g for g in ontology.groundings() if not g.is_grounded]
        assert unmapped, "the unmapped register should not be empty"
        for grounding in unmapped:
            assert grounding.evidence, f"{grounding.local_id} gives no reason"
            assert grounding.status == "unmapped"

    def test_ope_and_copper_omissions_are_documented(self, ontology):
        registered = {g.local_id for g in ontology.unmapped}
        assert {"equipment", "movement_patterns", "personalization"} <= registered

    def test_an_ungrounded_concept_still_resolves_and_is_usable(self, ontology, resolver):
        """Equipment carries no external identifier and must work regardless."""
        assert ontology.grounding_for("equipment:dumbbell") is None

        resolved = resolver.resolve("dumbbells")
        assert resolved.is_resolved
        assert resolved.canonical_id == "equipment:dumbbell"

    def test_grounding_lookup_tolerates_unknown_ids(self, ontology):
        for local_id in ["", "nonsense", "anatomy:not_a_region", "muscle:", "focus:core"]:
            assert ontology.grounding_for(local_id) is None

    def test_a_muscle_group_with_no_clean_counterpart_stays_unmapped(self, ontology):
        """"Core" spans several muscles SNOMED models individually."""
        assert ontology.grounding_for("muscle:core") is None
        assert "muscles:core" in {g.local_id for g in ontology.unmapped}


# --- the local vocabulary stays authoritative --------------------------------


class TestLocalIdsRemainAuthoritative:
    def test_mapped_concept_retains_its_local_id(self, ontology):
        knee = ontology.anatomy["knee"]
        assert knee.id == "knee"
        assert knee.grounding is not None
        assert knee.grounding.local_id == "anatomy:knee"
        assert knee.grounding.code == "72696002"

    def test_resolver_still_returns_local_ids_not_ontology_codes(self, resolver):
        resolved = resolver.resolve("left knee")
        assert resolved.canonical_id == "anatomy:knee"

    def test_condition_keeps_its_local_id_after_correction(self, ontology):
        condition = ontology.injury_conditions["patellofemoral_pain_syndrome"]
        assert condition.affects == "patellofemoral_joint"
        assert condition.grounding is not None
        assert condition.grounding.code == "430725003"

    def test_ontology_codes_are_absent_from_the_safety_vocabulary(self, ontology):
        """No safety rule may key on an external identifier.

        Contraindication targets are catalog movement patterns and anatomy is a
        local id. If a SNOMED code ever appeared here, clinical identity would
        have leaked into the safety mechanism.
        """
        for condition in ontology.injury_conditions.values():
            for pattern in condition.contraindicates_patterns:
                assert not re.fullmatch(r"\d+", pattern)
            assert condition.affects in ontology.anatomy


# --- safety and traversal are unchanged --------------------------------------


class TestSafetySemanticsUnchanged:
    """Baseline numbers captured before grounding was extended.

    If a mapping change ever moves one of these, grounding has stopped being
    metadata and started being logic.
    """

    @pytest.mark.parametrize(
        ("prompt", "eligible", "excluded", "downranked"),
        [
            ("Create a 45-minute lower-body workout. Her left knee is bothering her.", 18, 32, 8),
            (
                "Build a full-body workout. She has no barbell, only dumbbells and a kettlebell.",
                16,
                34,
                7,
            ),
            ("Create a lower-body workout but exclude deadlifts.", 17, 33, 7),
        ],
    )
    def test_filtering_counts_are_identical_to_the_pre_grounding_baseline(
        self, evaluate, repository, member, resolver, ontology, prompt, eligible, excluded, downranked
    ):
        decisions, context = evaluate(prompt)
        intent, resolved = parse_intent(prompt, 45, resolver)
        candidates = rank_candidates(
            repository.list_exercises(), decisions, member, intent, resolved, ontology
        )

        assert len(candidates) == eligible
        assert sum(1 for d in decisions.values() if d.status == "excluded") == excluded
        assert sum(1 for d in decisions.values() if d.status == "downranked") == downranked

    def test_anatomy_closure_is_unchanged_by_grounding(self, ontology):
        closure = ontology.anatomical_closure("patellofemoral_joint")
        assert closure == {"patellofemoral_joint", "knee", "lower_limb"}

    def test_part_of_path_still_reaches_the_parent_joint(self, ontology):
        assert ontology.part_of_path("patellofemoral_joint", "knee") == [
            "patellofemoral_joint",
            "knee",
        ]

    def test_catalog_joints_still_map_onto_local_anatomy(self, ontology):
        for joint in [
            "knee",
            "hip",
            "ankle",
            "shoulder",
            "elbow",
            "wrist",
            "lumbar spine",
            "thoracic spine",
            "cervical spine",
        ]:
            assert ontology.anatomy_by_catalog_joint(joint) is not None

    def test_no_safety_rule_reads_ontology_metadata(self, evaluate):
        """Stripping every mapping must not change a single decision."""
        stripped = load_ontology(ONTOLOGY_PATH)
        for concept in stripped.anatomy.values():
            object.__setattr__(concept, "grounding", None)
        for condition in stripped.injury_conditions.values():
            object.__setattr__(condition, "grounding", None)

        repository = InMemoryGraphRepository.from_files(
            DATA / "exercises.json", DATA / "member-context.json", ontology=stripped
        )
        from app.resolution.resolver import ConceptResolver
        from app.safety.engine import SafetyEngine

        resolver = ConceptResolver.from_ontology(stripped)
        engine = SafetyEngine(repository, stripped)
        member = repository.get_member_context("mbr_01HX9JORDAN")
        assert member is not None

        prompt = "Create a 45-minute lower-body workout. Her left knee is bothering her."
        intent, resolved = parse_intent(prompt, 45, resolver)
        context = engine.build_context(member, intent, resolved)
        ungrounded = {d.exercise_id: d.status for d in engine.evaluate_all(context)}

        grounded, _ = evaluate(prompt)
        assert ungrounded == {eid: d.status for eid, d in grounded.items()}


# --- the graph carries the mapping, without a second store -------------------


class TestGraphStorage:
    def test_skos_edges_use_declared_relationship_types(self, repository):
        stats = repository.stats()
        assert stats.get("edge:SKOS_EXACT_MATCH", 0) > 0
        assert stats.get("edge:SKOS_CLOSE_MATCH", 0) > 0
        assert stats.get("node:OntologyConcept", 0) > 0

    def test_every_skos_relationship_is_a_declared_constant(self, repository):
        declared = {
            value
            for name, value in vars(graph_model).items()
            if name.startswith("SKOS_") and isinstance(value, str)
        }
        used = {e.type for e in repository.graph().edges if e.type.startswith("SKOS_")}
        assert used <= declared

    def test_ontology_nodes_carry_uri_and_evidence(self, repository):
        nodes = repository.graph().nodes_with_label(graph_model.ONTOLOGY_CONCEPT)
        assert nodes
        for node in nodes:
            assert node.properties.get("uri", "").startswith("http")
            assert node.properties.get("code")
            assert node.properties.get("evidence")

    def test_ontology_concept_count_matches_the_mapping_set(self, repository, ontology):
        """The graph asserts exactly as many external identities as we verified."""
        grounded_codes = {
            f"{g.source}:{g.code}" for g in ontology.groundings() if g.is_grounded
        }
        nodes = repository.graph().nodes_with_label(graph_model.ONTOLOGY_CONCEPT)
        assert {str(n.properties["id"]) for n in nodes} == grounded_codes

    def test_no_ontology_node_exists_for_an_unmapped_concept(self, repository, ontology):
        nodes = repository.graph().nodes_with_label(graph_model.ONTOLOGY_CONCEPT)
        labels = {str(n.properties.get("name", "")).lower() for n in nodes}
        for grounding in ontology.unmapped:
            assert grounding.label.lower() not in labels

    def test_domain_nodes_carry_grounding_without_a_second_store(self, repository):
        knee = repository.graph().nodes[graph_model.anatomy_key("knee")]
        assert knee.properties["ontology_code"] == "72696002"
        assert knee.properties["mapping_predicate"] == "skos:exactMatch"
        assert knee.label == graph_model.ANATOMICAL_REGION


# --- serialization -----------------------------------------------------------


class TestSerialization:
    def test_grounding_serializes_with_every_documented_field(self, ontology):
        projected = to_concept_grounding(ontology.grounding_for("anatomy:knee"))
        assert projected is not None
        payload = projected.model_dump()

        assert payload["local_id"] == "anatomy:knee"
        assert payload["ontology_source"] == "SNOMED_CT"
        assert payload["ontology_code"] == "72696002"
        assert payload["ontology_uri"] == "http://snomed.info/id/72696002"
        assert payload["mapping_relation"] == "exactMatch"
        assert payload["mapping_evidence"]
        assert payload["mapping_version"] == "2025_09_01"
        assert payload["status"] == "verified"

    def test_unmapped_grounding_serializes_without_a_partial_mapping(self, ontology):
        unmapped = next(g for g in ontology.unmapped if g.local_id == "equipment")
        projected = to_concept_grounding(unmapped)
        assert projected is not None
        assert projected.is_grounded is False
        assert projected.ontology_code is None
        assert projected.mapping_relation is None
        assert projected.mapping_evidence  # the reason survives

    def test_report_separates_mapped_from_unmapped(self, ontology):
        report = build_grounding_report(ontology)
        assert report.counts["mapped"] == len(report.mapped)
        assert report.counts["unmapped"] == len(report.unmapped)
        assert all(row.is_grounded for row in report.mapped)
        assert not any(row.is_grounded for row in report.unmapped)
        assert report.mapping_set_version

    def test_relation_is_a_closed_set_in_the_contract(self):
        with pytest.raises(ValueError):
            ConceptGrounding(
                local_id="anatomy:knee",
                label="Knee",
                ontology_source="SNOMED_CT",
                ontology_code="72696002",
                mapping_relation="skos:sameAs",  # type: ignore[arg-type]
            )


# --- provenance can expose grounding -----------------------------------------


class TestProvenanceExposure:
    def _reasoning(self, repository, engine, resolver, member, ontology, with_ontology):
        prompt = (
            "Create a 45-minute lower-body workout. Her left knee is bothering her "
            "and she only has dumbbells and a kettlebell."
        )
        intent, resolved = parse_intent(prompt, 45, resolver)
        context = engine.build_context(member, intent, resolved)
        decisions = {d.exercise_id: d for d in engine.evaluate_all(context)}
        candidates = rank_candidates(
            repository.list_exercises(), decisions, member, intent, resolved, ontology
        )
        return build_graph_reasoning(
            trace_id="test",
            graph_backend="memory",
            decisions=decisions,
            candidates=candidates,
            resolved_concepts=resolved,
            member_facts=[],
            in_plan_count=0,
            ontology=ontology if with_ontology else None,
        )

    def test_provenance_exposes_ontology_source_when_present(
        self, repository, engine, resolver, member, ontology
    ):
        reasoning = self._reasoning(repository, engine, resolver, member, ontology, True)
        knee = next(c for c in reasoning.prompt_concepts if c.canonical_id == "anatomy:knee")

        assert knee.grounding is not None
        assert knee.grounding.ontology_source == "SNOMED_CT"
        assert knee.grounding.mapping_relation == "exactMatch"
        assert knee.grounding.ontology_uri

    def test_concepts_without_grounding_expose_none_not_a_placeholder(
        self, repository, engine, resolver, member, ontology
    ):
        reasoning = self._reasoning(repository, engine, resolver, member, ontology, True)
        equipment = [
            c for c in reasoning.prompt_concepts if (c.canonical_id or "").startswith("equipment:")
        ]
        assert equipment
        assert all(c.grounding is None for c in equipment)

    def test_grounding_is_optional_and_omitting_it_changes_nothing_else(
        self, repository, engine, resolver, member, ontology
    ):
        with_ont = self._reasoning(repository, engine, resolver, member, ontology, True)
        without = self._reasoning(repository, engine, resolver, member, ontology, False)

        assert all(c.grounding is None for c in without.prompt_concepts)
        assert with_ont.summary.model_dump() == without.summary.model_dump()
        assert [t.model_dump() for t in with_ont.traversals] == [
            t.model_dump() for t in without.traversals
        ]

    def test_unresolved_phrases_are_never_given_a_grounding(
        self, repository, engine, resolver, member, ontology
    ):
        prompt = "Create a workout but she has a weird knee-ish thing going on."
        intent, resolved = parse_intent(prompt, 45, resolver)
        context = engine.build_context(member, intent, resolved)
        decisions = {d.exercise_id: d for d in engine.evaluate_all(context)}
        reasoning = build_graph_reasoning(
            trace_id="test",
            graph_backend="memory",
            decisions=decisions,
            candidates=[],
            resolved_concepts=resolved,
            member_facts=[],
            in_plan_count=0,
            ontology=ontology,
        )
        for concept in reasoning.prompt_concepts:
            if not concept.resolved:
                assert concept.grounding is None
