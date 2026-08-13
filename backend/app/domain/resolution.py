"""Concept-resolution contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ResolutionMethod = Literal["exact", "alias", "fuzzy", "embedding", "unresolved"]
ConceptType = Literal[
    "anatomy",
    "equipment",
    "movement_pattern",
    "muscle",
    "injury_condition",
    "exercise",
]


class CanonicalConcept(BaseModel):
    """A node in the canonical vocabulary the graph is keyed on."""

    id: str
    label: str
    concept_type: ConceptType
    aliases: list[str] = Field(default_factory=list)
    # Ontology grounding is optional and present only where we could justify it.
    ontology_source: str | None = None
    ontology_code: str | None = None
    ontology_uri: str | None = None
    mapping_predicate: (
        Literal["skos:exactMatch", "skos:closeMatch", "skos:broadMatch"] | None
    ) = None
    note: str | None = None


class ResolvedConcept(BaseModel):
    """The audit record of one free-text phrase to canonical concept attempt."""

    source_text: str
    canonical_id: str | None = None
    label: str | None = None
    concept_type: ConceptType | None = None
    method: ResolutionMethod = "unresolved"
    confidence: float = 0.0
    # Populated when resolution was ambiguous or rejected, so the UI can show
    # what we considered rather than silently dropping the phrase.
    alternatives: list[str] = Field(default_factory=list)

    @property
    def is_resolved(self) -> bool:
        return self.canonical_id is not None and self.method != "unresolved"