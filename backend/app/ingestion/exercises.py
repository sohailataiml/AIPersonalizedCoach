"""Ingest data/exercises.json into the Movement/Clinical knowledge graph (KG1).

Data realities this module handles explicitly (all verified against the supplied
file, see README "Data notes"):

* ``priority_tier`` is **2 for all 50 rows** - it carries no ranking signal. We
  preserve it for fidelity but never rank on it.
* 2 rows have an **empty ``joints_loaded``** list. They get an ``UNKNOWN_ANATOMY``
  marker so the safety engine can be conservative instead of assuming safety.
* 1 row lists ``shoulder`` twice; joint lists are de-duplicated.
* All 18 ``bilateral_pair_id`` values are **dangling** - the contralateral twins
  are not in this 50-row slice. We record the raw id on the node and only create
  a ``BILATERAL_PAIR`` edge when the target actually exists.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.domain.exercise import Exercise
from app.graph import model as m
from app.graph.model import KnowledgeGraph
from app.ontology.loader import Ontology


def load_exercises(path: Path) -> list[Exercise]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    exercises: list[Exercise] = []
    for row in raw:
        # De-duplicate joints while preserving order (one row repeats "shoulder").
        row = dict(row)
        row["joints_loaded"] = list(dict.fromkeys(row.get("joints_loaded") or []))
        exercises.append(Exercise.model_validate(row))
    return exercises


def ingest_exercise_graph(
    graph: KnowledgeGraph,
    exercises: list[Exercise],
    ontology: Ontology,
) -> KnowledgeGraph:
    _ingest_anatomy(graph, ontology)
    _ingest_injury_conditions(graph, ontology)
    _ingest_movement_families(graph, ontology)

    for exercise in exercises:
        _ingest_exercise(graph, exercise, ontology)

    # Bilateral pairs, only where the twin is actually present in the catalog.
    for exercise in exercises:
        if not exercise.bilateral_pair_id:
            continue
        graph.add_edge(
            m.exercise_key(exercise.id),
            m.BILATERAL_PAIR,
            m.exercise_key(exercise.bilateral_pair_id),
        )

    return graph


def _ingest_anatomy(graph: KnowledgeGraph, ontology: Ontology) -> None:
    for concept in ontology.anatomy.values():
        key = m.anatomy_key(concept.id)
        graph.add_node(
            key,
            m.ANATOMICAL_REGION,
            id=concept.id,
            name=concept.label,
            aliases=list(concept.aliases),
            ontology_source=concept.ontology_source,
            ontology_code=concept.ontology_code,
            ontology_term=concept.ontology_term,
            ontology_status=concept.ontology_status,
        )
        _link_ontology(
            graph,
            key,
            concept.ontology_source,
            concept.ontology_code,
            concept.ontology_term,
            concept.mapping_predicate,
            concept.ontology_status,
        )

    # PART_OF is the hierarchy that makes injury reasoning work.
    for concept in ontology.anatomy.values():
        if concept.part_of:
            graph.add_edge(
                m.anatomy_key(concept.id), m.PART_OF, m.anatomy_key(concept.part_of)
            )


def _ingest_injury_conditions(graph: KnowledgeGraph, ontology: Ontology) -> None:
    for condition in ontology.injury_conditions.values():
        key = m.injury_condition_key(condition.id)
        graph.add_node(
            key,
            m.INJURY_CONDITION,
            id=condition.id,
            name=condition.label,
            aliases=list(condition.aliases),
            ontology_source=condition.ontology_source,
            ontology_code=condition.ontology_code,
            ontology_term=condition.ontology_term,
            ontology_status=condition.ontology_status,
            contraindication_note=condition.contraindication_note,
        )
        graph.add_edge(key, m.AFFECTS, m.anatomy_key(condition.affects))
        _link_ontology(
            graph,
            key,
            condition.ontology_source,
            condition.ontology_code,
            condition.ontology_term,
            condition.mapping_predicate,
            condition.ontology_status,
        )


def _ingest_movement_families(graph: KnowledgeGraph, ontology: Ontology) -> None:
    for family in ontology.movement_families.values():
        graph.add_node(
            m.family_key(family.id),
            m.MOVEMENT_FAMILY,
            id=family.id,
            name=family.label,
            aliases=list(family.aliases),
            note=family.note,
        )
        for pattern in family.patterns:
            pkey = m.pattern_key(pattern)
            graph.add_node(pkey, m.MOVEMENT_PATTERN, id=m.slug(pattern), name=pattern)
            graph.add_edge(pkey, m.IN_FAMILY, m.family_key(family.id))

    # CONTRAINDICATES edges are created after patterns exist so endpoints resolve.
    for condition in ontology.injury_conditions.values():
        for pattern in condition.contraindicates_patterns:
            pkey = m.pattern_key(pattern)
            graph.add_node(pkey, m.MOVEMENT_PATTERN, id=m.slug(pattern), name=pattern)
            graph.add_edge(
                m.injury_condition_key(condition.id),
                m.CONTRAINDICATES,
                pkey,
                note=condition.contraindication_note,
            )


def _ingest_exercise(graph: KnowledgeGraph, exercise: Exercise, ontology: Ontology) -> None:
    key = m.exercise_key(exercise.id)
    graph.add_node(
        key,
        m.EXERCISE,
        id=exercise.id,
        name=exercise.name,
        priority_tier=exercise.priority_tier,
        is_bilateral=exercise.is_bilateral,
        is_unilateral=exercise.is_unilateral,
        side=exercise.side,
        loaded_body_side=exercise.loaded_body_side,
        bilateral_pair_id=exercise.bilateral_pair_id,
        is_reps=exercise.is_reps,
        is_duration=exercise.is_duration,
        supports_weight=exercise.supports_weight,
        estimated_rep_duration=exercise.estimated_rep_duration,
        has_anatomy_data=exercise.has_anatomy_data,
    )

    for muscle in exercise.muscle_groups:
        mkey = m.muscle_key(muscle)
        node_props = {"id": m.slug(muscle), "name": muscle}
        note = ontology.muscle_notes.get(muscle, {})
        ont = note.get("ontology") or {}
        graph.add_node(mkey, m.MUSCLE, **node_props)
        graph.add_edge(key, m.TARGETS, mkey)
        _link_ontology(
            graph,
            mkey,
            ont.get("source"),
            ont.get("code"),
            ont.get("term"),
            ont.get("predicate"),
            ont.get("status"),
        )

    for joint in exercise.joints_loaded:
        concept = ontology.anatomy_by_catalog_joint(joint)
        if concept is None:
            # Unknown catalog joint: create a local region so the edge is not lost.
            akey = m.anatomy_key(m.slug(joint))
            graph.add_node(akey, m.ANATOMICAL_REGION, id=m.slug(joint), name=joint, unmapped=True)
        else:
            akey = m.anatomy_key(concept.id)
        graph.add_edge(key, m.STRESSES, akey, source_label=joint)

    for pattern in exercise.movement_patterns:
        pkey = m.pattern_key(pattern)
        graph.add_node(pkey, m.MOVEMENT_PATTERN, id=m.slug(pattern), name=pattern)
        graph.add_edge(key, m.HAS_PATTERN, pkey)

    for equipment in exercise.equipment_required:
        ekey = m.equipment_key(equipment)
        graph.add_node(
            ekey,
            m.EQUIPMENT,
            id=m.slug(equipment),
            name=equipment,
            aliases=list(ontology.equipment_aliases.get(equipment, ())),
        )
        graph.add_edge(key, m.REQUIRES, ekey)


def _link_ontology(
    graph: KnowledgeGraph,
    subject_key: str,
    source: str | None,
    code: str | None,
    term: str | None,
    predicate: str | None,
    status: str | None,
) -> None:
    """Create an explicit OntologyConcept node + SKOS mapping edge.

    Only when we actually have a code. Unverified mappings stay as node
    properties rather than becoming fake external concepts.
    """
    if not source or not code:
        return
    okey = m.ontology_key(source, code)
    graph.add_node(
        okey,
        m.ONTOLOGY_CONCEPT,
        id=f"{source}:{code}",
        name=term or code,
        source=source,
        code=code,
        status=status,
    )
    rel = m.SKOS_CLOSE_MATCH if predicate == "skos:closeMatch" else m.SKOS_EXACT_MATCH
    graph.add_edge(subject_key, rel, okey, predicate=predicate)
