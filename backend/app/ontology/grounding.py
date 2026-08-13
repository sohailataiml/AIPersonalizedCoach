"""Projection from the loaded mapping set onto the API contract.

One conversion, used by every surface that shows grounding (the REST report,
the graph-reasoning payload, the provenance panel). Keeping it in a single
place is what stops two views of the same mapping from disagreeing.
"""

from __future__ import annotations

from app.domain.ontology import (
    ConceptGrounding,
    OntologyGroundingReport,
    OntologySourceInfo,
)
from app.ontology.loader import Ontology, OntologyGrounding


def to_concept_grounding(grounding: OntologyGrounding | None) -> ConceptGrounding | None:
    """Convert a loaded grounding into its wire form.

    Fields are emitted only for a grounding that is actually grounded. A
    reviewed-but-unmapped concept keeps its label and evidence (the reason) and
    carries no source, code or relation - so a client cannot render a partial
    mapping as if it were a real one.
    """
    if grounding is None:
        return None

    if not grounding.is_grounded:
        return ConceptGrounding(
            local_id=grounding.local_id,
            label=grounding.label,
            mapping_evidence=grounding.evidence,
            status="unmapped",
        )

    return ConceptGrounding(
        local_id=grounding.local_id,
        label=grounding.label,
        ontology_source=grounding.source,
        ontology_code=grounding.code,
        ontology_term=grounding.term,
        ontology_uri=grounding.uri,
        browser_url=grounding.browser_url,
        mapping_relation=grounding.relation,  # type: ignore[arg-type]
        mapping_evidence=grounding.evidence,
        mapping_version=grounding.version,
        status="verified",
    )


def build_grounding_report(ontology: Ontology) -> OntologyGroundingReport:
    """The whole mapping set as one auditable document."""
    mapped: list[ConceptGrounding] = []
    unmapped: list[ConceptGrounding] = []

    for grounding in ontology.groundings():
        projected = to_concept_grounding(grounding)
        if projected is None:
            continue
        (mapped if projected.is_grounded else unmapped).append(projected)

    mapped.sort(key=lambda row: row.local_id)
    unmapped.sort(key=lambda row: row.local_id)

    by_relation: dict[str, int] = {}
    for row in mapped:
        if row.mapping_relation:
            by_relation[row.mapping_relation] = by_relation.get(row.mapping_relation, 0) + 1

    return OntologyGroundingReport(
        mapping_set_version=ontology.mapping_set.get("version"),
        verified_on=ontology.mapping_set.get("verified_on"),
        method=ontology.mapping_set.get("method"),
        sources=[
            OntologySourceInfo(
                id=source.id,
                label=source.label,
                version=source.version,
                used_for=source.used_for,
            )
            for source in ontology.sources.values()
        ],
        mapped=mapped,
        unmapped=unmapped,
        counts={
            "mapped": len(mapped),
            "unmapped": len(unmapped),
            **{f"relation_{name}": count for name, count in sorted(by_relation.items())},
        },
    )
