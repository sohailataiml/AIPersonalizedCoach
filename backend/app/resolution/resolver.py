"""The 3-pass concept resolver.

    normalize -> exact/alias -> fuzzy -> embedding -> threshold -> unresolved

Every result carries source text, canonical id, type, method and confidence, so
the UI can show *how* a phrase was understood and a reviewer can audit it.

The hard rule is at the bottom of `resolve`: below threshold we return an
``unresolved`` record rather than the best-guess concept. Forcing a low
confidence match on clinical language is how a system silently applies the wrong
safety rule, which is worse than admitting it does not know.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process

from app.domain.resolution import CanonicalConcept, ConceptType, ResolvedConcept
from app.ontology.loader import Ontology, get_ontology
from app.resolution.embeddings import EmbeddingIndex
from app.resolution.normalizer import normalization_variants, normalize

DEFAULT_FUZZY_THRESHOLD = 0.88
DEFAULT_EMBEDDING_THRESHOLD = 0.82

# A fuzzy match this much better than the runner-up is treated as unambiguous.
AMBIGUITY_MARGIN = 0.05


@dataclass
class _IndexedAlias:
    text: str
    concept_id: str


# Below this token count a phrase is treated as already specific, so no
# coverage penalty applies ("no barbell" should still resolve to Barbell).
SPECIFICITY_MIN_TOKENS = 3
SPECIFICITY_MIN_COVERAGE = 0.5


def _specificity_factor(query: str, alias: str) -> float:
    """Penalize a long vague phrase that matched on one incidental token.

    RapidFuzz's WRatio awards high partial-match scores, so "weird knee-ish
    thing" scores ~0.90 against the alias "knee". Adopting that as a *clinical*
    resolution is precisely the false-canonicalization failure mode we care
    about: it would silently apply a knee safety rule the coach never asked for.

    We therefore scale confidence by how much of the query the matched alias
    actually accounts for. Short phrases are exempt so ordinary coach shorthand
    ("no barbell", "only DBs") is unaffected.
    """
    query_tokens = [t for t in query.split() if t]
    if len(query_tokens) < SPECIFICITY_MIN_TOKENS:
        return 1.0

    alias_tokens = set(alias.split())
    covered = sum(1 for token in query_tokens if token in alias_tokens)
    coverage = covered / len(query_tokens)
    if coverage >= SPECIFICITY_MIN_COVERAGE:
        return 1.0
    return 0.5 + coverage


class ConceptResolver:
    def __init__(
        self,
        concepts: list[CanonicalConcept],
        fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD,
        embedding_threshold: float = DEFAULT_EMBEDDING_THRESHOLD,
        embedding_index: EmbeddingIndex | None = None,
    ) -> None:
        self._concepts = {c.id: c for c in concepts}
        self._fuzzy_threshold = fuzzy_threshold
        self._embedding_threshold = embedding_threshold

        # Exact/alias index: normalized surface form -> concept id.
        self._alias_index: dict[str, str] = {}
        self._aliases: list[_IndexedAlias] = []
        for concept in concepts:
            for surface in [concept.label, *concept.aliases]:
                normalized = normalize(surface)
                if not normalized:
                    continue
                self._alias_index.setdefault(normalized, concept.id)
                self._aliases.append(_IndexedAlias(text=normalized, concept_id=concept.id))

        self._embedding_index = embedding_index or self._build_embedding_index(concepts)

    @staticmethod
    def _build_embedding_index(concepts: list[CanonicalConcept]) -> EmbeddingIndex:
        index = EmbeddingIndex()
        for concept in concepts:
            for surface in [concept.label, *concept.aliases]:
                normalized = normalize(surface)
                if normalized:
                    index.add(concept.id, normalized)
        return index

    @classmethod
    def from_ontology(
        cls,
        ontology: Ontology | None = None,
        fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD,
        embedding_threshold: float = DEFAULT_EMBEDDING_THRESHOLD,
    ) -> ConceptResolver:
        ontology = ontology or get_ontology()
        return cls(
            ontology.canonical_concepts(),
            fuzzy_threshold=fuzzy_threshold,
            embedding_threshold=embedding_threshold,
        )

    # --- public API -------------------------------------------------------

    def resolve(
        self, text: str, expected_type: ConceptType | None = None
    ) -> ResolvedConcept:
        """Resolve one phrase. ``expected_type`` narrows the search space."""
        if not text or not text.strip():
            return ResolvedConcept(source_text=text or "", method="unresolved", confidence=0.0)

        allowed = self._allowed_ids(expected_type)

        exact = self._pass_exact(text, allowed)
        if exact is not None:
            return exact

        fuzzy = self._pass_fuzzy(text, allowed)
        if fuzzy is not None and fuzzy.confidence >= self._fuzzy_threshold:
            return fuzzy

        embedding = self._pass_embedding(text, allowed)
        if embedding is not None and embedding.confidence >= self._embedding_threshold:
            return embedding

        # Nothing cleared threshold. Report the best near-miss for transparency
        # but do NOT adopt it as the resolution.
        best = max(
            [c for c in (fuzzy, embedding) if c is not None],
            key=lambda c: c.confidence,
            default=None,
        )
        return ResolvedConcept(
            source_text=text,
            canonical_id=None,
            label=None,
            concept_type=None,
            method="unresolved",
            confidence=round(best.confidence, 4) if best else 0.0,
            alternatives=best.alternatives if best else [],
        )

    def resolve_many(
        self, texts: list[str], expected_type: ConceptType | None = None
    ) -> list[ResolvedConcept]:
        seen: set[str] = set()
        results: list[ResolvedConcept] = []
        for text in texts:
            key = normalize(text)
            if not key or key in seen:
                continue
            seen.add(key)
            results.append(self.resolve(text, expected_type))
        return results

    def get_concept(self, concept_id: str) -> CanonicalConcept | None:
        return self._concepts.get(concept_id)

    # --- passes -----------------------------------------------------------

    def _allowed_ids(self, expected_type: ConceptType | None) -> set[str] | None:
        if expected_type is None:
            return None
        return {cid for cid, c in self._concepts.items() if c.concept_type == expected_type}

    def _pass_exact(self, text: str, allowed: set[str] | None) -> ResolvedConcept | None:
        """Exact hit on a canonical label or curated alias.

        Confidence 1.0 for a label hit, 0.98 for an alias hit - an alias is a
        curated equivalence, which is marginally weaker evidence than the
        canonical name itself.
        """
        for variant in normalization_variants(text):
            concept_id = self._alias_index.get(variant)
            if concept_id is None or (allowed is not None and concept_id not in allowed):
                continue
            concept = self._concepts[concept_id]
            is_label = normalize(concept.label) == variant
            return self._build(
                text,
                concept,
                method="exact" if is_label else "alias",
                confidence=1.0 if is_label else 0.98,
            )
        return None

    def _pass_fuzzy(self, text: str, allowed: set[str] | None) -> ResolvedConcept | None:
        """RapidFuzz over the alias surface forms.

        Uses WRatio, which handles typos and partial phrases well. We also
        record the runner-up so ambiguity is visible rather than hidden.
        """
        candidates = [a for a in self._aliases if allowed is None or a.concept_id in allowed]
        if not candidates:
            return None

        query = normalize(text)
        matches = process.extract(
            query,
            [a.text for a in candidates],
            scorer=fuzz.WRatio,
            limit=5,
        )
        if not matches:
            return None

        best_text, best_score, best_index = matches[0]
        concept = self._concepts[candidates[best_index].concept_id]
        confidence = (best_score / 100.0) * _specificity_factor(query, best_text)

        alternatives = [
            self._concepts[candidates[idx].concept_id].label
            for _, _, idx in matches[1:4]
            if candidates[idx].concept_id != concept.id
        ]

        resolved = self._build(text, concept, method="fuzzy", confidence=confidence)
        resolved.alternatives = list(dict.fromkeys(alternatives))
        return resolved

    def _pass_embedding(self, text: str, allowed: set[str] | None) -> ResolvedConcept | None:
        results = self._embedding_index.search(normalize(text), top_k=5)
        results = [r for r in results if allowed is None or r[0] in allowed]
        if not results:
            return None

        concept_id, _, score = results[0]
        concept = self._concepts[concept_id]
        resolved = self._build(text, concept, method="embedding", confidence=score)
        resolved.alternatives = list(
            dict.fromkeys(
                self._concepts[cid].label for cid, _, _ in results[1:4] if cid != concept_id
            )
        )
        return resolved

    def _build(
        self, text: str, concept: CanonicalConcept, method: str, confidence: float
    ) -> ResolvedConcept:
        return ResolvedConcept(
            source_text=text,
            canonical_id=concept.id,
            label=concept.label,
            concept_type=concept.concept_type,
            method=method,  # type: ignore[arg-type]
            confidence=round(min(1.0, max(0.0, confidence)), 4),
        )
