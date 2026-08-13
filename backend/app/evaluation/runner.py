"""Executes the evaluation corpus and computes measured metrics.

Design notes worth defending:

* **Every case runs the real code path.** Safety cases drive the real engine;
  validation cases drive the real LangGraph workflow with an adversarial model;
  MCP cases call the real tools. A harness that re-implemented the logic would
  measure the harness.
* **Metrics carry numerator and denominator.** A displayed percentage is always
  derived from a ratio the caller can check, never asserted on its own.
* **Invariants are computed from case outcomes**, so a green tick in the
  dashboard always traces back to executed evidence.
* **Nothing is averaged across categories.** They measure different things, and
  one blended score would let a safety escape hide behind a good resolver run.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from statistics import median
from typing import Any

from app.agents.adjustment import adjust_workout
from app.agents.intent import parse_intent
from app.agents.workout_graph import WorkoutWorkflow
from app.domain.evaluation import (
    CaseResult,
    EvaluationRun,
    GraphEvidence,
    Invariant,
    LatencySummary,
    Metric,
)
from app.domain.workout import LLMWorkoutDraft, WorkoutRequest
from app.evaluation.adversarial import AdversarialLLM, adversarial_draft
from app.evaluation.cases import ALL_CASES, BASE_ADJUSTMENT_PROMPT, EvalCase
from app.llm.stub import StubLLMClient
from app.member.trajectory import MemberTrajectoryService
from app.ontology.loader import ONTOLOGY_PATH, load_ontology
from app.provenance.graph_trace import build_graph_reasoning
from app.resolution.resolver import ConceptResolver
from app.safety.policies import MAX_LONGITUDINAL_ADJUSTMENT, SMALLEST_SAFETY_PENALTY
from app.safety.ranking import rank_candidates
from app.safety.validator import UnsafePlanError, validate_and_repair

MEMBER_ID = "mbr_01HX9JORDAN"


class CaseFailure(Exception):
    """Raised by a case body to report a deterministic mismatch."""

    def __init__(self, actual: str) -> None:
        super().__init__(actual)
        self.actual = actual


class EvaluationRunner:
    def __init__(self, services: Any) -> None:
        self._services = services
        self._member = services.repository.get_member_context(MEMBER_ID)
        if self._member is None:  # pragma: no cover - dataset guarantees a member
            raise RuntimeError(f"Evaluation member {MEMBER_ID} is missing")
        self._trajectory_service = services.trajectory or MemberTrajectoryService(
            services.ontology
        )

    # --- entry point ------------------------------------------------------

    async def run(self, cases: list[EvalCase] | None = None) -> EvaluationRun:
        selected = cases if cases is not None else ALL_CASES
        started = time.perf_counter()
        results: list[CaseResult] = []

        for case in selected:
            results.append(await self._run_case(case))

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        latencies = sorted(r.latency_ms for r in results)

        run = EvaluationRun(
            run_id=f"eval-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}",
            started_at=datetime.now(UTC).isoformat(timespec="seconds"),
            duration_ms=duration_ms,
            graph_backend=self._services.backend,
            llm_provider=getattr(self._services.llm, "name", "unknown"),
            total_cases=len(results),
            passed_cases=sum(1 for r in results if r.passed),
            failed_cases=sum(1 for r in results if not r.passed),
            unsafe_escapes=sum(1 for r in results if r.unsafe_escape),
            results=results,
            latency=_latency(latencies, duration_ms),
        )
        run.metrics = _metrics(results)
        run.invariants = _invariants(results)
        return run

    async def _run_case(self, case: EvalCase) -> CaseResult:
        started = time.perf_counter()
        evidence: list[GraphEvidence] = []
        notes: list[str] = []
        unsafe_escape = False

        try:
            handler = getattr(self, f"_case_{case.kind}")
        except AttributeError:  # pragma: no cover - guarded by a test
            return self._result(case, "no handler for this case kind", False, started)

        try:
            actual = await _maybe_await(handler(case, evidence, notes))
            passed = True
        except CaseFailure as failure:
            actual, passed = failure.actual, False
            unsafe_escape = case.category == "validation"
        except Exception as exc:  # noqa: BLE001 - an error is a failed case
            actual, passed = f"{type(exc).__name__}: {exc}", False
            unsafe_escape = case.category == "validation"

        return self._result(
            case, actual, passed, started, evidence=evidence, notes=notes,
            unsafe_escape=unsafe_escape,
        )

    @staticmethod
    def _result(
        case: EvalCase,
        actual: str,
        passed: bool,
        started: float,
        *,
        evidence: list[GraphEvidence] | None = None,
        notes: list[str] | None = None,
        unsafe_escape: bool = False,
    ) -> CaseResult:
        return CaseResult(
            case_id=case.id,
            category=case.category,
            name=case.name,
            input_summary=case.input_summary,
            expected=case.expectation,
            actual=actual,
            passed=passed,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            evidence=evidence or [],
            notes=notes or [],
            unsafe_escape=unsafe_escape,
        )

    # --- shared helpers ---------------------------------------------------

    def _evaluate(self, prompt: str, duration: int = 45):
        """Run the deterministic half: intent -> safety -> ranking."""
        intent, resolved = parse_intent(prompt, duration, self._services.resolver)
        context = self._services.engine.build_context(self._member, intent, resolved)
        decisions = {d.exercise_id: d for d in self._services.engine.evaluate_all(context)}
        candidates = rank_candidates(
            self._services.repository.list_exercises(),
            decisions,
            self._member,
            intent,
            resolved,
            self._services.ontology,
            trajectory=self._trajectory_service.analyze(self._member),
        )
        return intent, resolved, decisions, candidates

    def _by_name(self, name: str) -> str:
        for exercise in self._services.repository.list_exercises():
            if exercise.name == name:
                return exercise.id
        raise CaseFailure(f"catalog has no exercise named {name!r}")

    def _capture(self, decision, evidence: list[GraphEvidence]) -> None:
        """Attach the decision's evidence, including its real traversals.

        Built through the same projection the coach UI uses, so the dashboard
        renders identical paths rather than a parallel representation.
        """
        reasoning = build_graph_reasoning(
            trace_id="eval",
            graph_backend=self._services.backend,
            decisions={decision.exercise_id: decision},
            candidates=[],
            resolved_concepts=[],
            member_facts=[],
            in_plan_count=0,
            ontology=self._services.ontology,
        )
        evidence.append(
            GraphEvidence(
                exercise=decision.exercise_name,
                decision=decision.status,
                rule_ids=[r.rule_id for r in decision.reasons],
                rendered_paths=[p.render() for p in decision.graph_paths],
                facts=[f for p in decision.graph_paths for f in p.facts],
                traversals=reasoning.traversals,
            )
        )

    def _workflow(self, llm=None) -> WorkoutWorkflow:
        return WorkoutWorkflow(
            self._services.repository,
            self._services.ontology,
            self._services.resolver,
            self._services.engine,
            llm or StubLLMClient(),
            self._trajectory_service,
        )

    # --- concept resolution ----------------------------------------------

    def _case_resolve(self, case, evidence, notes) -> str:  # noqa: ARG002
        params = case.params
        result = self._services.resolver.resolve(params["text"])
        expected_id = params.get("canonical_id")

        if expected_id is None:
            if result.is_resolved:
                raise CaseFailure(
                    f"resolved to {result.canonical_id} ({result.method}, "
                    f"{result.confidence:.2f}) - should have stayed unresolved"
                )
            return f"unresolved (nearest: {', '.join(result.alternatives) or 'none'})"

        if result.canonical_id != expected_id:
            raise CaseFailure(f"resolved to {result.canonical_id or 'unresolved'}")
        if params.get("method") and result.method != params["method"]:
            raise CaseFailure(
                f"{result.canonical_id} but via {result.method}, not {params['method']}"
            )
        if result.confidence < params.get("min_confidence", 0.0):
            raise CaseFailure(f"confidence {result.confidence:.2f} below threshold")
        return f"{result.canonical_id} via {result.method} ({result.confidence:.2f})"

    def _case_resolve_with_thresholds(self, case, evidence, notes) -> str:  # noqa: ARG002
        params = case.params
        resolver = ConceptResolver.from_ontology(
            self._services.ontology,
            fuzzy_threshold=params["fuzzy_threshold"],
            embedding_threshold=params["embedding_threshold"],
        )
        result = resolver.resolve(params["text"])
        expected_id = params.get("canonical_id")

        if expected_id is None:
            if result.is_resolved:
                raise CaseFailure(f"resolved to {result.canonical_id} ({result.method})")
            return "unresolved as expected"
        if result.canonical_id != expected_id:
            raise CaseFailure(f"resolved to {result.canonical_id or 'unresolved'}")
        if params.get("method") and result.method != params["method"]:
            raise CaseFailure(f"via {result.method}, not {params['method']}")
        return f"{result.canonical_id} via {result.method} ({result.confidence:.2f})"

    def _case_intent_resolves(self, case, evidence, notes) -> str:  # noqa: ARG002
        _, resolved = parse_intent(
            case.params["prompt"], 45, self._services.resolver
        )
        for concept in resolved:
            for prefix in case.params.get("forbidden_prefixes", []):
                if (concept.canonical_id or "").startswith(prefix):
                    raise CaseFailure(
                        f"'{concept.source_text}' resolved to {concept.canonical_id}"
                    )
        return f"{len(resolved)} concept(s), none forbidden"

    # --- safety -----------------------------------------------------------

    def _case_safety(self, case, evidence, notes) -> str:
        params = case.params
        _, _, decisions, candidates = self._evaluate(params["prompt"])
        parts: list[str] = []

        for name in params.get("excluded", []):
            decision = decisions[self._by_name(name)]
            self._capture(decision, evidence)
            if not decision.is_excluded:
                raise CaseFailure(f"{name} is {decision.status}, expected excluded")
            for rule in params.get("rules", []):
                if rule not in {r.rule_id for r in decision.reasons}:
                    raise CaseFailure(f"{name} excluded but not by {rule}")
            if params.get("require_evidence") and not decision.graph_paths:
                raise CaseFailure(f"{name} excluded with no graph evidence")
            parts.append(f"{name} EXCLUDED")

        for name in params.get("downranked", []):
            decision = decisions[self._by_name(name)]
            self._capture(decision, evidence)
            if decision.status != "downranked":
                raise CaseFailure(f"{name} is {decision.status}, expected downranked")
            for rule in params.get("rules", []):
                if rule not in {r.rule_id for r in decision.reasons}:
                    raise CaseFailure(f"{name} down-ranked but not by {rule}")
            if params.get("require_evidence") and not decision.graph_paths:
                raise CaseFailure(f"{name} down-ranked with no graph evidence")
            parts.append(f"{name} DOWN-RANKED")

        fired = {r.rule_id for d in decisions.values() for r in d.reasons}
        for rule in params.get("rules_present", []):
            if rule not in fired:
                raise CaseFailure(f"{rule} never fired across the catalog")
            parts.append(f"{rule} fired")

        never = params.get("rule_never_excludes")
        if never:
            offenders = [
                d.exercise_name
                for d in decisions.values()
                if d.is_excluded and {r.rule_id for r in d.reasons} == {never}
            ]
            if offenders:
                raise CaseFailure(f"{never} excluded {', '.join(offenders[:3])}")
            parts.append(f"{never} never excluded anything")

        minimum = params.get("min_eligible")
        if minimum is not None:
            if len(candidates) < minimum:
                raise CaseFailure(f"only {len(candidates)} eligible, expected >= {minimum}")
            parts.append(f"{len(candidates)} eligible")

        return "; ".join(parts) or "no assertions"

    def _case_anatomy_closure(self, case, evidence, notes) -> str:  # noqa: ARG002
        closure = self._services.ontology.anatomical_closure(case.params["region"])
        expected = set(case.params["closure"])
        if closure != expected:
            raise CaseFailure(f"closure = {sorted(closure)}")
        return f"closure = {sorted(closure)}"

    def _case_counts(self, case, evidence, notes) -> str:  # noqa: ARG002
        params = case.params
        _, _, decisions, candidates = self._evaluate(params["prompt"])
        actual = {
            "eligible": len(candidates),
            "excluded": sum(1 for d in decisions.values() if d.is_excluded),
            "downranked": sum(1 for d in decisions.values() if d.status == "downranked"),
        }
        expected = {k: params[k] for k in ("eligible", "excluded", "downranked")}
        if actual != expected:
            raise CaseFailure(str(actual))
        return str(actual)

    def _case_evidence_shape(self, case, evidence, notes) -> str:  # noqa: ARG002
        """Absence of equipment is a set difference, so it must be a *fact*.

        The one real traversal is the exercise's own REQUIRES edge. Anything
        else - a "DOES_NOT_HAVE" edge, say - would be a relationship the graph
        does not contain, rendered as if it did.
        """
        params = case.params
        allowed = set(params.get("allowed_relationships", []))
        _, _, decisions, _ = self._evaluate(params["prompt"])

        for decision in decisions.values():
            for reason in decision.reasons:
                if reason.rule_id != params["rule"]:
                    continue
                for path in reason.graph_paths:
                    if params.get("require_facts") and not path.facts:
                        raise CaseFailure(f"{params['rule']} evidence carries no facts")
                    invented = set(path.edges) - allowed
                    if invented:
                        raise CaseFailure(f"invented relationship(s): {sorted(invented)}")
                self._capture(decision, evidence)
                return (
                    f"{params['rule']} evidence: facts present, "
                    f"only {', '.join(sorted(allowed))} traversed"
                )
        raise CaseFailure(f"{params['rule']} never fired")

    def _case_provenance_coverage(self, case, evidence, notes) -> str:  # noqa: ARG002
        _, _, decisions, _ = self._evaluate(case.params["prompt"])
        flagged = [d for d in decisions.values() if d.status != "allowed"]
        uncovered = [
            d.exercise_name
            for d in flagged
            if not d.reasons or not any(r.graph_paths for r in d.reasons)
        ]
        if uncovered:
            raise CaseFailure(f"{len(uncovered)} without evidence: {uncovered[:3]}")
        return f"{len(flagged)}/{len(flagged)} flagged decisions carry evidence"

    def _case_ontology_neutrality(self, case, evidence, notes) -> str:  # noqa: ARG002
        """Stripping every published mapping must not move a single decision."""
        stripped = load_ontology(ONTOLOGY_PATH)
        for concept in stripped.anatomy.values():
            object.__setattr__(concept, "grounding", None)
        for condition in stripped.injury_conditions.values():
            object.__setattr__(condition, "grounding", None)
        for muscle in stripped.muscles.values():
            object.__setattr__(muscle, "grounding", None)

        from app.graph.memory_repository import InMemoryGraphRepository
        from app.safety.engine import SafetyEngine

        settings = self._services.settings
        repository = InMemoryGraphRepository.from_files(
            settings.exercises_path, settings.member_context_path, ontology=stripped
        )
        resolver = ConceptResolver.from_ontology(stripped)
        engine = SafetyEngine(repository, stripped)
        member = repository.get_member_context(MEMBER_ID)

        intent, resolved = parse_intent(case.params["prompt"], 45, resolver)
        context = engine.build_context(member, intent, resolved)
        ungrounded = {d.exercise_id: d.status for d in engine.evaluate_all(context)}

        _, _, grounded, _ = self._evaluate(case.params["prompt"])
        if ungrounded != {eid: d.status for eid, d in grounded.items()}:
            raise CaseFailure("decisions changed when ontology grounding was removed")
        return f"{len(ungrounded)}/{len(ungrounded)} decisions identical without grounding"

    # --- equipment --------------------------------------------------------

    def _case_equipment(self, case, evidence, notes) -> str:  # noqa: ARG002
        params = case.params
        _, _, _, candidates = self._evaluate(params["prompt"])
        offenders = [
            f"{c.exercise.name} needs {item}"
            for c in candidates
            for item in self._services.repository.exercise_required_equipment(
                c.exercise.id
            )
            if item in params["forbidden"]
        ]
        if offenders:
            raise CaseFailure(f"{len(offenders)} escaped: {offenders[:2]}")
        return f"{len(candidates)} eligible, none require {', '.join(params['forbidden'])}"

    def _case_equipment_available(self, case, evidence, notes) -> str:  # noqa: ARG002
        params = case.params
        intent, resolved = parse_intent(params["prompt"], 45, self._services.resolver)
        context = self._services.engine.build_context(self._member, intent, resolved)
        available = context.available_equipment

        for item in params.get("available", []):
            if item not in available:
                raise CaseFailure(f"{item} was dropped from the available set")
        for item in params.get("unavailable", []):
            if item in available:
                raise CaseFailure(f"{item} leaked into the available set")
        return f"available = {', '.join(sorted(available))}"

    def _case_equipment_bodyweight(self, case, evidence, notes) -> str:  # noqa: ARG002
        _, _, _, candidates = self._evaluate(case.params["prompt"])
        bodyweight = [
            c
            for c in candidates
            if not self._services.repository.exercise_required_equipment(c.exercise.id)
        ]
        if not bodyweight:
            raise CaseFailure("no bodyweight exercise survived equipment filtering")
        return f"{len(bodyweight)} bodyweight exercises remain eligible"

    # --- explicit exclusions ---------------------------------------------

    def _case_exclusion(self, case, evidence, notes) -> str:
        params = case.params
        _, _, decisions, _ = self._evaluate(params["prompt"])
        for name in params["excluded"]:
            decision = decisions[self._by_name(name)]
            self._capture(decision, evidence)
            if not decision.is_excluded:
                raise CaseFailure(f"{name} is {decision.status}, expected excluded")
            rule = params.get("rule")
            if rule and rule not in {r.rule_id for r in decision.reasons}:
                raise CaseFailure(
                    f"{name} excluded by {[r.rule_id for r in decision.reasons]}, not {rule}"
                )
        return f"{', '.join(params['excluded'])} EXCLUDED"

    def _case_catalog_premise(self, case, evidence, notes) -> str:  # noqa: ARG002
        needle = case.params["substring"].lower()
        hits = [
            e.name
            for e in self._services.repository.list_exercises()
            if needle in e.name.lower()
        ]
        if len(hits) != case.params["expected_count"]:
            raise CaseFailure(f"{len(hits)} matches: {hits[:3]}")
        return f"{len(hits)} exercises contain '{needle}' - exclusion must use the graph"

    def _case_exclusion_scope(self, case, evidence, notes) -> str:  # noqa: ARG002
        params = case.params
        _, _, decisions, candidates = self._evaluate(params["prompt"])
        eligible = {c.exercise.id for c in candidates}
        for name in params["still_eligible"]:
            exercise_id = self._by_name(name)
            if exercise_id not in eligible:
                raise CaseFailure(
                    f"{name} was removed: {decisions[exercise_id].status}"
                )
        return f"{', '.join(params['still_eligible'])} still eligible"

    # --- longitudinal ------------------------------------------------------

    def _case_trajectory(self, case, evidence, notes) -> str:  # noqa: ARG002
        params = case.params
        trajectory = self._trajectory_service.analyze(self._member)
        checks: list[str] = []

        if "adherence_direction" in params:
            if trajectory.adherence.direction != params["adherence_direction"]:
                raise CaseFailure(f"adherence {trajectory.adherence.direction}")
            checks.append(f"adherence {trajectory.adherence.direction}")
        if "adherence_delta" in params:
            if trajectory.adherence.delta != params["adherence_delta"]:
                raise CaseFailure(f"delta {trajectory.adherence.delta}")
            checks.append(f"delta {trajectory.adherence.delta}")
        if "sleep_direction" in params:
            if trajectory.sleep.direction != params["sleep_direction"]:
                raise CaseFailure(f"sleep {trajectory.sleep.direction}")
            checks.append(f"sleep {trajectory.sleep.direction} (avg "
                          f"{trajectory.sleep.average_recent}h)")
        if "load_state" in params:
            if trajectory.training_load.state != params["load_state"]:
                raise CaseFailure(f"load {trajectory.training_load.state}")
            checks.append(
                f"load {trajectory.training_load.state} "
                f"({trajectory.training_load.sessions_per_week}/wk)"
            )
        if "progression" in params:
            if trajectory.progression.state != params["progression"]:
                raise CaseFailure(f"progression {trajectory.progression.state}")
            if params.get("require_rationale") and not trajectory.progression.rationale:
                raise CaseFailure("progression carries no rationale")
            checks.append(f"progression {trajectory.progression.state}")
        return "; ".join(checks)

    def _case_trajectory_variant(self, case, evidence, notes) -> str:  # noqa: ARG002
        from app.domain.member import AdherenceObservation

        params = case.params
        member = self._member.model_copy(deep=True)

        if params["variant"] == "stable":
            member.adherence.weekly_completion_pct = [
                AdherenceObservation(week_of=f"2026-05-{day:02d}", pct=90.0)
                for day in (5, 12, 19, 26)
            ]
            member.preferences.training_days_per_week = 2
        elif params["variant"] == "sparse":
            member.adherence.weekly_completion_pct = [
                AdherenceObservation(week_of="2026-06-02", pct=50.0)
            ]
        elif params["variant"] == "collapsing_adherence":
            member.adherence.weekly_completion_pct = [
                AdherenceObservation(week_of="2026-05-12", pct=100.0),
                AdherenceObservation(week_of="2026-06-02", pct=10.0),
            ]

        trajectory = self._trajectory_service.analyze(member)
        if "progression" in params and trajectory.progression.state != params["progression"]:
            raise CaseFailure(f"progression {trajectory.progression.state}")
        if "injury_state" in params:
            if trajectory.injury_trajectory.state != params["injury_state"]:
                raise CaseFailure(f"injury {trajectory.injury_trajectory.state}")
            if trajectory.injury_trajectory.source != params["injury_source"]:
                raise CaseFailure(f"source {trajectory.injury_trajectory.source}")
        return (
            f"progression {trajectory.progression.state}, "
            f"injury {trajectory.injury_trajectory.state} "
            f"({trajectory.injury_trajectory.source})"
        )

    def _case_longitudinal_ranking(self, case, evidence, notes) -> str:  # noqa: ARG002
        _, _, _, candidates = self._evaluate(case.params["prompt"])
        boosted = [c for c in candidates if c.longitudinal_adjustment > 0]
        if case.params.get("expect_boost") and not boosted:
            raise CaseFailure("no candidate received a familiarity bonus")
        return (
            f"{len(boosted)} boosted, e.g. {boosted[0].exercise.name} "
            f"(+{boosted[0].longitudinal_adjustment:.0f})"
        )

    def _case_longitudinal_precedence(self, case, evidence, notes) -> str:  # noqa: ARG002
        _, _, decisions, candidates = self._evaluate(case.params["prompt"])
        excluded = {eid for eid, d in decisions.items() if d.is_excluded}
        leaked = {c.exercise.id for c in candidates} & excluded
        if leaked:
            raise CaseFailure(f"{len(leaked)} excluded exercise(s) survived ranking")
        return f"{len(excluded)} excluded, 0 survived ranking"

    def _case_longitudinal_bound(self, case, evidence, notes) -> str:  # noqa: ARG002
        if MAX_LONGITUDINAL_ADJUSTMENT >= SMALLEST_SAFETY_PENALTY:
            raise CaseFailure(
                f"bound {MAX_LONGITUDINAL_ADJUSTMENT} >= {SMALLEST_SAFETY_PENALTY}"
            )
        return (
            f"max longitudinal {MAX_LONGITUDINAL_ADJUSTMENT} < "
            f"smallest safety penalty {SMALLEST_SAFETY_PENALTY}"
        )

    # --- adjustment --------------------------------------------------------

    async def _adjust(self, adjustment: str, previous_ids: list[str] | None = None):
        base_state = await self._workflow().run(
            WorkoutRequest(
                member_id=MEMBER_ID, prompt=BASE_ADJUSTMENT_PROMPT, duration_minutes=45
            )
        )
        previous = previous_ids or [
            item.exercise_id
            for section in base_state["generated_workout"].sections
            for item in section.exercises
        ]
        return await adjust_workout(
            services=self._services,
            member_id=MEMBER_ID,
            base_prompt=BASE_ADJUSTMENT_PROMPT,
            adjustment=adjustment,
            base_duration=45,
            previous_exercise_ids=previous,
        )

    async def _case_adjustment(self, case, evidence, notes) -> str:
        params = case.params
        outcome = await self._adjust(params["adjustment"])
        state, diff = outcome["state"], outcome["diff"]
        decisions = state["safety_decisions"]
        plan_ids = [
            item.exercise_id
            for section in state["generated_workout"].sections
            for item in section.exercises
        ]
        checks: list[str] = []

        excluded = {eid for eid, d in decisions.items() if d.is_excluded}
        if set(plan_ids) & excluded:
            raise CaseFailure("the adjusted plan contains an excluded exercise")

        for name in params.get("newly_excluded_names", []):
            decision = decisions[self._by_name(name)]
            self._capture(decision, evidence)
            if not decision.is_excluded:
                raise CaseFailure(f"{name} is {decision.status}, expected excluded")
            checks.append(f"{name} now ineligible")

        for name in params.get("still_excluded_names", []):
            if not decisions[self._by_name(name)].is_excluded:
                raise CaseFailure(f"{name} stopped being excluded")
            checks.append(f"{name} still excluded")

        minimum = params.get("min_newly_excluded")
        if minimum is not None and diff.counts.get("newly_excluded", 0) < minimum:
            raise CaseFailure(f"newly_excluded={diff.counts.get('newly_excluded', 0)}")

        for item in params.get("plan_forbids_equipment", []):
            for exercise_id in plan_ids:
                required = self._services.repository.exercise_required_equipment(
                    exercise_id
                )
                if item in required:
                    raise CaseFailure(f"plan still requires {item}")
            checks.append(f"plan free of {item}")

        if params.get("expect_downranking") and not diff.downranked:
            raise CaseFailure("ranking did not move")
        if params.get("expect_downranking"):
            checks.append(f"{len(diff.downranked)} down-ranked")

        if params.get("eligible_set_unchanged"):
            _, _, _, base_candidates = self._evaluate(BASE_ADJUSTMENT_PROMPT)
            before = {c.exercise.id for c in base_candidates}
            after = {c.exercise.id for c in state["eligible_exercises"]}
            if before != after:
                raise CaseFailure("the eligible set changed, expected ranking-only")
            checks.append("eligible set unchanged")

        if "duration" in params:
            actual = state["generated_workout"].duration_minutes
            if actual != params["duration"]:
                raise CaseFailure(f"plan duration is {actual} minutes")
            checks.append(f"duration {actual} min")

        if params.get("expect_no_change_note"):
            if diff.removed or diff.added or diff.downranked:
                notes.append("adjustment changed the plan; note not required")
            elif not diff.notes:
                raise CaseFailure("no change and no explanatory note")
            else:
                checks.append("no change, stated explicitly")

        if not state["post_validation"].passed and not params.get("allow_corrections"):
            notes.append("post-validation applied corrections")

        return "; ".join(checks) or "adjusted plan is safe"

    async def _case_adjustment_safety_sweep(self, case, evidence, notes) -> str:  # noqa: ARG002
        adjustments = [
            "Exclude deadlifts.",
            "Only use dumbbells.",
            "Make it more quad focused.",
            "Make it 30 minutes.",
            "Avoid exercises that stress her knee.",
            "Keep it as it is.",
        ]
        for adjustment in adjustments:
            outcome = await self._adjust(adjustment)
            state = outcome["state"]
            excluded = {
                eid for eid, d in state["safety_decisions"].items() if d.is_excluded
            }
            plan = {
                item.exercise_id
                for section in state["generated_workout"].sections
                for item in section.exercises
            }
            if plan & excluded:
                raise CaseFailure(f"'{adjustment}' leaked an excluded exercise")
        return f"{len(adjustments)}/{len(adjustments)} adjusted plans safe"

    async def _case_adjustment_diff_honesty(self, case, evidence, notes) -> str:  # noqa: ARG002
        outcome = await self._adjust(case.params["adjustment"])
        diff = outcome["diff"]
        text = " ".join(
            reason
            for change in [*diff.removed, *diff.added, *diff.downranked]
            for reason in change.reasons
        ).lower()
        for forbidden in ("equivalent", "replaces", "instead of"):
            if forbidden in text:
                raise CaseFailure(f"diff claims '{forbidden}'")
        return "diff explains changes without inventing equivalence"

    # --- validation (adversarial) -----------------------------------------

    async def _case_adversarial(self, case, evidence, notes) -> str:  # noqa: ARG002
        params = case.params

        if params["mode"] == "fail_closed":
            draft = LLMWorkoutDraft.model_validate(
                {
                    "title": "Ghost",
                    "sections": [
                        {
                            "name": "main",
                            "exercises": [
                                {"exercise_id": "not-a-real-id", "name": "Ghost"}
                            ],
                        }
                    ],
                }
            )
            try:
                validate_and_repair(draft, {}, [], 45)
            except UnsafePlanError:
                return "UnsafePlanError raised - failed closed"
            raise CaseFailure("an unvalidated plan was returned")

        _, _, decisions, candidates = self._evaluate(params["prompt"])
        banned = adversarial_draft(params["mode"], decisions, candidates)
        workflow = self._workflow(AdversarialLLM(banned))
        state = await workflow.run(
            WorkoutRequest(
                member_id=MEMBER_ID, prompt=params["prompt"], duration_minutes=45
            )
        )

        planned = {
            item.exercise_id
            for section in state["generated_workout"].sections
            for item in section.exercises
        }
        excluded = {eid for eid, d in state["safety_decisions"].items() if d.is_excluded}
        survivors = planned & excluded
        unknown = planned - set(state["safety_decisions"])

        if survivors or unknown:
            raise CaseFailure(
                f"{len(survivors)} excluded and {len(unknown)} unknown id(s) survived"
            )

        report = state["post_validation"]
        return (
            f"{len(report.rejected)} rejected, {len(report.replacements)} replaced, "
            f"0 unsafe survivors"
        )

    async def _case_duration_validation(self, case, evidence, notes) -> str:  # noqa: ARG002
        state = await self._workflow().run(
            WorkoutRequest(
                member_id=MEMBER_ID,
                prompt=case.params["prompt"],
                duration_minutes=case.params["duration"],
            )
        )
        actual = state["generated_workout"].duration_minutes
        if actual != case.params["duration"]:
            raise CaseFailure(f"plan reports {actual} minutes")
        return f"{actual} minutes"

    async def _case_schema(self, case, evidence, notes) -> str:  # noqa: ARG002
        state = await self._workflow().run(
            WorkoutRequest(
                member_id=MEMBER_ID, prompt=case.params["prompt"], duration_minutes=45
            )
        )
        workout = state["generated_workout"]
        catalog = {e.id for e in self._services.repository.list_exercises()}

        for section in workout.sections:
            if section.name not in {"warmup", "main", "cooldown"}:
                raise CaseFailure(f"unexpected section '{section.name}'")
            for item in section.exercises:
                if item.exercise_id not in catalog:
                    raise CaseFailure(f"id {item.exercise_id} is not in the catalog")
        if not workout.sections:
            raise CaseFailure("plan has no sections")
        return f"{len(workout.sections)} sections, all ids in catalog"

    # --- copilot / MCP -----------------------------------------------------

    async def _case_copilot(self, case, evidence, notes) -> str:  # noqa: ARG002
        params = case.params
        response = await self._services.copilot.answer(self._member, params["question"])
        grounding = response.grounding

        if params.get("intent") and response.intent != params["intent"]:
            raise CaseFailure(f"intent {response.intent}")
        if params.get("expect_mode") and (not grounding or grounding.mode != params["expect_mode"]):
            raise CaseFailure(f"mode {grounding.mode if grounding else 'none'}")
        for tool in params.get("expect_tools", []):
            if not grounding or tool not in grounding.tools_used:
                raise CaseFailure(
                    f"tools used: {grounding.tools_used if grounding else []}"
                )
        if params.get("expect_authoritative") and not (
            grounding and grounding.authoritative_safety
        ):
            raise CaseFailure("safety was not authoritative")
        if not response.answer.strip():
            raise CaseFailure("empty answer")

        return (
            f"intent={response.intent}, mode={grounding.mode if grounding else 'n/a'}, "
            f"tools={','.join(grounding.tools_used) if grounding else 'none'}"
        )

    def _case_mcp_parity(self, case, evidence, notes) -> str:  # noqa: ARG002
        from app.mcp.tools import evaluate_exercise_safety

        _, _, decisions, _ = self._evaluate(
            "Create a 45-minute lower-body workout. Her left knee is bothering her."
        )
        mismatches = []
        for exercise in self._services.repository.list_exercises():
            tool = evaluate_exercise_safety(
                self._services,
                MEMBER_ID,
                exercise.id,
                "Create a 45-minute lower-body workout. Her left knee is bothering her.",
            )
            if tool.status != decisions[exercise.id].status:
                mismatches.append(exercise.name)
        if mismatches:
            raise CaseFailure(f"{len(mismatches)} disagreed: {mismatches[:3]}")
        return f"{len(decisions)}/{len(decisions)} verdicts identical to the engine"

    def _case_mcp_provenance(self, case, evidence, notes) -> str:  # noqa: ARG002
        from app.mcp.tools import get_exercise_provenance

        result = get_exercise_provenance(
            self._services,
            MEMBER_ID,
            self._by_name(case.params["exercise"]),
            "Create a 45-minute lower-body workout. Her left knee is bothering her.",
        )
        paths = [p for p in result.graph_paths if p.relationships]
        if not paths:
            raise CaseFailure("no path with real relationships returned")
        return (
            f"{len(paths)} graph path(s), e.g. "
            f"{'/'.join(paths[0].relationships)} - {paths[0].rendered[:50]}"
        )

    def _case_mcp_candidates(self, case, evidence, notes) -> str:  # noqa: ARG002
        from app.mcp.tools import get_safe_exercise_candidates

        _, _, decisions, _ = self._evaluate(case.params["prompt"])
        excluded = {eid for eid, d in decisions.items() if d.is_excluded}
        result = get_safe_exercise_candidates(
            self._services, MEMBER_ID, case.params["prompt"], limit=50
        )
        returned = [*result.eligible_candidates, *result.downranked_candidates]
        leaked = {c.exercise_id for c in returned} & excluded
        if leaked:
            raise CaseFailure(f"{len(leaked)} excluded exercise(s) returned")
        return f"{len(returned)} candidates returned, 0 excluded"

    def _case_mcp_evaluate(self, case, evidence, notes) -> str:  # noqa: ARG002
        from app.mcp.tools import evaluate_workout_request

        result = evaluate_workout_request(self._services, MEMBER_ID, case.params["prompt"])
        if result.composed_workout is not None:
            raise CaseFailure("the read-only tool composed a workout")
        _, _, _, candidates = self._evaluate(case.params["prompt"])
        if result.safety_summary.eligible_count != len(candidates):
            raise CaseFailure(
                f"eligible {result.safety_summary.eligible_count} != "
                f"engine {len(candidates)}"
            )
        return (
            f"read-only; eligible={result.safety_summary.eligible_count} "
            f"excluded={result.safety_summary.excluded_count}"
        )

    async def _case_copilot_fallback(self, case, evidence, notes) -> str:  # noqa: ARG002
        """Break the MCP gateway and confirm the deterministic path answers."""
        from app.copilot.mcp_gateway import McpUnavailableError
        from app.copilot.service import CopilotService

        class BrokenGateway:
            """Every entry point fails, exactly as an unreachable server would."""

            async def call(self, *args, **kwargs):  # noqa: ANN002, ANN003, ARG002
                raise McpUnavailableError("simulated outage")

            async def call_many(self, *args, **kwargs):  # noqa: ANN002, ANN003, ARG002
                raise McpUnavailableError("simulated outage")

            async def list_tool_names(self):
                raise McpUnavailableError("simulated outage")

        copilot = CopilotService(
            StubLLMClient(),
            gateway=BrokenGateway(),
            trajectory_service=self._trajectory_service,
        )
        response = await copilot.answer(self._member, case.params["question"])
        grounding = response.grounding
        if grounding and grounding.mode != "fallback":
            raise CaseFailure(f"mode {grounding.mode}, expected fallback")
        if "100" not in str(response.evidence) and "50" not in str(response.evidence):
            raise CaseFailure("fallback answer lost the real numbers")
        return "MCP unreachable -> deterministic dispatcher answered"

    async def _case_copilot_missing_data(self, case, evidence, notes) -> str:  # noqa: ARG002
        from app.copilot.service import CopilotService

        stripped = self._member.model_copy(deep=True)
        stripped.labs.blood_panel = None
        stripped.labs.dexa_scan = None

        copilot = CopilotService(
            StubLLMClient(), trajectory_service=self._trajectory_service
        )
        response = await copilot.answer(stripped, "Show me her labs")
        if "no lab" not in response.answer.lower():
            raise CaseFailure(f"answered: {response.answer[:80]}")
        return "admitted the absence instead of improvising"


# --- metrics -----------------------------------------------------------------


def _ratio(results: list[CaseResult], category: str) -> tuple[int, int]:
    subset = [r for r in results if r.category == category]
    return sum(1 for r in subset if r.passed), len(subset)


def _metrics(results: list[CaseResult]) -> list[Metric]:
    """One metric per category, plus the cross-cutting safety numbers."""
    definitions = [
        ("concept_resolution_accuracy", "Concept resolution", "concept_resolution"),
        ("hard_safety_satisfaction", "Hard safety constraints", "safety"),
        ("equipment_compliance", "Equipment compliance", "equipment"),
        ("explicit_exclusion_compliance", "Explicit exclusions", "exclusion"),
        ("longitudinal_consistency", "Longitudinal consistency", "longitudinal"),
        ("adjustment_satisfaction", "Adjustment constraints", "adjustment"),
        ("workout_schema_validity", "Workout validation", "validation"),
        ("mcp_routing_accuracy", "Copilot / MCP", "copilot_mcp"),
    ]

    metrics = [
        Metric(key=key, label=label, numerator=n, denominator=d)
        for key, label, category in definitions
        for n, d in [_ratio(results, category)]
    ]

    validation = [r for r in results if r.category == "validation"]
    metrics.append(
        Metric(
            key="unsafe_escape_rate",
            label="Unsafe validation escapes",
            numerator=sum(1 for r in validation if r.unsafe_escape),
            denominator=len(validation),
            higher_is_better=False,
            detail="Unsafe exercises that survived post-generation validation. Must be 0.",
        )
    )

    coverage = [
        r for r in results if r.case_id in {"safe-provenance-coverage", "safe-counts-injury"}
    ]
    metrics.append(
        Metric(
            key="provenance_coverage",
            label="Provenance coverage",
            numerator=sum(1 for r in coverage if r.passed),
            denominator=len(coverage),
            detail="Every non-allowed decision carries a rule id and graph evidence.",
        )
    )

    parity = [r for r in results if r.case_id in {"mcp-safety-parity", "mcp-fallback"}]
    metrics.append(
        Metric(
            key="mcp_safety_parity",
            label="MCP safety parity",
            numerator=sum(1 for r in parity if r.passed),
            denominator=len(parity),
            detail="MCP verdicts match a direct SafetyEngine call; outage falls back.",
        )
    )

    unresolved = [
        r
        for r in results
        if r.category == "concept_resolution" and "unresolved" in r.expected.lower()
    ]
    metrics.append(
        Metric(
            key="unresolved_correctness",
            label="Unresolved correctness",
            numerator=sum(1 for r in unresolved if r.passed),
            denominator=len(unresolved),
            detail="Phrases that must NOT be forced onto a concept.",
        )
    )
    return metrics


#: Each invariant names the cases that must pass to demonstrate it. Nothing here
#: is asserted by hand - `holds` is computed from those cases' outcomes.
INVARIANT_SPECS: list[tuple[str, str, list[str]]] = [
    (
        "graph_decides_safety",
        "Safety decisions come from graph traversal, not the model",
        ["safe-knee-plyometric", "safe-part-of-closure", "safe-region-stress"],
    ),
    (
        "llm_cannot_reintroduce",
        "The LLM cannot introduce an excluded exercise",
        ["val-excluded-exercise", "val-all-excluded", "val-outside-candidates"],
    ),
    (
        "hallucinated_ids_rejected",
        "Invented exercise ids are rejected and the plan fails closed",
        ["val-hallucinated-id", "val-empty-plan-fails-closed"],
    ),
    (
        "equipment_survives_composition",
        "Equipment constraints survive composition",
        ["val-unavailable-equipment", "adj-only-dumbbells", "equip-no-barbell"],
    ),
    (
        "exclusions_override_personalization",
        "Explicit exclusions override personalization",
        ["long-safety-precedence", "adj-exclude-deadlifts"],
    ),
    (
        "safety_over_longitudinal",
        "Hard safety overrides longitudinal ranking",
        ["long-bounded-adjustment", "long-safety-precedence", "adj-quad-focus"],
    ),
    (
        "mcp_parity",
        "MCP safety matches the direct SafetyEngine",
        ["mcp-safety-parity", "mcp-safe-candidates"],
    ),
    (
        "mcp_fallback_is_deterministic",
        "An MCP outage falls back to the deterministic engine",
        ["mcp-fallback"],
    ),
    (
        "provenance_is_real_evidence",
        "Provenance contains real graph or set-operation evidence",
        ["safe-provenance-coverage", "safe-set-operation-equipment", "mcp-provenance-tool"],
    ),
    (
        "ontology_is_metadata_only",
        "Ontology metadata does not alter SafetyEngine output",
        ["safe-ontology-neutral"],
    ),
    (
        "unresolved_is_never_guessed",
        "An unresolvable phrase is reported, never forced onto a concept",
        ["res-unresolved-nonsense", "res-unresolved-vague-clinical", "res-threshold-guard"],
    ),
    (
        "adjustment_rereuns_safety",
        "Every adjustment re-runs the deterministic safety pipeline",
        ["adj-safety-never-weakened", "adj-knee-safety"],
    ),
]


def _invariants(results: list[CaseResult]) -> list[Invariant]:
    by_id = {r.case_id: r for r in results}
    invariants: list[Invariant] = []

    for key, statement, case_ids in INVARIANT_SPECS:
        present = [cid for cid in case_ids if cid in by_id]
        proven = [cid for cid in present if by_id[cid].passed]
        failed = [cid for cid in present if not by_id[cid].passed]
        invariants.append(
            Invariant(
                key=key,
                statement=statement,
                # An invariant with no executed evidence does not hold. Absence
                # of a failure is not a demonstration.
                holds=bool(present) and not failed,
                proven_by=proven,
                failed_by=failed,
                detail=None if present else "no evaluation case covers this invariant",
            )
        )
    return invariants


def _latency(sorted_latencies: list[float], duration_ms: float) -> LatencySummary:
    if not sorted_latencies:
        return LatencySummary(total_ms=duration_ms)
    index = max(0, int(round(0.95 * (len(sorted_latencies) - 1))))
    return LatencySummary(
        p50_ms=round(median(sorted_latencies), 2),
        p95_ms=round(sorted_latencies[index], 2),
        max_ms=round(sorted_latencies[-1], 2),
        total_ms=duration_ms,
    )


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value
