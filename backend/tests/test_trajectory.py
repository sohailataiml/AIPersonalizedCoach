"""Longitudinal reasoning tests.

Three properties, in descending order of how much damage a bug would do:

1. **Hard safety always wins.** A trajectory can reorder what safety allowed and
   nothing else. No combination of longitudinal signals may promote an excluded
   exercise, or lift a safety-flagged one past an unflagged one.
2. **Nothing medical is inferred.** ``injury_trajectory`` is copied from the
   recorded status. Falling adherence and short sessions never become a clinical
   conclusion, because they do not support one.
3. **Insufficient data is an answer.** Every signal degrades to an explicit
   ``insufficient_data`` / ``unknown`` rather than to a confident guess from one
   observation.

The negative tests carry most of the weight here. A personalization layer that
quietly outranks a safety penalty would still look correct in a demo.
"""

from __future__ import annotations

import pytest

from app.agents.intent import parse_intent
from app.api.deps import Services
from app.copilot import analytics
from app.copilot.service import CopilotService
from app.core.config import get_settings
from app.domain.member import AdherenceObservation, WorkoutSession
from app.domain.trajectory import MemberTrajectory
from app.llm.stub import StubLLMClient
from app.member.trajectory import MemberTrajectoryService
from app.safety.policies import (
    MAX_LONGITUDINAL_ADJUSTMENT,
    SMALLEST_SAFETY_PENALTY,
)
from app.safety.ranking import rank_candidates

INJURY_PROMPT = "Create a 45-minute lower-body workout. Her left knee is bothering her."


@pytest.fixture
def service(ontology) -> MemberTrajectoryService:
    return MemberTrajectoryService(ontology)


@pytest.fixture
def services(repository, ontology, resolver, engine, service) -> Services:
    """A Services container over the in-memory backend, sharing one trajectory."""
    return Services(
        settings=get_settings(),
        ontology=ontology,
        repository=repository,
        resolver=resolver,
        engine=engine,
        llm=StubLLMClient(),
        workflow=None,  # not needed: no MCP tool composes a workout
        copilot=None,
        backend="memory",
        trajectory=service,
    )


@pytest.fixture
def trajectory(service, member) -> MemberTrajectory:
    return service.analyze(member)


def _ranked(repository, decisions, member, resolver, ontology, prompt, trajectory=None):
    intent, resolved = parse_intent(prompt, 45, resolver)
    return rank_candidates(
        repository.list_exercises(),
        decisions,
        member,
        intent,
        resolved,
        ontology,
        trajectory=trajectory,
    )


# --- the derived signals -----------------------------------------------------


class TestDerivedSignals:
    def test_declining_adherence_is_read_from_the_observations(self, trajectory):
        assert trajectory.adherence.direction == "declining"
        assert trajectory.adherence.first == 100.0
        assert trajectory.adherence.latest == 50.0
        assert trajectory.adherence.delta == -50.0
        assert trajectory.adherence.observations == 4

    def test_sleep_is_reported_flat_because_the_data_is_flat(self, trajectory):
        """The supplied nights average 6.27h with no downward drift.

        Calling this "declining" would be the easy, wrong answer - it fits the
        narrative of a struggling member but not the numbers.
        """
        assert trajectory.sleep.direction == "flat"
        assert trajectory.sleep.average_recent == 6.27
        assert trajectory.sleep.nights == 7

    def test_training_load_is_measured_against_the_members_own_target(self, trajectory):
        assert trajectory.training_load.state == "low"
        assert trajectory.training_load.completed_sessions == 3
        assert trajectory.training_load.target_sessions_per_week == 4
        assert trajectory.training_load.ratio_to_target == pytest.approx(0.66, abs=0.01)

    def test_progression_holds_and_says_why(self, trajectory):
        assert trajectory.progression.state == "hold"
        assert any("Adherence declining" in r for r in trajectory.progression.rationale)
        assert any("Training load low" in r for r in trajectory.progression.rationale)

    def test_bias_follows_from_progression(self, trajectory):
        assert trajectory.bias.volume_bias == "conservative"
        assert trajectory.bias.novelty_bias == "low"

    def test_stable_adherence_does_not_produce_a_hold(self, service, member):
        steady = member.model_copy(deep=True)
        steady.adherence.weekly_completion_pct = [
            AdherenceObservation(week_of=f"2026-05-{day:02d}", pct=90.0)
            for day in (5, 12, 19, 26)
        ]
        steady.preferences.training_days_per_week = 2

        result = service.analyze(steady)
        assert result.adherence.direction == "flat"
        assert result.training_load.state in {"moderate", "high"}
        assert result.progression.state == "progress"
        assert result.bias.novelty_bias in {"standard", "high"}


# --- insufficient data -------------------------------------------------------


class TestInsufficientData:
    def test_a_single_adherence_week_is_insufficient_not_flat(self, service, member):
        sparse = member.model_copy(deep=True)
        sparse.adherence.weekly_completion_pct = [
            AdherenceObservation(week_of="2026-06-02", pct=50.0)
        ]
        result = service.analyze(sparse)

        assert result.adherence.direction == "insufficient_data"
        assert result.progression.state == "insufficient_data"

    def test_no_history_leaves_training_load_insufficient(self, service, member):
        empty = member.model_copy(deep=True)
        empty.workout_history = []
        result = service.analyze(empty)

        assert result.training_load.state == "insufficient_data"
        assert result.progression.state == "insufficient_data"

    def test_one_completed_session_is_not_enough_for_a_load_reading(self, service, member):
        thin = member.model_copy(deep=True)
        thin.workout_history = [
            WorkoutSession(
                date="2026-06-03", title="Lower Body", planned=True, completed=True,
                duration_min=30, rpe=6,
            )
        ]
        assert service.analyze(thin).training_load.state == "insufficient_data"

    def test_an_unparseable_date_degrades_rather_than_crashing(self, service, member):
        broken = member.model_copy(deep=True)
        broken.workout_history[0].date = "not-a-date"
        assert service.analyze(broken).training_load.state == "insufficient_data"

    def test_missing_weekly_target_leaves_load_insufficient(self, service, member):
        untargeted = member.model_copy(deep=True)
        untargeted.preferences.training_days_per_week = None
        assert service.analyze(untargeted).training_load.state == "insufficient_data"

    def test_no_signal_means_no_personalization_lever(self, service, member):
        blank = member.model_copy(deep=True)
        blank.adherence.weekly_completion_pct = []
        blank.workout_history = []
        result = service.analyze(blank)

        assert result.has_signal is False
        assert result.bias.volume_bias == "standard"
        assert result.bias.novelty_bias == "standard"


# --- nothing medical is inferred ---------------------------------------------


class TestNoFabricatedTrajectory:
    def test_injury_trajectory_is_copied_from_the_recorded_status(self, trajectory):
        assert trajectory.injury_trajectory.state == "recovering"
        assert trajectory.injury_trajectory.source == "recorded_status"
        assert trajectory.injury_trajectory.recorded_status == "recovering"

    def test_declining_adherence_never_implies_a_worsening_injury(self, service, member):
        """The most tempting bad inference available in this dataset."""
        struggling = member.model_copy(deep=True)
        struggling.adherence.weekly_completion_pct = [
            AdherenceObservation(week_of="2026-05-12", pct=100.0),
            AdherenceObservation(week_of="2026-06-02", pct=10.0),
        ]
        result = service.analyze(struggling)

        assert result.adherence.direction == "declining"
        assert result.injury_trajectory.state == "recovering"  # unchanged
        assert result.injury_trajectory.source == "recorded_status"

    def test_an_unrecognised_status_is_unknown_not_the_nearest_guess(
        self, service, member
    ):
        odd = member.model_copy(deep=True)
        odd.injuries[0].status = "under review"
        result = service.analyze(odd)

        assert result.injury_trajectory.state == "unknown"
        assert result.injury_trajectory.recorded_status == "under review"

    def test_no_injury_yields_unknown_with_no_source(self, service, member):
        healthy = member.model_copy(deep=True)
        healthy.injuries = []
        result = service.analyze(healthy)

        assert result.injury_trajectory.state == "unknown"
        assert result.injury_trajectory.source == "absent"

    def test_familiar_families_come_from_the_ontology_not_invented(
        self, trajectory, ontology
    ):
        for family_id in trajectory.bias.familiar_movement_families:
            assert family_id in ontology.movement_families

    def test_unmatchable_history_names_contribute_nothing(self, service, member):
        """"Hip Thrust", "Wall Sit" and "Banded Lateral Walk" have no family alias."""
        families = service.familiar_movement_families(member)
        assert set(families) == {"hinge", "lunge", "pull", "push", "squat"}

    def test_only_completed_sessions_count_as_familiar(self, service, member):
        skipped = member.model_copy(deep=True)
        for session in skipped.workout_history:
            session.completed = False
        assert service.familiar_movement_families(skipped) == []


# --- ranking influence -------------------------------------------------------


class TestRankingInfluence:
    def test_familiar_families_are_rewarded_while_adherence_declines(
        self, evaluate, repository, member, resolver, ontology, trajectory
    ):
        decisions, _ = evaluate(INJURY_PROMPT)
        ranked = _ranked(
            repository, decisions, member, resolver, ontology, INJURY_PROMPT, trajectory
        )
        boosted = [c for c in ranked if c.longitudinal_adjustment > 0]

        assert boosted, "expected at least one familiar-family exercise to be boosted"
        for candidate in boosted:
            assert candidate.longitudinal_reasons
            assert "familiar movement family" in candidate.longitudinal_reasons[0]

    def test_the_influence_is_recorded_separately_from_the_score(
        self, evaluate, repository, member, resolver, ontology, trajectory
    ):
        decisions, _ = evaluate(INJURY_PROMPT)
        with_traj = _ranked(
            repository, decisions, member, resolver, ontology, INJURY_PROMPT, trajectory
        )
        without = {
            c.exercise.id: c
            for c in _ranked(
                repository, decisions, member, resolver, ontology, INJURY_PROMPT
            )
        }

        for candidate in with_traj:
            baseline = without[candidate.exercise.id]
            assert candidate.score == pytest.approx(
                baseline.score + candidate.longitudinal_adjustment
            )

    def test_omitting_the_trajectory_reproduces_the_pre_longitudinal_ordering(
        self, evaluate, repository, member, resolver, ontology
    ):
        decisions, _ = evaluate(INJURY_PROMPT)
        ranked = _ranked(repository, decisions, member, resolver, ontology, INJURY_PROMPT)

        assert all(c.longitudinal_adjustment == 0.0 for c in ranked)
        assert all(c.longitudinal_reasons == [] for c in ranked)

    def test_a_high_novelty_bias_rewards_unfamiliar_families_instead(
        self, evaluate, repository, member, resolver, ontology, trajectory
    ):
        ambitious = trajectory.model_copy(deep=True)
        ambitious.bias.novelty_bias = "high"

        decisions, _ = evaluate(INJURY_PROMPT)
        ranked = _ranked(
            repository, decisions, member, resolver, ontology, INJURY_PROMPT, ambitious
        )
        boosted = [c for c in ranked if c.longitudinal_adjustment > 0]

        assert boosted
        assert all("new movement family" in c.longitudinal_reasons[0] for c in boosted)


# --- hard safety still wins --------------------------------------------------


class TestSafetyRemainsAuthoritative:
    def test_the_adjustment_is_bounded_below_the_smallest_safety_penalty(self):
        """The structural guarantee, asserted rather than intended."""
        assert MAX_LONGITUDINAL_ADJUSTMENT < SMALLEST_SAFETY_PENALTY

    def test_no_candidate_exceeds_the_bound(
        self, evaluate, repository, member, resolver, ontology, trajectory
    ):
        decisions, _ = evaluate(INJURY_PROMPT)
        ranked = _ranked(
            repository, decisions, member, resolver, ontology, INJURY_PROMPT, trajectory
        )
        for candidate in ranked:
            assert abs(candidate.longitudinal_adjustment) <= MAX_LONGITUDINAL_ADJUSTMENT

    @pytest.mark.parametrize(
        "prompt",
        [
            INJURY_PROMPT,
            "Build a full-body workout. She has no barbell, only dumbbells and a kettlebell.",
            "Create a lower-body workout but exclude deadlifts.",
        ],
    )
    def test_the_eligible_set_is_identical_with_and_without_a_trajectory(
        self, evaluate, repository, member, resolver, ontology, trajectory, prompt
    ):
        """Longitudinal reasoning may reorder. It may never add or remove."""
        decisions, _ = evaluate(prompt)
        with_traj = _ranked(
            repository, decisions, member, resolver, ontology, prompt, trajectory
        )
        without = _ranked(repository, decisions, member, resolver, ontology, prompt)

        assert {c.exercise.id for c in with_traj} == {c.exercise.id for c in without}

    def test_an_excluded_exercise_is_never_boosted_back(
        self, evaluate, repository, member, resolver, ontology, trajectory
    ):
        """"Exclude deadlifts" removes the hinge family - the most familiar one."""
        prompt = "Create a lower-body workout but exclude deadlifts."
        decisions, _ = evaluate(prompt)
        excluded = {eid for eid, d in decisions.items() if d.is_excluded}

        assert "hinge" in trajectory.bias.familiar_movement_families
        ranked = _ranked(
            repository, decisions, member, resolver, ontology, prompt, trajectory
        )
        assert not {c.exercise.id for c in ranked} & excluded

    def test_familiarity_cannot_outrank_a_safety_penalty(
        self, evaluate, repository, member, resolver, ontology, trajectory
    ):
        """A boosted, safety-flagged exercise stays below its unflagged twin.

        Compares each safety-penalised candidate against the identical exercise
        scored with no penalty: the longitudinal lift can never close a gap the
        safety engine opened.
        """
        decisions, _ = evaluate(INJURY_PROMPT)
        ranked = _ranked(
            repository, decisions, member, resolver, ontology, INJURY_PROMPT, trajectory
        )
        for candidate in ranked:
            decision = decisions[candidate.exercise.id]
            if decision.score_adjustment >= 0:
                continue
            assert (
                candidate.longitudinal_adjustment < abs(decision.score_adjustment)
            ), f"{candidate.exercise.name}: personalization offset a safety penalty"

    def test_the_safety_engine_never_receives_a_trajectory(self, engine):
        """The boundary, checked at the interface rather than by convention."""
        import inspect

        for name in ("build_context", "evaluate", "evaluate_all"):
            signature = inspect.signature(getattr(engine, name))
            assert "trajectory" not in signature.parameters


# --- one shared service ------------------------------------------------------


class TestSharedAcrossSurfaces:
    def test_the_service_does_not_recompute_analytics(self, service, member):
        """Trend numbers must come from copilot.analytics, not a second impl."""
        result = service.analyze(member)
        adherence = analytics.adherence_trend(member)
        sleep = analytics.sleep_trend(member)

        assert result.adherence.direction == adherence.direction
        assert result.adherence.delta == adherence.delta
        assert result.sleep.direction == sleep.direction
        assert result.sleep.average_recent == sleep.average

    async def test_copilot_and_the_pipeline_report_the_same_trajectory(
        self, service, member
    ):
        copilot = CopilotService(StubLLMClient(), trajectory_service=service)
        response = await copilot.answer(member, "How's adherence trending?")
        longitudinal = response.evidence.get("longitudinal")

        assert longitudinal is not None
        expected = service.analyze(member)
        assert longitudinal["progression_state"] == expected.progression.state
        assert longitudinal["adherence_direction"] == expected.adherence.direction
        assert longitudinal["injury_trajectory"] == expected.injury_trajectory.state

    async def test_copilot_without_the_service_degrades_quietly(self, member):
        copilot = CopilotService(StubLLMClient())
        response = await copilot.answer(member, "How's adherence trending?")

        assert response.evidence.get("longitudinal") is None
        assert response.evidence["direction"] == "declining"

    def test_summary_facts_state_the_provenance_of_the_injury_reading(self, trajectory):
        facts = " ".join(trajectory.summary_facts())
        assert "recorded status - not inferred" in facts


# --- pipeline integration and provenance -------------------------------------


class TestPipelineIntegration:
    async def _run(self, repository, ontology, resolver, engine, prompt=INJURY_PROMPT):
        from app.agents.workout_graph import WorkoutWorkflow
        from app.domain.workout import WorkoutRequest

        workflow = WorkoutWorkflow(repository, ontology, resolver, engine, StubLLMClient())
        return await workflow.run(
            WorkoutRequest(member_id="mbr_01HX9JORDAN", prompt=prompt, duration_minutes=45)
        )

    async def test_the_workflow_runs_a_longitudinal_node(
        self, repository, ontology, resolver, engine
    ):
        state = await self._run(repository, ontology, resolver, engine)

        assert "analyze_longitudinal_context" in state["timings"]
        assert state["trajectory"].progression.state == "hold"

    async def test_provenance_states_the_longitudinal_influence(
        self, repository, ontology, resolver, engine
    ):
        state = await self._run(repository, ontology, resolver, engine)
        bundle = state["provenance"]

        assert bundle.trajectory is not None
        influenced = [i for i in bundle.included if i.longitudinal_adjustment]
        assert influenced, "expected the plan to contain a familiarity-boosted exercise"
        for item in influenced:
            assert item.longitudinal_reasons
            assert any(
                r.startswith("Longitudinal personalization:") for r in item.reasons
            )

    async def test_member_facts_carry_the_trajectory_summary(
        self, repository, ontology, resolver, engine
    ):
        state = await self._run(repository, ontology, resolver, engine)
        facts = " ".join(state["provenance"].member_facts)

        assert "Adherence declining" in facts
        assert "Progression: hold" in facts

    async def test_the_plan_still_excludes_everything_safety_excluded(
        self, repository, ontology, resolver, engine
    ):
        """End-to-end restatement of the invariant, through the real workflow."""
        state = await self._run(
            repository, ontology, resolver, engine,
            prompt="Create a lower-body workout but exclude deadlifts.",
        )
        excluded = {
            eid for eid, d in state["safety_decisions"].items() if d.is_excluded
        }
        planned = {
            item.exercise_id
            for section in state["generated_workout"].sections
            for item in section.exercises
        }
        assert not planned & excluded

    async def test_the_llm_receives_states_not_raw_longitudinal_data(
        self, repository, ontology, resolver, engine, member, trajectory
    ):
        """The model may phrase a conclusion; it may not recompute one."""
        from app.agents.workout_planner import _build_payload
        from app.safety.engine import SafetyContext

        intent, resolved = parse_intent(INJURY_PROMPT, 45, resolver)
        context: SafetyContext = engine.build_context(member, intent, resolved)
        payload = _build_payload(member, intent, [], context, {}, trajectory)

        block = payload["member_trajectory"]
        assert block["progression_state"] == "hold"
        assert block["volume_bias"] == "conservative"
        # No weekly percentages, no nightly sleep hours, no session rows.
        serialized = str(block)
        assert "100" not in serialized and "6.27" not in serialized

    async def test_the_api_exposes_the_trajectory(self, monkeypatch):
        from fastapi.testclient import TestClient

        import app.mcp.server as mcp_server_module
        from app.main import create_app

        # The MCP ASGI app is cached at module scope and its session manager may
        # only be started once, so a second app in the same process needs the
        # cache cleared. Same reset the MCP round-trip test performs.
        monkeypatch.setattr(mcp_server_module, "_asgi_app", None)

        with TestClient(create_app()) as client:
            response = client.post(
                "/api/workouts/generate",
                json={
                    "member_id": "mbr_01HX9JORDAN",
                    "prompt": INJURY_PROMPT,
                    "duration_minutes": 45,
                },
            )
            assert response.status_code == 200
            body = response.json()

        assert body["trajectory"]["progression"]["state"] == "hold"
        assert body["trajectory"]["injury_trajectory"]["source"] == "recorded_status"
        assert "analyze_longitudinal_context" in body["timings_ms"]


class TestMcpReuse:
    def test_member_context_carries_the_shared_trajectory(self, services, member, service):
        from app.mcp.tools import get_member_context

        view = get_member_context(services, member.profile.id)
        assert view.trajectory is not None
        assert view.trajectory.model_dump() == service.analyze(member).model_dump()

    def test_metric_trend_carries_the_same_trajectory(self, services, member, service):
        from app.mcp.tools import get_member_metric_trend

        result = get_member_metric_trend(services, member.profile.id, "adherence")
        assert result.trajectory is not None
        assert result.trajectory.progression.state == service.analyze(member).progression.state

    def test_metric_trend_numbers_are_unchanged_by_the_addition(self, services, member):
        from app.mcp.tools import get_member_metric_trend

        result = get_member_metric_trend(services, member.profile.id, "adherence")
        trend = analytics.adherence_trend(member)

        assert result.first_value == trend.first
        assert result.latest_value == trend.latest
        assert result.direction == "declining"
        assert result.computed_by == "deterministic_python"
