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


@dataclass(frozen=True)
class AnatomyConcept:
    id: str
    label: str
    aliases: tuple[str, ...]
    part_of: str | None
    ontology_source: str | None = None
    ontology_code: str | None = None
    ontology_term: str | None = None
    ontology_status: str | None = None
    mapping_predicate: str | None = None


@dataclass(frozen=True)
class InjuryConditionConcept:
    id: str
    label: str
    aliases: tuple[str, ...]
    affects: str
    contraindicates_patterns: tuple[str, ...]
    contraindication_note: str | None = None
    ontology_source: str | None = None
    ontology_code: str | None = None
    ontology_term: str | None = None
    ontology_status: str | None = None
    mapping_predicate: str | None = None


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
    muscle_notes: dict[str, dict] = field(default_factory=dict)

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
                    ontology_source=concept.ontology_source,
                    ontology_code=concept.ontology_code,
                    mapping_predicate=_predicate(concept.mapping_predicate),
                    note=concept.ontology_status,
                )
            )

        for condition in self.injury_conditions.values():
            out.append(
                CanonicalConcept(
                    id=f"injury:{condition.id}",
                    label=condition.label,
                    concept_type="injury_condition",
                    aliases=list(condition.aliases),
                    ontology_source=condition.ontology_source,
                    ontology_code=condition.ontology_code,
                    mapping_predicate=_predicate(condition.mapping_predicate),
                    note=condition.ontology_status,
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
    return value if value in {"skos:exactMatch", "skos:closeMatch", "skos:broadMatch"} else None


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.strip().lower()).strip("_")


def _ont(raw: dict) -> dict:
    ontology = raw.get("ontology") or {}
    return {
        "ontology_source": ontology.get("source"),
        "ontology_code": ontology.get("code"),
        "ontology_term": ontology.get("term"),
        "ontology_status": ontology.get("status"),
        "mapping_predicate": ontology.get("predicate"),
    }


def load_ontology(path: Path | None = None) -> Ontology:
    raw = yaml.safe_load((path or ONTOLOGY_PATH).read_text(encoding="utf-8"))
    ontology = Ontology()

    for cid, node in (raw.get("anatomy") or {}).items():
        ontology.anatomy[cid] = AnatomyConcept(
            id=cid,
            label=node["label"],
            aliases=tuple(a.lower() for a in node.get("aliases", [])),
            part_of=node.get("part_of"),
            **_ont(node),
        )

    for cid, node in (raw.get("injury_conditions") or {}).items():
        ontology.injury_conditions[cid] = InjuryConditionConcept(
            id=cid,
            label=node["label"],
            aliases=tuple(a.lower() for a in node.get("aliases", [])),
            affects=node["affects"],
            contraindicates_patterns=tuple(node.get("contraindicates_patterns", [])),
            contraindication_note=node.get("contraindication_note"),
            **_ont(node),
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
    ontology.muscle_notes = raw.get("muscle_notes") or {}

    return ontology


@lru_cache
def get_ontology() -> Ontology:
    return load_ontology()
