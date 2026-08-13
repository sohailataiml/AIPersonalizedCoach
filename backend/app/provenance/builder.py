"""Provenance construction.

Provenance is assembled from deterministic evidence only - the graph paths and
rule ids the safety engine already produced. The LLM is never asked to invent a
justification, because a fluent explanation of a decision the system did not
actually make is worse than no explanation at all.

Aligned to PROV-O conceptually: each item records what was generated
(the decision), what activity produced it (graph traversal vs LLM composition
vs post-validation), and what it was derived from (the traversed paths).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.exercise import ExerciseCandidate
from app.domain.resolution import ResolvedConcept
from app.domain.safety import SafetyDecision
from app.domain.workout import GeneratedWorkout, PostValidationReport
from app.safety.engine import SafetyContext

DecisionLabel = Literal["included", "downranked", "filtered", "substituted"]


class EvidencePath(BaseModel):
    path: list[str]
    rendered: str


class ProvenanceItem(BaseModel):
    exercise_id: str
    exercise: str
    decision: DecisionLabel
    reasons: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    evidence: list[EvidencePath] = Field(default_factory=list)
    decision_source: Literal["knowledge_graph", "llm_composition", "post_validation"] = (
        "knowledge_graph"
    )
    score: float | None = None
    score_adjustment: float = 0.0
    in_plan: bool = False
    section: str | None = None


class ProvenanceBundle(BaseModel):
    included: list[ProvenanceItem] = Field(default_factory=list)
    filtered: list[ProvenanceItem] = Field(default_factory=list)
    resolved_concepts: list[ResolvedConcept] = Field(default_factory=list)
    unresolved_concepts: list[ResolvedConcept] = Field(default_factory=list)
    member_facts: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


def build_provenance(
    workout: GeneratedWorkout,
    decisions: dict[str, SafetyDecision],
    candidates: list[ExerciseCandidate],
    context: SafetyContext,
    report: PostValidationReport,
) -> ProvenanceBundle:
    bundle = ProvenanceBundle()
    score_by_id = {c.exercise.id: c for c in candidates}

    section_by_id: dict[str, str] = {}
    substituted_ids: set[str] = set()
    for section in workout.sections:
        for item in section.exercises:
            section_by_id[item.exercise_id] = section.name
            if item.substituted_for:
                substituted_ids.add(item.exercise_id)

    for exercise_id, section_name in section_by_id.items():
        decision = decisions.get(exercise_id)
        candidate = score_by_id.get(exercise_id)
        if decision is None:
            continue

        reasons = _inclusion_reasons(decision, candidate, context)
        bundle.included.append(
            ProvenanceItem(
                exercise_id=exercise_id,
                exercise=decision.exercise_name,
                decision="substituted" if exercise_id in substituted_ids else "included",
                reasons=reasons,
                rule_ids=[r.rule_id for r in decision.reasons],
                evidence=_evidence(decision),
                decision_source=(
                    "post_validation" if exercise_id in substituted_ids else "knowledge_graph"
                ),
                score=candidate.score if candidate else None,
                score_adjustment=decision.score_adjustment,
                in_plan=True,
                section=section_name,
            )
        )

    for exercise_id, decision in decisions.items():
        if exercise_id in section_by_id:
            continue
        if decision.status == "allowed":
            continue  # eligible but simply not chosen - not a safety event
        bundle.filtered.append(
            ProvenanceItem(
                exercise_id=exercise_id,
                exercise=decision.exercise_name,
                decision="filtered" if decision.is_excluded else "downranked",
                reasons=decision.reason_messages(),
                rule_ids=[r.rule_id for r in decision.reasons],
                evidence=_evidence(decision),
                decision_source="knowledge_graph",
                score_adjustment=decision.score_adjustment,
                in_plan=False,
            )
        )

    bundle.filtered.sort(key=lambda item: (item.decision != "filtered", item.exercise))

    bundle.resolved_concepts = [c for c in context.resolved_concepts if c.is_resolved]
    bundle.unresolved_concepts = [c for c in context.resolved_concepts if not c.is_resolved]
    bundle.member_facts = _member_facts(context)
    bundle.counts = {
        "catalog_total": len(decisions),
        "excluded": sum(1 for d in decisions.values() if d.status == "excluded"),
        "downranked": sum(1 for d in decisions.values() if d.status == "downranked"),
        "eligible": len(candidates),
        "in_plan": len(section_by_id),
        "post_validation_rejections": len(report.rejected),
        "post_validation_replacements": len(report.replacements),
    }
    return bundle


def build_pre_generation_provenance(
    decisions: dict[str, SafetyDecision],
    candidates: list[ExerciseCandidate],
    context: SafetyContext,
) -> ProvenanceBundle:
    """Provenance for a request that was evaluated but never composed.

    ``build_provenance`` above needs a ``GeneratedWorkout`` because it reports on
    what actually made it into a plan. The MCP ``evaluate_workout_request`` tool
    deliberately stops before LLM composition, so it has decisions and ranked
    candidates but no plan.

    This builds the same ``ProvenanceBundle`` from that earlier point in the
    pipeline, reusing the identical evidence and member-fact helpers. Nothing is
    re-derived here: ``in_plan`` is uniformly False and the post-validation
    counters are absent, because neither has happened yet.
    """
    bundle = ProvenanceBundle()
    score_by_id = {c.exercise.id: c for c in candidates}

    for exercise_id, candidate in score_by_id.items():
        decision = decisions.get(exercise_id)
        if decision is None:
            continue
        bundle.included.append(
            ProvenanceItem(
                exercise_id=exercise_id,
                exercise=decision.exercise_name,
                decision="downranked" if decision.status == "downranked" else "included",
                reasons=_inclusion_reasons(decision, candidate, context),
                rule_ids=[r.rule_id for r in decision.reasons],
                evidence=_evidence(decision),
                decision_source="knowledge_graph",
                score=candidate.score,
                score_adjustment=decision.score_adjustment,
                in_plan=False,
            )
        )

    bundle.included.sort(key=lambda item: -(item.score or 0.0))

    for exercise_id, decision in decisions.items():
        if exercise_id in score_by_id or not decision.is_excluded:
            continue
        bundle.filtered.append(
            ProvenanceItem(
                exercise_id=exercise_id,
                exercise=decision.exercise_name,
                decision="filtered",
                reasons=decision.reason_messages(),
                rule_ids=[r.rule_id for r in decision.reasons],
                evidence=_evidence(decision),
                decision_source="knowledge_graph",
                score_adjustment=decision.score_adjustment,
                in_plan=False,
            )
        )

    bundle.filtered.sort(key=lambda item: item.exercise)
    bundle.resolved_concepts = [c for c in context.resolved_concepts if c.is_resolved]
    bundle.unresolved_concepts = [c for c in context.resolved_concepts if not c.is_resolved]
    bundle.member_facts = _member_facts(context)
    bundle.counts = {
        "catalog_total": len(decisions),
        "excluded": sum(1 for d in decisions.values() if d.status == "excluded"),
        "downranked": sum(1 for d in decisions.values() if d.status == "downranked"),
        "eligible": len(candidates),
        "in_plan": 0,
    }
    return bundle


def _evidence(decision: SafetyDecision) -> list[EvidencePath]:
    return [
        EvidencePath(path=path.as_steps(), rendered=path.render())
        for path in decision.graph_paths
    ]


def _inclusion_reasons(
    decision: SafetyDecision,
    candidate: ExerciseCandidate | None,
    context: SafetyContext,
) -> list[str]:
    """Why this exercise was allowed to appear - stated positively."""
    reasons: list[str] = []

    required = [] if candidate is None else candidate.exercise.equipment_required
    if required:
        reasons.append(f"Required equipment available: {', '.join(required)}.")
    else:
        reasons.append("Bodyweight - no equipment required.")

    if context.injuries and not any(
        r.rule_id in {"injury_region_stress", "injury_contraindicated_pattern"}
        for r in decision.reasons
    ):
        injury = context.injuries[0]
        reasons.append(
            f"No graph-derived contraindication against {injury['injury_name']} "
            f"({injury['condition_label']})."
        )

    if candidate is not None:
        reasons.extend(candidate.rank_reasons)

    # Anything the graph flagged still gets stated, so an included-but-cautioned
    # exercise never looks unconditionally safe.
    reasons.extend(decision.reason_messages())
    return reasons


def _member_facts(context: SafetyContext) -> list[str]:
    member = context.member
    facts = [f"Member: {member.profile.name} ({member.profile.tier})."]

    for injury in context.injuries:
        facts.append(
            f"Injury: {injury['injury_name']} - {injury.get('severity')}/{injury.get('status')}, "
            f"mapped to {injury['condition_label']}."
        )
    if context.available_equipment:
        facts.append(f"Equipment for this session: {', '.join(sorted(context.available_equipment))}.")
    if member.goals:
        top = sorted(member.goals, key=lambda g: g.priority)[0]
        facts.append(f"Primary goal: {top.text}.")
    if member.preferences.dislikes:
        facts.append(f"Dislikes (ranking only): {', '.join(member.preferences.dislikes)}.")
    return facts
