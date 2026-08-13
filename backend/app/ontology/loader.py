"""Loads the curated ontology YAML into typed structures.

This module owns the *canonical vocabulary*: every concept the resolver can map
onto and every anatomy/contraindication edge the safety engine can traverse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from app.domain.resolution import CanonicalConcept

ONTOLOGY_PATH = Path(__file__).with_name("mappings.yaml")


VALID_PREDICATES = ("skos:exactMatch", "skos:closeMatch", "skos:broadMatch")


@dataclass(frozen=True)
class OntologySource:
    """Metadata for one published vocabulary the mapping set draws on."""

    id: str
    label: str
    version: str | None = None
    terminology: str | None = None
    uri_template: str | None = None
    browser_template: str | None = None
    api_template: str | None = None
    used_for: str | None = None

    def uri_for(self, code: str) -> str | None:
        return self.uri_template.format(code=code) if self.uri_template else None

    def browser_url_for(self, code: str) -> str | None:
        return self.browser_template.format(code=code) if self.browser_template else None


@dataclass(frozen=True)
class OntologyGrounding:
    """One local concept's link to a published ontology concept.

    Deliberately a value object rather than loose fields on every concept type:
    anatomy, conditions and muscles all ground the same way, and the API and
    provenance layers want one shape to serialize.

    ``code`` is ``None`` for a concept that was reviewed and left ungrounded. In
    that case ``status`` is ``"unmapped"`` and ``evidence`` carries the reason -
    the mapping set records the *decision*, never a placeholder identifier.
    """

    local_id: str
    label: str
    source: str | None = None
    code: str | None = None
    term: str | None = None
    uri: str | None = None
    browser_url: str | None = None
    predicate: str | None = None
    status: str = "unmapped"
    evidence: str | None = None
    version: str | None = None

    @property
    def is_grounded(self) -> bool:
        """True only for a mapping that carries a real external identifier."""
        return bool(self.source and self.code and self.predicate)

    @property
    def relation(self) -> str | None:
        """The SKOS predicate, short form: ``exactMatch`` / ``closeMatch`` / ..."""
        return self.predicate.split(":", 1)[-1] if self.predicate else None


@dataclass(frozen=True)
class AnatomyConcept:
    id: str
    label: str
    aliases: tuple[str, ...]
    part_of: str | None
    grounding: OntologyGrounding | None = None


@dataclass(frozen=True)
class MuscleConcept:
    """A catalog muscle-group label and its optional grounding.

    ``id`` is the catalog's own ``muscle_groups`` string, verbatim - that is the
    join key ingestion uses to attach the mapping to the Muscle node.
    """

    id: str
    label: str
    grounding: OntologyGrounding | None = None


@dataclass(frozen=True)
class InjuryConditionConcept:
    id: str
    label: str
    aliases: tuple[str, ...]
    affects: str
    contraindicates_patterns: tuple[str, ...]
    contraindication_note: str | None = None
    grounding: OntologyGrounding | None = None


@dataclass(frozen=True)
class MovementFamily:
    id: str
    label: str
    aliases: tuple[str, ...]
    patterns: tuple[str, ...]
    note: str | None = None


@dataclass(frozen=True)
class FocusTarget:
    id: str
    label: str
    aliases: tuple[str, ...]
    muscle_groups: tuple[str, ...]
    joints: tuple[str, ...]


@dataclass
class Ontology:
    anatomy: dict[str, AnatomyConcept] = field(default_factory=dict)
    injury_conditions: dict[str, InjuryConditionConcept] = field(default_factory=dict)
    movement_families: dict[str, MovementFamily] = field(default_factory=dict)
    focus_targets: dict[str, FocusTarget] = field(default_factory=dict)
    equipment_aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    muscles: dict[str, MuscleConcept] = field(default_factory=dict)
    sources: dict[str, OntologySource] = field(default_factory=dict)
    unmapped: tuple[OntologyGrounding, ...] = ()
    mapping_set: dict = field(default_factory=dict)

    # --- ontology grounding -----------------------------------------------

    def groundings(self) -> list[OntologyGrounding]:
        """Every grounding decision in the mapping set, mapped and unmapped.

        This is the auditable list: one row per local concept that was
        considered, including the ones deliberately left without an identifier.
        """
        out = [c.grounding for c in self.anatomy.values() if c.grounding]
        out += [c.grounding for c in self.injury_conditions.values() if c.grounding]
        out += [c.grounding for c in self.muscles.values() if c.grounding]
        out += list(self.unmapped)
        return out

    def grounding_for(self, local_id: str) -> OntologyGrounding | None:
        """Look up grounding by canonical id, e.g. ``anatomy:knee``.

        Accepts the same prefixed ids the resolver emits so a caller holding a
        ``ResolvedConcept`` needs no translation step. Returns ``None`` for a
        concept type that carries no grounding at all (equipment, movement
        families, focus targets) - the caller renders nothing rather than
        implying an absent mapping is a failed one.
        """
        kind, _, identifier = local_id.partition(":")
        if not identifier:
            return None
        if kind == "anatomy":
            concept = self.anatomy.get(identifier)
            return concept.grounding if concept else None
        if kind == "injury":
            condition = self.injury_conditions.get(identifier)
            return condition.grounding if condition else None
        if kind == "muscle":
            muscle = self.muscles.get(identifier)
            return muscle.grounding if muscle else None
        return None

    # --- anatomy traversal ------------------------------------------------

    def ancestors_of(self, anatomy_id: str) -> list[str]:
        """Walk PART_OF upward: patellofemoral_joint -> knee -> lower_limb."""
        chain: list[str] = []
        seen: set[str] = set()
        current = self.anatomy.get(anatomy_id)
        while current is not None and current.part_of and current.part_of not in seen:
            seen.add(current.part_of)
            chain.append(current.part_of)
            current = self.anatomy.get(current.part_of)
        return chain

    def descendants_of(self, anatomy_id: str) -> list[str]:
        """Walk PART_OF downward: knee -> {patellofemoral, tibiofemoral}."""
        out: list[str] = []
        frontier = [anatomy_id]
        seen = {anatomy_id}
        while frontier:
            parent = frontier.pop()
            for cid, concept in self.anatomy.items():
                if concept.part_of == parent and cid not in seen:
                    seen.add(cid)
                    out.append(cid)
                    frontier.append(cid)
        return out

    def anatomical_closure(self, anatomy_id: str) -> set[str]:
        """The full set of regions an injury at ``anatomy_id`` implicates.

        Both directions matter, for different reasons:
          * descendants - an injury to the "knee" implicates its sub-structures;
          * ancestors - an injury recorded at the *patellofemoral joint* must
            still match exercises the catalog only annotates as loading "knee".

        The second direction is the one that does the work for this dataset.
        """
        return {anatomy_id, *self.ancestors_of(anatomy_id), *self.descendants_of(anatomy_id)}

    def part_of_path(self, start: str, target: str) -> list[str] | None:
        """The PART_OF chain from ``start`` up to ``target``, if one exists."""
        if start == target:
            return [start]
        chain = [start]
        current = self.anatomy.get(start)
        seen = {start}
        while current is not None and current.part_of:
            parent = current.part_of
            if parent in seen:
                return None
            chain.append(parent)
            if parent == target:
                return chain
            seen.add(parent)
            current = self.anatomy.get(parent)
        return None

    # --- lookups ----------------------------------------------------------

    def anatomy_by_catalog_joint(self, joint: str) -> AnatomyConcept | None:
        """Map a catalog ``joints_loaded`` value onto a canonical anatomy node.

        The catalog's 9 joint labels ("knee", "lumbar spine", ...) are matched
        by label or alias.
        """
        needle = joint.strip().lower()
        for concept in self.anatomy.values():
            if concept.label.lower() == needle or needle in concept.aliases:
                return concept
        return None

    def family_for_pattern(self, pattern: str) -> MovementFamily | None:
        for family in self.movement_families.values():
            if pattern in family.patterns:
                return family
        return None

    def canonical_concepts(self) -> list[CanonicalConcept]:
        """Everything the resolver may map free text onto."""
        out: list[CanonicalConcept] = []

        for concept in self.anatomy.values():
            out.append(
                CanonicalConcept(
                    id=f"anatomy:{concept.id}",
                    label=concept.label,
                    concept_type="anatomy",
                    aliases=list(concept.aliases),
                    **_grounding_fields(concept.grounding),
                )
            )

        for condition in self.injury_conditions.values():
            out.append(
                CanonicalConcept(
                    id=f"injury:{condition.id}",
                    label=condition.label,
                    concept_type="injury_condition",
                    aliases=list(condition.aliases),
                    **_grounding_fields(condition.grounding),
                )
            )

        for canonical_name, aliases in self.equipment_aliases.items():
            out.append(
                CanonicalConcept(
                    id=f"equipment:{_slug(canonical_name)}",
                    label=canonical_name,
                    concept_type="equipment",
                    aliases=list(aliases),
                )
            )

        for family in self.movement_families.values():
            out.append(
                CanonicalConcept(
                    id=f"movement_family:{family.id}",
                    label=family.label,
                    concept_type="movement_pattern",
                    aliases=list(family.aliases),
                    note=family.note,
                )
            )

        for target in self.focus_targets.values():
            out.append(
                CanonicalConcept(
                    id=f"focus:{target.id}",
                    label=target.label,
                    concept_type="muscle",
                    aliases=list(target.aliases),
                )
            )

        return out


def _predicate(value: str | None) -> str | None:
    """Accept only the SKOS predicates this system understands.

    An unrecognised predicate is dropped rather than passed through, so a typo
    in the YAML cannot produce a mapping edge with meaningless semantics.
    """
    return value if value in VALID_PREDICATES else None


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.strip().lower()).strip("_")


def _grounding_fields(grounding: OntologyGrounding | None) -> dict:
    """Project a grounding onto the ontology fields of ``CanonicalConcept``."""
    if grounding is None or not grounding.is_grounded:
        return {}
    return {
        "ontology_source": grounding.source,
        "ontology_code": grounding.code,
        "ontology_uri": grounding.uri,
        "mapping_predicate": grounding.predicate,
        "note": grounding.term,
    }


def _build_grounding(
    local_id: str,
    label: str,
    raw: dict,
    sources: dict[str, OntologySource],
) -> OntologyGrounding | None:
    """Read one concept's ``ontology:`` block into a typed grounding.

    A block with a source and code but no *recognised* predicate is downgraded
    to ``unmapped`` rather than half-applied: without a mapping relation there
    is nothing meaningful to assert about the two concepts.
    """
    block = raw.get("ontology") or {}
    if not block:
        return None

    source_id = block.get("source")
    code = str(block["code"]) if block.get("code") is not None else None
    predicate = _predicate(block.get("predicate"))
    source = sources.get(source_id) if source_id else None
    grounded = bool(source_id and code and predicate)

    return OntologyGrounding(
        local_id=local_id,
        label=label,
        source=source_id if grounded else None,
        code=code if grounded else None,
        term=block.get("term"),
        uri=source.uri_for(code) if grounded and source and code else None,
        browser_url=source.browser_url_for(code) if grounded and source and code else None,
        predicate=predicate if grounded else None,
        status=block.get("status", "verified") if grounded else "unmapped",
        evidence=block.get("evidence") or block.get("note"),
        version=block.get("version") or (source.version if source else None),
    )


def _load_sources(raw: dict) -> dict[str, OntologySource]:
    return {
        sid: OntologySource(
            id=sid,
            label=node.get("label", sid),
            version=node.get("version"),
            terminology=node.get("terminology"),
            uri_template=node.get("uri_template"),
            browser_template=node.get("browser_template"),
            api_template=node.get("api_template"),
            used_for=node.get("used_for"),
        )
        for sid, node in (raw.get("ontology_sources") or {}).items()
    }


def _load_unmapped(raw: dict) -> tuple[OntologyGrounding, ...]:
    """The register of concepts reviewed and deliberately left ungrounded."""
    out: list[OntologyGrounding] = []
    for group, node in (raw.get("unmapped") or {}).items():
        reason = node.get("reason")
        intended = node.get("intended_source")
        # A group either enumerates individual concepts ("core", "obliques") or
        # stands for a whole category left ungrounded ("equipment"). Both are
        # one row each so the register reads as a flat, countable list.
        concepts = node.get("concepts")
        for label in concepts or [group]:
            out.append(
                OntologyGrounding(
                    local_id=f"{group}:{_slug(str(label))}" if concepts else group,
                    label=str(label),
                    source=None,
                    code=None,
                    status="unmapped",
                    term=intended,
                    evidence=reason,
                )
            )
    return tuple(out)


def load_ontology(path: Path | None = None) -> Ontology:
    raw = yaml.safe_load((path or ONTOLOGY_PATH).read_text(encoding="utf-8"))
    sources = _load_sources(raw)
    ontology = Ontology(
        sources=sources,
        unmapped=_load_unmapped(raw),
        mapping_set=raw.get("mapping_set") or {},
    )

    for cid, node in (raw.get("anatomy") or {}).items():
        ontology.anatomy[cid] = AnatomyConcept(
            id=cid,
            label=node["label"],
            aliases=tuple(a.lower() for a in node.get("aliases", [])),
            part_of=node.get("part_of"),
            grounding=_build_grounding(f"anatomy:{cid}", node["label"], node, sources),
        )

    for cid, node in (raw.get("injury_conditions") or {}).items():
        ontology.injury_conditions[cid] = InjuryConditionConcept(
            id=cid,
            label=node["label"],
            aliases=tuple(a.lower() for a in node.get("aliases", [])),
            affects=node["affects"],
            contraindicates_patterns=tuple(node.get("contraindicates_patterns", [])),
            contraindication_note=node.get("contraindication_note"),
            grounding=_build_grounding(f"injury:{cid}", node["label"], node, sources),
        )

    for cid, node in (raw.get("muscles") or {}).items():
        ontology.muscles[cid] = MuscleConcept(
            id=cid,
            label=node.get("label", cid),
            grounding=_build_grounding(
                f"muscle:{cid}", node.get("label", cid), node, sources
            ),
        )

    for cid, node in (raw.get("movement_families") or {}).items():
        ontology.movement_families[cid] = MovementFamily(
            id=cid,
            label=node["label"],
            aliases=tuple(a.lower() for a in node.get("aliases", [])),
            patterns=tuple(node.get("patterns", [])),
            note=node.get("note"),
        )

    for cid, node in (raw.get("focus_targets") or {}).items():
        ontology.focus_targets[cid] = FocusTarget(
            id=cid,
            label=node["label"],
            aliases=tuple(a.lower() for a in node.get("aliases", [])),
            muscle_groups=tuple(node.get("muscle_groups", [])),
            joints=tuple(node.get("joints", [])),
        )

    ontology.equipment_aliases = {
        name: tuple(a.lower() for a in aliases)
        for name, aliases in (raw.get("equipment_aliases") or {}).items()
    }

    return ontology


@lru_cache
def get_ontology() -> Ontology:
    return load_ontology()
