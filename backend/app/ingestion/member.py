"""Ingest data/member-context.json into the Member Context graph (KG2).

The member is decomposed into queryable nodes - never stored as one JSON blob.
Longitudinal observations (adherence weeks, sleep nights, weights, chats) keep
their timestamps as individual nodes so the copilot can run real queries.

The two graphs are joined here, at ingest time, through canonical concepts:

    Member -HAS_INJURY-> Injury -MAPS_TO-> InjuryCondition -AFFECTS-> AnatomicalRegion
    Member -HAS_EQUIPMENT-> Equipment  (the same Equipment nodes KG1 uses)
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from app.domain.member import (
    ExercisePerformance,
    MemberContext,
)
from app.graph import model as m
from app.graph.model import KnowledgeGraph
from app.ontology.loader import Ontology


def load_member_context(path: Path) -> MemberContext:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.pop("_note", None)

    # workout_history stores bare display names; lift them into typed objects.
    for session in raw.get("workout_history", []):
        session["exercises"] = [
            {"name": name} if isinstance(name, str) else name
            for name in session.get("exercises", [])
        ]

    return MemberContext.model_validate(raw)


def resolve_injury_condition(ontology: Ontology, injury) -> str | None:
    """Map a member injury onto a canonical InjuryCondition.

    Prefers the clinically specific condition when the notes support it: the
    sample member's notes say "Patellofemoral pain", which is materially more
    precise than generic knee pain and carries different contraindications.
    """
    haystack = " ".join(
        filter(None, [injury.region, injury.joint, injury.notes, injury.snomedct_hint])
    ).lower()

    best: tuple[int, str] | None = None
    for cid, condition in ontology.injury_conditions.items():
        for alias in condition.aliases:
            if alias in haystack:
                score = len(alias)
                if best is None or score > best[0]:
                    best = (score, cid)
    if best:
        return best[1]

    # Fall back to any condition whose affected region matches the injury joint.
    if injury.joint:
        joint_concept = ontology.anatomy_by_catalog_joint(injury.joint)
        if joint_concept:
            for cid, condition in ontology.injury_conditions.items():
                if condition.affects == joint_concept.id:
                    return cid
    return None


def injury_body_side(injury) -> str | None:
    """Extract laterality from free text, e.g. "left knee" -> "left"."""
    text = f"{injury.region or ''} {injury.notes or ''}".lower()
    if "left" in text:
        return "left"
    if "right" in text:
        return "right"
    return None


def ingest_member_graph(
    graph: KnowledgeGraph,
    context: MemberContext,
    ontology: Ontology,
    exercise_name_index: dict[str, str] | None = None,
) -> KnowledgeGraph:
    profile = context.profile
    mkey = m.member_key(profile.id)
    graph.add_node(
        mkey,
        m.MEMBER,
        id=profile.id,
        name=profile.name,
        age=profile.age,
        sex=profile.sex,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        timezone=profile.timezone,
        member_since=profile.member_since,
        coach_id=profile.coach_id,
        tier=profile.tier,
    )

    _ingest_goals(graph, mkey, context)
    _ingest_preferences(graph, mkey, context)
    _ingest_equipment(graph, mkey, context, ontology)
    _ingest_injuries(graph, mkey, context, ontology)
    _ingest_history(graph, mkey, context, exercise_name_index or {})
    _ingest_adherence(graph, mkey, context)
    _ingest_biomarkers(graph, mkey, context)
    _ingest_labs(graph, mkey, context)
    _ingest_chat(graph, mkey, context)
    _ingest_brief(graph, mkey, context)

    return graph


def _ingest_goals(graph: KnowledgeGraph, mkey: str, context: MemberContext) -> None:
    for goal in context.goals:
        key = f"{m.GOAL}:{goal.id}"
        graph.add_node(
            key,
            m.GOAL,
            id=goal.id,
            name=goal.text,
            priority=goal.priority,
            target_date=goal.target_date,
        )
        graph.add_edge(mkey, m.HAS_GOAL, key, priority=goal.priority)


def _ingest_preferences(graph: KnowledgeGraph, mkey: str, context: MemberContext) -> None:
    prefs = context.preferences
    key = f"{m.PREFERENCE}:{context.profile.id}"
    graph.add_node(
        key,
        m.PREFERENCE,
        id=f"pref_{context.profile.id}",
        name="Training preferences",
        preferred_session_minutes=prefs.preferred_session_minutes,
        training_days_per_week=prefs.training_days_per_week,
        preferred_days=list(prefs.preferred_days),
        dislikes=list(prefs.dislikes),
        notes=prefs.notes,
    )
    graph.add_edge(mkey, m.HAS_PREFERENCE, key)

    # Dislikes are first-class nodes so the UI can show that a preference
    # influenced ranking WITHOUT it ever becoming a safety exclusion.
    for dislike in prefs.dislikes:
        dkey = f"{m.PREFERENCE}:dislike:{m.slug(dislike)}"
        graph.add_node(dkey, m.PREFERENCE, id=m.slug(dislike), name=dislike, kind="dislike")
        graph.add_edge(mkey, m.DISLIKES, dkey)


def _ingest_equipment(
    graph: KnowledgeGraph, mkey: str, context: MemberContext, ontology: Ontology
) -> None:
    for equipment in context.equipment_available:
        ekey = m.equipment_key(equipment)
        graph.add_node(
            ekey,
            m.EQUIPMENT,
            id=m.slug(equipment),
            name=equipment,
            aliases=list(ontology.equipment_aliases.get(equipment, ())),
        )
        graph.add_edge(mkey, m.HAS_EQUIPMENT, ekey)


def _ingest_injuries(
    graph: KnowledgeGraph, mkey: str, context: MemberContext, ontology: Ontology
) -> None:
    for injury in context.injuries:
        key = f"{m.INJURY}:{injury.id}"
        side = injury_body_side(injury)
        graph.add_node(
            key,
            m.INJURY,
            id=injury.id,
            name=f"{injury.region.title()} ({injury.status})" if injury.region else injury.id,
            region=injury.region,
            joint=injury.joint,
            status=injury.status,
            severity=injury.severity,
            since=injury.since,
            notes=injury.notes,
            body_side=side,
            snomedct_hint=injury.snomedct_hint,
        )
        graph.add_edge(mkey, m.HAS_INJURY, key)

        condition_id = resolve_injury_condition(ontology, injury)
        if condition_id:
            graph.add_edge(key, m.MAPS_TO, m.injury_condition_key(condition_id))
        elif injury.joint:
            # No condition matched: still connect to anatomy so the region is
            # protected, and mark the gap rather than silently dropping it.
            concept = ontology.anatomy_by_catalog_joint(injury.joint)
            if concept:
                graph.add_edge(key, m.AFFECTS, m.anatomy_key(concept.id), unmapped_condition=True)


def _ingest_history(
    graph: KnowledgeGraph,
    mkey: str,
    context: MemberContext,
    exercise_name_index: dict[str, str],
) -> None:
    for session in context.workout_history:
        key = f"{m.WORKOUT_SESSION}:{context.profile.id}:{session.date}"
        graph.add_node(
            key,
            m.WORKOUT_SESSION,
            id=f"{context.profile.id}:{session.date}",
            name=session.title,
            date=session.date,
            planned=session.planned,
            completed=session.completed,
            duration_min=session.duration_min,
            rpe=session.rpe,
        )
        graph.add_edge(
            mkey,
            m.COMPLETED if session.completed else m.SCHEDULED,
            key,
            date=session.date,
        )

        for performance in session.exercises:
            resolved = _match_history_name(performance, exercise_name_index)
            pkey = f"{m.EXERCISE_PERFORMANCE}:{session.date}:{m.slug(performance.name)}"
            graph.add_node(
                pkey,
                m.EXERCISE_PERFORMANCE,
                id=m.slug(performance.name),
                name=performance.name,
                date=session.date,
                resolved_exercise_id=resolved,
            )
            graph.add_edge(key, m.CONTAINS, pkey)
            if resolved:
                graph.add_edge(pkey, m.PERFORMED_EXERCISE, m.exercise_key(resolved))


def _match_history_name(
    performance: ExercisePerformance, index: dict[str, str]
) -> str | None:
    """Best-effort link from a history display name to a catalog exercise.

    History names such as "KB Romanian Deadlift" do not exist in the 50-row
    catalog. We link only on a confident normalized match and leave the rest
    unresolved rather than guessing.
    """
    if performance.resolved_exercise_id:
        return performance.resolved_exercise_id
    normalized = m.slug(performance.name)
    return index.get(normalized)


def _ingest_adherence(graph: KnowledgeGraph, mkey: str, context: MemberContext) -> None:
    for observation in context.adherence.weekly_completion_pct:
        key = f"{m.ADHERENCE_OBSERVATION}:{context.profile.id}:{observation.week_of}"
        graph.add_node(
            key,
            m.ADHERENCE_OBSERVATION,
            id=observation.week_of,
            name=f"Adherence week of {observation.week_of}",
            week_of=observation.week_of,
            pct=observation.pct,
        )
        graph.add_edge(mkey, m.HAS_ADHERENCE, key, week_of=observation.week_of)


def _ingest_biomarkers(graph: KnowledgeGraph, mkey: str, context: MemberContext) -> None:
    bio = context.biomarkers
    member_id = context.profile.id

    for metric, value in (
        ("resting_hr_bpm", bio.resting_hr_bpm),
        ("hrv_ms", bio.hrv_ms),
    ):
        if value is None:
            continue
        key = f"{m.BIOMARKER_OBSERVATION}:{member_id}:{metric}"
        graph.add_node(
            key,
            m.BIOMARKER_OBSERVATION,
            id=metric,
            name=metric,
            metric=metric,
            value=value,
        )
        graph.add_edge(mkey, m.HAS_BIOMARKER, key, metric=metric)

    # Sleep is supplied as a bare 7-element array with no dates. We anchor it to
    # the coach brief date so the copilot can plot a real weekly series, and we
    # record `date_inferred=True` so the UI never implies more precision than
    # the data actually has.
    anchor = _brief_date(context)
    nights = bio.sleep_hours_last_7_days
    for offset, hours in enumerate(nights):
        night = anchor - timedelta(days=len(nights) - offset)
        key = f"{m.BIOMARKER_OBSERVATION}:{member_id}:sleep:{night.isoformat()}"
        graph.add_node(
            key,
            m.BIOMARKER_OBSERVATION,
            id=f"sleep:{night.isoformat()}",
            name="Sleep hours",
            metric="sleep_hours",
            value=hours,
            date=night.isoformat(),
            date_inferred=True,
        )
        graph.add_edge(mkey, m.HAS_BIOMARKER, key, metric="sleep_hours")

    for weight in bio.weight_trend_kg:
        key = f"{m.BIOMARKER_OBSERVATION}:{member_id}:weight:{weight.date}"
        graph.add_node(
            key,
            m.BIOMARKER_OBSERVATION,
            id=f"weight:{weight.date}",
            name="Body weight",
            metric="weight_kg",
            value=weight.kg,
            date=weight.date,
        )
        graph.add_edge(mkey, m.HAS_BIOMARKER, key, metric="weight_kg")


def _brief_date(context: MemberContext) -> date:
    raw = context.coach_brief.generated_for
    if raw:
        try:
            return datetime.fromisoformat(raw).date()
        except ValueError:
            pass
    return date.today()


def _ingest_labs(graph: KnowledgeGraph, mkey: str, context: MemberContext) -> None:
    labs = context.labs
    member_id = context.profile.id

    if labs.blood_panel:
        panel = labs.blood_panel
        key = f"{m.LAB_RESULT}:{member_id}:blood:{panel.date}"
        graph.add_node(
            key,
            m.LAB_RESULT,
            id=f"blood:{panel.date}",
            name="Blood panel",
            panel="blood_panel",
            **panel.model_dump(exclude_none=True),
        )
        graph.add_edge(mkey, m.HAS_LAB_RESULT, key, date=panel.date)

    if labs.dexa_scan:
        dexa = labs.dexa_scan
        key = f"{m.DEXA_RESULT}:{member_id}:{dexa.date}"
        graph.add_node(
            key,
            m.DEXA_RESULT,
            id=f"dexa:{dexa.date}",
            name="DEXA scan",
            **dexa.model_dump(exclude_none=True),
        )
        graph.add_edge(mkey, m.HAS_DEXA_RESULT, key, date=dexa.date)


def _ingest_chat(graph: KnowledgeGraph, mkey: str, context: MemberContext) -> None:
    for index, message in enumerate(context.chat_history):
        key = f"{m.CHAT_MESSAGE}:{context.profile.id}:{index}"
        graph.add_node(
            key,
            m.CHAT_MESSAGE,
            id=f"msg_{index}",
            name=message.text[:60],
            ts=message.ts,
            sender=message.sender,
            text=message.text,
            attachments=[a.model_dump() for a in message.attachments],
        )
        graph.add_edge(mkey, m.PARTICIPATED_IN, key, ts=message.ts)


def _ingest_brief(graph: KnowledgeGraph, mkey: str, context: MemberContext) -> None:
    brief = context.coach_brief
    key = f"{m.COACH_BRIEF}:{context.profile.id}:{brief.generated_for}"
    graph.add_node(
        key,
        m.COACH_BRIEF,
        id=str(brief.generated_for),
        name=f"Coach brief {brief.generated_for}",
        generated_for=brief.generated_for,
        morning_tasks=[task.model_dump() for task in brief.morning_tasks],
    )
    graph.add_edge(mkey, m.HAS_BRIEF, key)

    if brief.churn_risk:
        ckey = f"{m.CHURN_SIGNAL}:{context.profile.id}"
        graph.add_node(
            ckey,
            m.CHURN_SIGNAL,
            id=f"churn_{context.profile.id}",
            name=f"Churn risk: {brief.churn_risk.level}",
            level=brief.churn_risk.level,
            reasons=list(brief.churn_risk.reasons),
        )
        graph.add_edge(mkey, m.HAS_CHURN_SIGNAL, ckey)


def build_exercise_name_index(exercises) -> dict[str, str]:
    return {m.slug(exercise.name): exercise.id for exercise in exercises}
