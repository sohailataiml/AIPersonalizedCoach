"""Serializable ontology-grounding contracts.

The loader's ``OntologyGrounding`` is the internal value object. These models
are what crosses the API boundary, and they exist separately for one reason:
the wire format is a promise to the frontend, while the loader's shape is free
to change with the YAML.

The invariant this module protects is the same one the mapping set protects: a
grounding either carries a real, resolvable external identifier, or it says
plainly that it has none. There is no third state, and nothing here can
manufacture the first from the second.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MappingRelation = Literal["exactMatch", "closeMatch", "broadMatch"]
GroundingStatus = Literal["verified", "unmapped"]


class ConceptGrounding(BaseModel):
    """One local concept's link to a published ontology concept.

    ``local_id`` is always the authority for identity inside this system.
    ``ontology_code`` standardises *clinical* identity for interchange; it never
    replaces the local id and no safety rule reads it.
    """

    local_id: str
    label: str
    ontology_source: str | None = None
    ontology_code: str | None = None
    ontology_term: str | None = None
    ontology_uri: str | None = None
    browser_url: str | None = None
    mapping_relation: MappingRelation | None = None
    mapping_evidence: str | None = None
    mapping_version: str | None = None
    status: GroundingStatus = "unmapped"

    @property
    def is_grounded(self) -> bool:
        return bool(self.ontology_source and self.ontology_code and self.mapping_relation)


class OntologySourceInfo(BaseModel):
    id: str
    label: str
    version: str | None = None
    used_for: str | None = None


class OntologyGroundingReport(BaseModel):
    """The full auditable mapping set, mapped and unmapped alike.

    ``unmapped`` is not an error list. It is the register of concepts that were
    reviewed and deliberately left without an identifier, which is what makes
    the mapped half trustworthy.
    """

    mapping_set_version: str | None = None
    verified_on: str | None = None
    method: str | None = None
    sources: list[OntologySourceInfo] = Field(default_factory=list)
    mapped: list[ConceptGrounding] = Field(default_factory=list)
    unmapped: list[ConceptGrounding] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
