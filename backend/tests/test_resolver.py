"""Concept resolver tests.

Chosen because resolution is the system's front door: if "left knee" or "DBs"
is mis-canonicalized, every downstream graph decision is confidently wrong. The
most important tests here are the *negative* ones - the resolver must refuse to
guess rather than force a match on clinical language.
"""

from __future__ import annotations

import pytest

from app.resolution.embeddings import CharNgramEmbedder, EmbeddingIndex, cosine_similarity
from app.resolution.normalizer import extract_laterality, normalize
from app.resolution.resolver import ConceptResolver


class TestNormalization:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("DB", "dumbbell"),
            ("DBs", "dumbbell"),
            ("KB", "kettlebell"),
            ("  Left   Knee!! ", "left knee"),
            ("RDL", "romanian deadlift"),
        ],
    )
    def test_normalizes_and_expands_abbreviations(self, raw, expected):
        assert normalize(raw) == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("her left knee", "left"), ("right shoulder", "right"), ("both knees", "bilateral")],
    )
    def test_extracts_laterality(self, raw, expected):
        assert extract_laterality(raw) == expected

    def test_laterality_absent_returns_none(self):
        assert extract_laterality("knee pain") is None


class TestExactAndAlias:
    def test_exact_label_match_scores_one(self, resolver: ConceptResolver):
        result = resolver.resolve("knee")
        assert result.canonical_id == "anatomy:knee"
        assert result.method == "exact"
        assert result.confidence == 1.0

    def test_alias_match_is_slightly_below_exact(self, resolver: ConceptResolver):
        result = resolver.resolve("left knee")
        assert result.canonical_id == "anatomy:knee"
        assert result.method == "alias"
        assert 0.9 <= result.confidence < 1.0

    @pytest.mark.parametrize("phrase", ["DB", "DBs", "dumbbell", "dumbbells"])
    def test_equipment_abbreviations_resolve_to_dumbbell(
        self, resolver: ConceptResolver, phrase
    ):
        result = resolver.resolve(phrase)
        assert result.canonical_id == "equipment:dumbbell"
        assert result.is_resolved

    @pytest.mark.parametrize("phrase", ["KB", "kettlebell", "kettlebells"])
    def test_kettlebell_variants_resolve(self, resolver: ConceptResolver, phrase):
        assert resolver.resolve(phrase).canonical_id == "equipment:kettlebell"

    @pytest.mark.parametrize(
        "phrase", ["lower back", "low back", "bad lower back", "lumbar", "lumbar region"]
    )
    def test_lower_back_phrases_resolve_to_lumbar_spine(
        self, resolver: ConceptResolver, phrase
    ):
        result = resolver.resolve(phrase)
        assert result.canonical_id == "anatomy:lumbar_spine"
        assert result.is_resolved

    def test_deadlift_resolves_to_hinge_family(self, resolver: ConceptResolver):
        """The catalog has no exercise named "deadlift" - it must resolve to a family."""
        result = resolver.resolve("deadlifts")
        assert result.canonical_id == "movement_family:hinge"
        assert result.concept_type == "movement_pattern"


class TestFuzzy:
    @pytest.mark.parametrize(
        ("typo", "expected"),
        [
            ("kettlebel", "equipment:kettlebell"),
            ("dumbell", "equipment:dumbbell"),
            ("kneee", "anatomy:knee"),
            ("kettlbell", "equipment:kettlebell"),
        ],
    )
    def test_typos_resolve_via_fuzzy(self, resolver: ConceptResolver, typo, expected):
        result = resolver.resolve(typo)
        assert result.canonical_id == expected
        assert result.method in {"fuzzy", "alias", "embedding"}
        assert result.confidence >= 0.82

    def test_fuzzy_reports_alternatives_for_auditability(self, resolver: ConceptResolver):
        result = resolver.resolve("no barbell")
        assert result.canonical_id == "equipment:barbell"
        assert isinstance(result.alternatives, list)


class TestEmbeddingFallback:
    def test_index_ranks_related_text_higher(self):
        index = EmbeddingIndex()
        index.add("anatomy:lumbar_spine", "lumbar spine")
        index.add("equipment:kettlebell", "kettlebell")

        results = index.search("lumbar spine region")
        assert results[0][0] == "anatomy:lumbar_spine"
        assert results[0][2] > 0.4

    def test_cosine_similarity_is_bounded_and_symmetric(self):
        embedder = CharNgramEmbedder()
        a, b = embedder.embed("kettlebell"), embedder.embed("kettlebell")
        assert cosine_similarity(a, b) == pytest.approx(1.0, abs=1e-6)
        assert cosine_similarity(a, {}) == 0.0

    def test_embedding_pass_can_rescue_a_missed_phrase(self, ontology):
        """Force exact+fuzzy to fail so only the embedding pass can answer."""
        resolver = ConceptResolver.from_ontology(
            ontology, fuzzy_threshold=1.01, embedding_threshold=0.30
        )
        # Not a curated alias, so exact/alias cannot hit it.
        result = resolver.resolve("lumbar spine region")
        assert result.canonical_id == "anatomy:lumbar_spine"
        assert result.method == "embedding"


class TestGracefulDegradation:
    """The resolver must never invent a clinical mapping."""

    @pytest.mark.parametrize(
        "phrase",
        [
            "weird knee-ish thing",
            "quantum flux capacitor",
            "some weird thing going on",
            "",
            "   ",
        ],
    )
    def test_low_confidence_input_is_unresolved(self, resolver: ConceptResolver, phrase):
        result = resolver.resolve(phrase)
        assert result.canonical_id is None
        assert result.method == "unresolved"
        assert not result.is_resolved

    def test_unresolved_still_reports_the_near_miss(self, resolver: ConceptResolver):
        """We surface what was considered without adopting it."""
        result = resolver.resolve("weird knee-ish thing")
        assert result.method == "unresolved"
        assert result.confidence < 0.88
        assert result.source_text == "weird knee-ish thing"

    def test_expected_type_narrows_the_search(self, resolver: ConceptResolver):
        result = resolver.resolve("knee", expected_type="equipment")
        assert result.canonical_id != "anatomy:knee"

    def test_near_threshold_typo_is_rejected_not_rounded_up(
        self, resolver: ConceptResolver
    ):
        """A 0.875 match sits just under the 0.88 gate and must not squeak through.

        This is the boundary that matters: anatomy mapped on a near-miss would
        apply a safety rule the coach never asked for.
        """
        result = resolver.resolve("shouldar")
        assert result.method == "unresolved"
        assert 0.8 < result.confidence < 0.88

    def test_thresholds_are_enforced_not_advisory(self, ontology):
        strict = ConceptResolver.from_ontology(
            ontology, fuzzy_threshold=0.99, embedding_threshold=0.99
        )
        result = strict.resolve("kettlebel")  # typo, ~0.95 fuzzy
        assert result.method == "unresolved"


class TestResolveMany:
    def test_deduplicates_equivalent_surface_forms(self, resolver: ConceptResolver):
        results = resolver.resolve_many(["DB", "DBs", "dumbbell"])
        assert len(results) == 1

    def test_preserves_source_text_for_the_ui(self, resolver: ConceptResolver):
        results = resolver.resolve_many(["left knee", "kettlebell"])
        assert [r.source_text for r in results] == ["left knee", "kettlebell"]
