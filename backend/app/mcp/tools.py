"""MCP tool implementations.

Every function here is an **adapter**: it accepts a ``Services`` container,
delegates to the services the REST API already uses, and reshapes the result
into an AI-facing schema. There is deliberately no business logic - no rule is
evaluated, no traversal is written, no threshold is applied.

Concretely, the delegation is:

    get_member_context      -> GraphRepository + copilot.analytics
    resolve_coach_concepts  -> agents.intent.parse_intent -> ConceptResolver
    evaluate_workout_request-> parse_intent -> SafetyEngine -> rank_candidates
                               -> provenance builders

If a safety question is ever asked of this module, the answer must come from
``SafetyEngine``. That is what keeps the knowledge graph the safety authority
regardless of which interface the request arrived through.

These take ``Services`` explicitly rather than reaching for a global, so they can
be unit-tested against an in-memory container without an ASGI app or a client
session.
"""

from __future__ import annotations

import uuid

from app.agents.intent import parse_intent
from app.api.deps import Services
from app.copilot import analytics
from app.domain.safety import SafetyDecision
from app.domain.workout import WorkoutIntent
from app.mcp.schemas import (
    BiomarkerView,
    CandidateView,
    ChurnView,
    CoachBriefView,
    ConceptView,
    ExcludedView,
    ExerciseProvenanceResult,
    ExerciseSafetyResult,
    GoalView,
    GraphPathView,
    InjuryEvidenceView,
    InjuryView,
    IntentView,
    MemberContextView,
    MetricTrendResult,
    ObservationView,
    PreferencesView,
    ProvenanceItemView,
    ResolveConceptsResult,
    SafeCandidatesResult,
    SafetyReasonView,
    SafetySummaryView,
    TrendView,
    WorkoutRequestEvaluation,
)
from app.member.trajectory import MemberTrajectoryService
from app.provenance.builder import build_pre_generation_provenance
from app.provenance.graph_trace import build_graph_reasoning
from app.safety.ranking import rank_candidates

# Keeps a tool result inside a sane context budget. The catalog is ~50 items, so
# this only ever truncates the long tail of low-scoring candidates.
MAX_CANDIDATES = 40
MAX_EXCLUDED = 40


class MemberNotFoundError(ValueError):
    """Raised when the requested member is not in the member graph."""


class ExerciseNotFoundError(ValueError):
    """Raised when the requested exercise is not in the catalog."""


def _trend(result: analytics.TrendResult) -> TrendView:
    """Project an analytics trend, preserving 'no data' rather than zero-filling."""
    if not result.has_data:
        return TrendView(has_data=False)
    return TrendView(
        has_data=True,
        labels=list(result.labels),
        values=list(result.values),
        first=result.first,
        latest=result.latest,
        delta=result.delta,
        average=result.average,
        direction=result.direction,
    )


def _require_member(services: Services, member_id: str):
    member = services.repository.get_member_context(member_id)
    if member is None:
        raise MemberNotFoundError(f"Unknown member: {member_id}")
    return member


def _trajectory_service(services: Services) -> MemberTrajectoryService:
    """The container's shared service, or an equivalent built from its ontology.

    The fallback exists so a hand-assembled ``Services`` (tests, scripts) still
    works. It reads the same ontology and the same analytics, so the result is
    identical either way - this is a construction convenience, not a second
    implementation.
    """
    return services.trajectory or MemberTrajectoryService(services.ontology)


# --- tool 1 ------------------------------------------------------------------


def get_member_context(services: Services, member_id: str) -> MemberContextView:
    """Compact member view assembled from the member graph and analytics."""
    member = _require_member(services, member_id)

    panel = member.labs.blood_panel
    dexa = member.labs.dexa_scan
    churn = member.coach_brief.churn_risk

    return MemberContextView(
        member_id=member.profile.id,
        name=member.profile.name,
        age=member.profile.age,
        sex=member.profile.sex,
        tier=member.profile.tier,
        member_since=member.profile.member_since,
        goals=[
            GoalView(id=g.id, text=g.text, priority=g.priority, target_date=g.target_date)
            for g in sorted(member.goals, key=lambda g: g.priority)
        ],
        preferences=PreferencesView(
            preferred_session_minutes=member.preferences.preferred_session_minutes,
            training_days_per_week=member.preferences.training_days_per_week,
            preferred_days=list(member.preferences.preferred_days),
            dislikes=list(member.preferences.dislikes),
            notes=member.preferences.notes,
        ),
        injuries=[
            InjuryView(
                id=i.id,
                region=i.region,
                joint=i.joint,
                status=i.status,
                severity=i.severity,
                since=i.since,
                notes=i.notes,
                clinical_hint=i.snomedct_hint,
            )
            for i in member.injuries
        ],
        equipment_available=list(member.equipment_available),
        adherence=_trend(analytics.adherence_trend(member)),
        sleep=_trend(analytics.sleep_trend(member)),
        trajectory=_trajectory_service(services).analyze(member),
        biomarkers=BiomarkerView(
            resting_hr_bpm=member.biomarkers.resting_hr_bpm,
            hrv_ms=member.biomarkers.hrv_ms,
            body_fat_pct=dexa.body_fat_pct if dexa else None,
            ldl_mg_dl=panel.ldl_mg_dl if panel else None,
            hdl_mg_dl=panel.hdl_mg_dl if panel else None,
            vitamin_d_ng_ml=panel.vitamin_d_ng_ml if panel else None,
            panel_date=panel.date if panel else None,
            dexa_date=dexa.date if dexa else None,
        ),
        coach_brief=CoachBriefView(
            generated_for=member.coach_brief.generated_for,
            morning_tasks=[t.text for t in member.coach_brief.morning_tasks],
        ),
        churn=ChurnView(
            level=churn.level if churn else None,
            reasons=list(churn.reasons) if churn else [],
        ),
        sessions_recorded=len(member.workout_history),
    )


# --- tool 2 ------------------------------------------------------------------


def resolve_coach_concepts(
    services: Services, text: str, duration_minutes: int = 45
) -> ResolveConceptsResult:
    """Resolve coach free text to canonical concepts.

    Routed through ``parse_intent`` rather than calling ``resolver.resolve``
    directly, because that is what the workout pipeline does: it performs
    clause-aware span extraction and then hands each span to the resolver. Using
    the same entry point guarantees the concepts reported here are exactly the
    ones the safety engine would receive for the same text - a tool that
    disagreed with the pipeline would be worse than no tool.

    Resolver behaviour is untouched: exact -> alias -> fuzzy -> lexical vector,
    each with its own acceptance threshold.
    """
    _, resolved = parse_intent(text, duration_minutes, services.resolver)
    views = [ConceptView.of(c) for c in resolved]
    return ResolveConceptsResult(
        text=text,
        concepts=[v for v in views if v.resolved],
        unresolved=[v for v in views if not v.resolved],
    )


# --- tool 7 ------------------------------------------------------------------


def _candidate_view(candidate, decision: SafetyDecision | None) -> CandidateView:
    exercise = candidate.exercise
    return CandidateView(
        exercise_id=exercise.id,
        name=exercise.name,
        score=round(candidate.score, 2),
        status=decision.status if decision else "allowed",
        equipment_required=list(exercise.equipment_required),
        movement_patterns=list(exercise.movement_patterns),
        muscle_groups=list(exercise.muscle_groups),
        reasons=list(candidate.rank_reasons)
        + (decision.reason_messages() if decision else []),
    )


def _baseline_context(services: Services, member, prompt: str = "", duration: int = 45):
    """SafetyContext for a member, optionally narrowed by a coach prompt.

    An empty prompt yields the member's standing constraints - recorded injuries
    and owned equipment - which is the correct baseline for "is X safe for her?"
    with no further qualification.
    """
    intent, resolved = parse_intent(prompt or "", duration, services.resolver)
    return services.engine.build_context(member, intent, resolved), intent, resolved


def _injury_evidence(context) -> list[InjuryEvidenceView]:
    return [
        InjuryEvidenceView(
            injury_name=injury["injury_name"],
            condition_label=injury.get("condition_label"),
            severity=injury.get("severity"),
            status=injury.get("status"),
            body_side=injury.get("body_side"),
            root_region=injury.get("root_region_label") or injury.get("root_region"),
            affected_regions=sorted(injury.get("closure") or []),
            contraindicated_patterns=list(injury.get("contraindicated_patterns") or []),
        )
        for injury in context.injuries
    ]


def _reason_views(decision: SafetyDecision) -> list[SafetyReasonView]:
    return [
        SafetyReasonView(
            rule_id=reason.rule_id,
            message=reason.message,
            evidence=[p.render() for p in reason.graph_paths],
        )
        for reason in decision.reasons
    ]


# --- tool 3 ------------------------------------------------------------------

#: Only metrics that genuinely exist in the member graph. Adding a key here
#: without a backing analytics function would let a model ask for data we do not
#: have and receive a confident-looking empty answer.
SUPPORTED_METRICS: dict[str, tuple[str, str | None]] = {
    "adherence": ("adherence_trend", "%"),
    "sleep": ("sleep_trend", "hours"),
    "weight": ("weight_trend", "kg"),
}

#: The analytics layer says "flat"; the MCP contract says "stable". This is a
#: vocabulary mapping at the boundary, not a recomputation.
_DIRECTION_MAP = {"flat": "stable", "insufficient_data": "insufficient_data"}


class UnsupportedMetricError(ValueError):
    """Raised for a metric the member graph does not carry."""


def get_member_metric_trend(
    services: Services,
    member_id: str,
    metric: str,
    window: int | None = None,
) -> MetricTrendResult:
    """Deterministic trend for one member metric.

    Every number here is computed by ``copilot.analytics`` in Python. The model
    receives finished arithmetic and is expected to phrase it, not redo it.
    """
    member = _require_member(services, member_id)

    key = (metric or "").strip().lower()
    if key not in SUPPORTED_METRICS:
        raise UnsupportedMetricError(
            f"Unsupported metric {metric!r}. "
            f"Supported: {', '.join(sorted(SUPPORTED_METRICS))}."
        )

    function_name, unit = SUPPORTED_METRICS[key]
    result = getattr(analytics, function_name)(member)

    labels = list(result.labels)
    values = list(result.values)
    if window is not None and window > 0:
        labels, values = labels[-window:], values[-window:]

    observations = [
        ObservationView(label=label, value=value)
        for label, value in zip(labels, values, strict=False)
    ]

    # Fewer than two observations cannot express a direction, regardless of what
    # the underlying analytics defaulted to.
    if len(values) < 2:
        return MetricTrendResult(
            member_id=member.profile.id,
            metric=key,
            observations=observations,
            count=len(values),
            first_value=values[0] if values else None,
            latest_value=values[-1] if values else None,
            direction="insufficient_data",
            unit=unit,
            trajectory=_trajectory_service(services).analyze(member),
        )

    first, latest = values[0], values[-1]
    # When a window was applied the cached delta no longer describes the slice,
    # so recompute over exactly what is being reported.
    absolute_delta = round(latest - first, 2)
    if window is not None and window > 0:
        direction = _DIRECTION_MAP.get(
            analytics._direction(absolute_delta, flat_band=_flat_band(key)),
            analytics._direction(absolute_delta, flat_band=_flat_band(key)),
        )
    else:
        absolute_delta = result.delta if result.delta is not None else absolute_delta
        direction = _DIRECTION_MAP.get(result.direction, result.direction)

    return MetricTrendResult(
        member_id=member.profile.id,
        metric=key,
        observations=observations,
        count=len(values),
        first_value=first,
        latest_value=latest,
        average_value=round(sum(values) / len(values), 2),
        absolute_delta=absolute_delta,
        # Undefined against a zero baseline - reported as null rather than 0.
        percent_delta=(
            round((latest - first) / abs(first) * 100, 1) if first else None
        ),
        direction=direction,
        unit=unit,
        trajectory=_trajectory_service(services).analyze(member),
    )


def _flat_band(metric: str) -> float:
    """The same flat bands ``copilot.analytics`` uses, so windows agree with it."""
    return {"adherence": 5.0, "sleep": 0.3, "weight": 0.3}[metric]


# --- tool 4 ------------------------------------------------------------------


def _require_exercise(services: Services, exercise_id: str):
    exercise = services.repository.get_exercise(exercise_id)
    if exercise is None:
        raise ExerciseNotFoundError(f"Unknown exercise: {exercise_id}")
    return exercise


def evaluate_exercise_safety(
    services: Services,
    member_id: str,
    exercise_id: str,
    prompt: str = "",
) -> ExerciseSafetyResult:
    """Authoritative single-exercise safety verdict.

    Delegates wholly to ``SafetyEngine.evaluate``. For identical inputs this
    returns the identical decision a direct engine call would - there is no
    second rule set here, and adding one would break the single-source guarantee
    the whole design rests on.
    """
    member = _require_member(services, member_id)
    exercise = _require_exercise(services, exercise_id)
    context, _, _ = _baseline_context(services, member, prompt)

    decision = services.engine.evaluate(exercise, context)

    required = services.repository.exercise_required_equipment(exercise.id)
    available = context.available_equipment
    regions = services.repository.exercise_stressed_regions(exercise.id)

    return ExerciseSafetyResult(
        member_id=member.profile.id,
        exercise_id=exercise.id,
        exercise_name=exercise.name,
        status=decision.status,
        is_excluded=decision.is_excluded,
        score_adjustment=decision.score_adjustment,
        reasons=_reason_views(decision),
        rule_ids=[r.rule_id for r in decision.reasons],
        injury_evidence=_injury_evidence(context),
        required_equipment=list(required),
        member_available_equipment=sorted(available),
        missing_equipment=sorted(set(required) - set(available)),
        movement_patterns=services.repository.exercise_patterns(exercise.id),
        stressed_regions=list(regions),
        graph_evidence=[p.render() for p in decision.graph_paths],
        decision_source=decision.decision_source,
        graph_backend=services.backend,
    )


# --- tool 5 ------------------------------------------------------------------


def get_exercise_provenance(
    services: Services,
    member_id: str,
    exercise_id: str,
    prompt: str = "",
) -> ExerciseProvenanceResult:
    """Explain a decision using only evidence the engine actually produced.

    Graph paths are serialised straight off the ``SafetyDecision`` the engine
    returned. Nothing is reconstructed from reason strings, and no relationship
    is invented. Where a rule is a set operation rather than a traversal -
    missing equipment is the common case - ``has_graph_path`` is False and the
    real basis is stated instead of a plausible-looking fake path.
    """
    member = _require_member(services, member_id)
    exercise = _require_exercise(services, exercise_id)
    context, _, _ = _baseline_context(services, member, prompt)

    decision = services.engine.evaluate(exercise, context)
    paths = decision.graph_paths

    graph_paths = [
        GraphPathView(
            nodes=list(p.nodes),
            relationships=list(p.edges),
            node_kinds=list(p.node_kinds),
            directions=[p.direction_at(i) for i in range(len(p.edges))],
            facts=list(p.facts),
            rendered=p.render(),
        )
        for p in paths
    ]

    required = services.repository.exercise_required_equipment(exercise.id)
    available = context.available_equipment
    missing = sorted(set(required) - set(available))

    equipment_evidence: list[str] = []
    if required:
        equipment_evidence.append(f"Requires: {', '.join(required)}.")
        equipment_evidence.append(
            f"Missing for this member: {', '.join(missing)}." if missing
            else "All required equipment is available to the member."
        )
    else:
        equipment_evidence.append("Bodyweight - no equipment required.")

    ontology = services.ontology
    anatomy_evidence: list[str] = []
    for region in services.repository.exercise_stressed_regions(exercise.id):
        concept = ontology.anatomy.get(region)
        label = concept.label if concept else region
        ancestors = [
            ontology.anatomy[a].label
            for a in ontology.ancestors_of(region)
            if a in ontology.anatomy
        ]
        anatomy_evidence.append(
            f"Stresses {label}" + (f" (PART_OF -> {' -> '.join(ancestors)})" if ancestors else "")
        )

    note = None
    if not graph_paths:
        note = (
            "No graph traversal underlies this decision. "
            + (
                "It rests on a deterministic set operation over the member's "
                "equipment, which is an absence rather than a relationship."
                if decision.reasons
                else "The exercise cleared every rule, so no constraint path exists."
            )
        )

    return ExerciseProvenanceResult(
        member_id=member.profile.id,
        exercise_id=exercise.id,
        exercise_name=exercise.name,
        status=decision.status,
        reasons=_reason_views(decision),
        rule_ids=[r.rule_id for r in decision.reasons],
        member_evidence=_member_facts_for(context),
        exercise_evidence=[
            f"Movement patterns: {', '.join(services.repository.exercise_patterns(exercise.id)) or 'none recorded'}.",
            f"Muscle groups: {', '.join(exercise.muscle_groups) or 'none recorded'}.",
        ],
        graph_paths=graph_paths,
        has_graph_path=bool(graph_paths),
        evidence_note=note,
        equipment_evidence=equipment_evidence,
        injury_evidence=_injury_evidence(context),
        anatomy_evidence=anatomy_evidence,
        graph_backend=services.backend,
    )


# --- tool 6 ------------------------------------------------------------------


def _bucket_phrases(
    services: Services,
    intent: WorkoutIntent,
    resolved: list,
    phrases: list[str] | None,
    bucket: list[str],
) -> None:
    """Resolve each phrase and file it under the intent bucket it belongs to.

    The engine matches exclusions and equipment by ``source_text``, so the
    resolved concept and the bucket entry must carry the identical string.
    """
    for phrase in phrases or []:
        text = (phrase or "").strip()
        if not text:
            continue
        concept = services.resolver.resolve(text)
        resolved.append(concept)
        bucket.append(text)


def get_safe_exercise_candidates(
    services: Services,
    member_id: str,
    focus: list[str] | None = None,
    equipment: list[str] | None = None,
    exclusions: list[str] | None = None,
    injury_mentions: list[str] | None = None,
    preferences: list[str] | None = None,
    limit: int = 20,
    equipment_is_restrictive: bool = True,
) -> SafeCandidatesResult:
    """The graph-approved candidate set for a member under optional constraints.

    Constraints arrive structured rather than as prose, but they are resolved by
    the same ``ConceptResolver`` and evaluated by the same ``SafetyEngine``, so
    the result is the same authority the workout pipeline would apply.

    ``limit`` is applied *after* safety filtering and ranking. Applying it
    earlier could truncate the catalog before exclusions ran and let an unsafe
    exercise survive by position.
    """
    member = _require_member(services, member_id)

    intent = WorkoutIntent(duration_minutes=45)
    resolved: list = []
    _bucket_phrases(services, intent, resolved, focus, intent.requested_focus)
    _bucket_phrases(services, intent, resolved, equipment, intent.equipment_mentions)
    _bucket_phrases(services, intent, resolved, exclusions, intent.explicit_exclusions)
    _bucket_phrases(services, intent, resolved, injury_mentions, intent.injury_mentions)
    intent.preferences = list(preferences or [])
    intent.equipment_is_restrictive = bool(equipment) and equipment_is_restrictive

    context = services.engine.build_context(member, intent, resolved)
    decisions = {d.exercise_id: d for d in services.engine.evaluate_all(context)}
    candidates = rank_candidates(
        services.repository.list_exercises(),
        decisions,
        member,
        intent,
        resolved,
        services.ontology,
    )

    eligible: list[CandidateView] = []
    downranked: list[CandidateView] = []
    for candidate in candidates:
        decision = decisions.get(candidate.exercise.id)
        view = _candidate_view(candidate, decision)
        (downranked if view.status == "downranked" else eligible).append(view)

    capped = max(1, int(limit)) if limit else len(eligible)
    views = [ConceptView.of(c) for c in resolved]

    return SafeCandidatesResult(
        member_id=member.profile.id,
        resolved_concepts=[v for v in views if v.resolved],
        unresolved_concepts=[v for v in views if not v.resolved],
        applied_constraints=IntentView(
            duration_minutes=intent.duration_minutes,
            requested_focus=list(intent.requested_focus),
            explicit_exclusions=list(intent.explicit_exclusions),
            equipment_mentions=list(intent.equipment_mentions),
            injury_mentions=list(intent.injury_mentions),
            equipment_is_restrictive=intent.equipment_is_restrictive,
        ),
        catalog_count=len(decisions),
        excluded_count=sum(1 for d in decisions.values() if d.is_excluded),
        downranked_count=sum(1 for d in decisions.values() if d.status == "downranked"),
        eligible_count=len(eligible),
        returned_count=len(eligible[:capped]),
        limit_applied=capped,
        eligible_candidates=eligible[:capped],
        downranked_candidates=downranked[:capped],
        graph_backend=services.backend,
    )


def _member_facts_for(context) -> list[str]:
    """Member evidence, borrowed from the provenance builder rather than restated."""
    from app.provenance.builder import _member_facts

    return _member_facts(context)


# --- tool 7 ------------------------------------------------------------------


def evaluate_workout_request(
    services: Services,
    member_id: str,
    prompt: str,
    duration_minutes: int = 45,
) -> WorkoutRequestEvaluation:
    """Deterministic, read-only evaluation of a workout request.

    Runs the authoritative pre-generation half of the workout pipeline and then
    stops:

        prompt -> intent parsing -> concept resolution -> member context
               -> graph safety evaluation -> ranking -> provenance / reasoning

    No LLM is invoked and no plan is composed. The result answers "would this be
    safe", "what would be excluded and why", and "what is eligible" from the
    same decisions the generator would have been constrained by.
    """
    member = _require_member(services, member_id)
    engine = services.engine

    intent, resolved = parse_intent(prompt, duration_minutes, services.resolver)
    context = engine.build_context(member, intent, resolved)
    decisions = {d.exercise_id: d for d in engine.evaluate_all(context)}
    candidates = rank_candidates(
        services.repository.list_exercises(),
        decisions,
        member,
        intent,
        resolved,
        services.ontology,
    )

    bundle = build_pre_generation_provenance(decisions, candidates, context)
    reasoning = build_graph_reasoning(
        trace_id=uuid.uuid4().hex[:12],
        graph_backend=services.backend,
        decisions=decisions,
        candidates=candidates,
        resolved_concepts=resolved,
        member_facts=bundle.member_facts,
        in_plan_count=0,  # nothing is composed by this tool, by design
        ontology=services.ontology,
    )

    eligible: list[CandidateView] = []
    downranked: list[CandidateView] = []
    for candidate in candidates:
        decision = decisions.get(candidate.exercise.id)
        view = _candidate_view(candidate, decision)
        (downranked if view.status == "downranked" else eligible).append(view)

    excluded = [
        ExcludedView(
            exercise_id=decision.exercise_id,
            name=decision.exercise_name,
            rule_ids=[r.rule_id for r in decision.reasons],
            reasons=decision.reason_messages(),
            evidence=[p.render() for p in decision.graph_paths],
        )
        for decision in decisions.values()
        if decision.is_excluded
    ]
    excluded.sort(key=lambda e: e.name)

    views = [ConceptView.of(c) for c in resolved]
    return WorkoutRequestEvaluation(
        member_id=member.profile.id,
        prompt=prompt,
        intent=IntentView(
            duration_minutes=intent.duration_minutes,
            requested_focus=list(intent.requested_focus),
            explicit_exclusions=list(intent.explicit_exclusions),
            equipment_mentions=list(intent.equipment_mentions),
            injury_mentions=list(intent.injury_mentions),
            equipment_is_restrictive=intent.equipment_is_restrictive,
        ),
        resolved_concepts=[v for v in views if v.resolved],
        unresolved_concepts=[v for v in views if not v.resolved],
        member_evidence=list(bundle.member_facts),
        safety_summary=SafetySummaryView(
            catalog_count=bundle.counts.get("catalog_total", 0),
            excluded_count=bundle.counts.get("excluded", 0),
            downranked_count=bundle.counts.get("downranked", 0),
            eligible_count=bundle.counts.get("eligible", 0),
        ),
        eligible_candidates=eligible[:MAX_CANDIDATES],
        downranked_candidates=downranked[:MAX_CANDIDATES],
        excluded=excluded[:MAX_EXCLUDED],
        graph_reasoning=reasoning,
        provenance=[
            ProvenanceItemView(
                exercise_id=item.exercise_id,
                exercise=item.exercise,
                decision=item.decision,
                rule_ids=list(item.rule_ids),
                reasons=list(item.reasons),
                evidence=[e.rendered for e in item.evidence],
            )
            for item in (bundle.included + bundle.filtered)[:MAX_CANDIDATES]
        ],
        graph_backend=services.backend,
    )
