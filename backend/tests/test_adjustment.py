"""Graph-driven workout adjustment tests.

The property under protection:

    An adjustment is a new deterministic request, not a patch handed to a
    model. Every adjustment re-runs concept resolution, the safety engine and
    the post-generation gate, so a constraint expressed in the adjustment is
    enforced by traversal rather than by the model's reading of the sentence.

The tests that matter most are the ones asserting an adjustment cannot *weaken*
anything: a focus request must not outrank an injury, and the final validator
must still reject an excluded exercise even when the model is told to keep it.
"""

from __future__ import annotations

import pytest

from app.agents.adjustment import combine, resolve_duration
from app.agents.intent import extract_duration, parse_intent
from app.domain.workout import LLMWorkoutDraft, WorkoutRequest
from app.llm.base import LLMClient
from app.llm.stub import StubLLMClient
from app.provenance.diff import build_adjustment_diff
from app.safety.validator import validate_and_repair

from .conftest import MEMBER_ID, by_name

BASE_PROMPT = (
    "Create a 45-minute lower-body workout. Her left knee is bothering her "
    "and she only has dumbbells and a kettlebell."
)


@pytest.fixture
def workflow(repository, ontology, resolver, engine):
    from app.agents.workout_graph import WorkoutWorkflow

    return WorkoutWorkflow(repository, ontology, resolver, engine, StubLLMClient())


async def _run(workflow, prompt: str, duration: int = 45, explicit: bool = False):
    return await workflow.run(
        WorkoutRequest(
            member_id=MEMBER_ID,
            prompt=prompt,
            duration_minutes=duration,
            duration_is_explicit=explicit,
        )
    )


def _plan_ids(state) -> list[str]:
    return [
        item.exercise_id
        for section in state["generated_workout"].sections
        for item in section.exercises
    ]


def _plan_names(state) -> list[str]:
    return [
        item.name
        for section in state["generated_workout"].sections
        for item in section.exercises
    ]


# --- request composition -----------------------------------------------------


class TestRequestComposition:
    def test_the_adjustment_becomes_its_own_clause(self):
        combined = combine("Lower body workout", "Exclude deadlifts")
        assert combined == "Lower body workout. Exclude deadlifts"

    def test_an_empty_side_degrades_cleanly(self):
        assert combine("", "Exclude deadlifts") == "Exclude deadlifts"
        assert combine("Lower body.", "") == "Lower body"

    def test_the_adjustment_duration_wins_over_the_original(self):
        assert resolve_duration(45, BASE_PROMPT, "Make it 30 minutes") == 30

    def test_the_original_duration_survives_an_adjustment_that_says_nothing(self):
        assert resolve_duration(45, BASE_PROMPT, "Exclude deadlifts") == 45

    def test_an_explicit_request_duration_is_used_when_no_prompt_states_one(self):
        assert resolve_duration(50, "Lower body workout", "More quads") == 50

    def test_extract_duration_reports_absence_rather_than_a_default(self):
        assert extract_duration("Exclude deadlifts") is None
        assert extract_duration("make it 30 mins") == 30

    def test_an_explicit_duration_overrides_the_in_prompt_scan(self, resolver):
        """The combined prompt holds two durations; the caller decides."""
        prompt = combine(BASE_PROMPT, "Make it 30 minutes")
        loose, _ = parse_intent(prompt, 45, resolver)
        strict, _ = parse_intent(prompt, 30, resolver, duration_is_explicit=True)

        assert loose.duration_minutes == 45  # regex finds the original first
        assert strict.duration_minutes == 30


# --- the five supported adjustments -----------------------------------------


class TestAdjustmentScenarios:
    async def test_exclude_deadlifts_removes_the_hinge_family(self, workflow, repository):
        walkout = by_name(repository, "One-Kettlebell Hamstring Walkout")
        before = await _run(workflow, BASE_PROMPT)
        assert walkout in _plan_ids(before)

        after = await _run(workflow, combine(BASE_PROMPT, "Exclude deadlifts."))
        assert walkout not in _plan_ids(after)
        assert after["safety_decisions"][walkout].is_excluded

    async def test_exclude_deadlifts_removes_the_whole_family_not_one_name(
        self, workflow, repository
    ):
        """No catalog exercise is named "deadlift" - this must resolve to a family."""
        after = await _run(workflow, combine(BASE_PROMPT, "Exclude deadlifts."))
        for name in ("One-Kettlebell Hamstring Walkout", "Med Ball Hamstring Walkout"):
            decision = after["safety_decisions"][by_name(repository, name)]
            assert decision.is_excluded
            assert "explicit_exclusion" in {r.rule_id for r in decision.reasons}

    async def test_only_dumbbells_re_runs_equipment_filtering(self, workflow, repository):
        """The later restrictive clause narrows the earlier one."""
        walkout = by_name(repository, "One-Kettlebell Hamstring Walkout")
        after = await _run(workflow, combine(BASE_PROMPT, "Only use dumbbells."))

        assert after["safety_decisions"][walkout].is_excluded
        for exercise_id in _plan_ids(after):
            required = repository.exercise_required_equipment(exercise_id)
            assert "Kettlebell" not in required

    async def test_quad_focus_narrows_ranking_without_touching_eligibility(
        self, workflow
    ):
        before = await _run(workflow, BASE_PROMPT)
        after = await _run(
            workflow,
            combine(BASE_PROMPT, "Make it more quad focused without aggravating her knee."),
        )

        # Ranking moved...
        before_scores = {c.exercise.id: c.score for c in before["eligible_exercises"]}
        after_scores = {c.exercise.id: c.score for c in after["eligible_exercises"]}
        assert any(after_scores[k] != before_scores[k] for k in after_scores if k in before_scores)

        # ...but the eligible set did not.
        assert set(before_scores) == set(after_scores)

    async def test_duration_adjustment_is_honoured_by_the_validated_plan(self, workflow):
        after = await _run(
            workflow, combine(BASE_PROMPT, "Make it 30 minutes."), duration=30, explicit=True
        )
        assert after["generated_workout"].duration_minutes == 30
        assert after["intent"].duration_minutes == 30

    async def test_knee_safety_adjustment_re_runs_every_rule(self, workflow, repository):
        """The knee constraint is already in the graph, so the answer is stable.

        The point is not that the plan changes - it is that the whole safety
        pipeline ran again and reached the same conclusion from traversal.
        """
        after = await _run(
            workflow, combine(BASE_PROMPT, "Avoid exercises that stress her knee.")
        )
        jump = by_name(repository, "Static Jump")

        assert after["safety_decisions"][jump].is_excluded
        assert "knee" in " ".join(
            c.canonical_id or "" for c in after["resolved_concepts"]
        )

    async def test_a_region_named_under_an_exclusion_cue_is_not_a_focus_target(
        self, resolver
    ):
        """"Avoid ... her knee" must not make the knee something to train."""
        intent, _ = parse_intent(
            combine(BASE_PROMPT, "Avoid exercises that stress her knee."), 45, resolver
        )
        assert "knee" in intent.injury_mentions
        assert "knee" not in intent.requested_focus


# --- safety cannot be weakened by an adjustment ------------------------------


class TestSafetySurvivesAdjustment:
    async def test_focus_never_overrides_an_injury_exclusion(self, workflow, repository):
        """Asking for quads must not resurrect a plyometric."""
        after = await _run(
            workflow, combine(BASE_PROMPT, "Make it much more quad focused.")
        )
        for name in ("Static Jump", "Vertical Jump to Broad Jump"):
            assert after["safety_decisions"][by_name(repository, name)].is_excluded
        assert not set(_plan_ids(after)) & {
            by_name(repository, "Static Jump"),
            by_name(repository, "Vertical Jump to Broad Jump"),
        }

    async def test_focus_never_overrides_an_equipment_exclusion(self, workflow, repository):
        after = await _run(
            workflow, combine(BASE_PROMPT, "Make it more quad focused, only use dumbbells.")
        )
        for exercise_id in _plan_ids(after):
            required = repository.exercise_required_equipment(exercise_id)
            assert "Barbell" not in required and "Kettlebell" not in required

    async def test_every_adjusted_plan_excludes_what_the_graph_excluded(
        self, workflow
    ):
        for adjustment in [
            "Exclude deadlifts.",
            "Only use dumbbells.",
            "Make it more quad focused.",
            "Make it 30 minutes.",
            "Avoid exercises that stress her knee.",
        ]:
            state = await _run(workflow, combine(BASE_PROMPT, adjustment))
            excluded = {
                eid for eid, d in state["safety_decisions"].items() if d.is_excluded
            }
            assert not set(_plan_ids(state)) & excluded, adjustment

    async def test_the_final_gate_blocks_reintroduction_after_an_adjustment(
        self, repository, ontology, resolver, engine
    ):
        """An adversarial model is told to keep the excluded hinge work."""
        from app.agents.workout_graph import WorkoutWorkflow

        banned_id = by_name(repository, "One-Kettlebell Hamstring Walkout")

        class Adversarial(LLMClient):
            name = "adversarial"

            async def generate_structured(self, *, schema, system, user):  # noqa: ARG002
                return LLMWorkoutDraft.model_validate(
                    {
                        "title": "Adversarial",
                        "sections": [
                            {
                                "name": "main",
                                "exercises": [
                                    {
                                        "exercise_id": banned_id,
                                        "name": "One-Kettlebell Hamstring Walkout",
                                        "sets": 3,
                                        "reps": "8",
                                    }
                                ],
                            }
                        ],
                    }
                )

        workflow = WorkoutWorkflow(repository, ontology, resolver, engine, Adversarial())
        state = await _run(workflow, combine(BASE_PROMPT, "Exclude deadlifts."))

        assert banned_id not in _plan_ids(state)
        assert state["post_validation"].passed is False
        assert any(r["exercise_id"] == banned_id for r in state["post_validation"].rejected)

    def test_validation_still_fails_closed_when_nothing_survives(self):
        draft = LLMWorkoutDraft.model_validate(
            {
                "title": "Empty",
                "sections": [{"name": "main", "exercises": [
                    {"exercise_id": "not-a-real-id", "name": "Ghost", "sets": 3, "reps": "8"}
                ]}],
            }
        )
        from app.safety.validator import UnsafePlanError

        with pytest.raises(UnsafePlanError):
            validate_and_repair(draft, {}, [], 45)


# --- the diff ----------------------------------------------------------------


class TestAdjustmentDiff:
    async def test_removed_entries_carry_the_rule_that_removed_them(
        self, workflow, repository
    ):
        before = await _run(workflow, BASE_PROMPT)
        after = await _run(workflow, combine(BASE_PROMPT, "Exclude deadlifts."))

        diff = build_adjustment_diff(
            previous_exercise_ids=_plan_ids(before),
            new_plan_ids=_plan_ids(after),
            decisions=after["safety_decisions"],
            baseline_candidates=before["eligible_exercises"],
            adjusted_candidates=after["eligible_exercises"],
            provenance=after["provenance"],
        )

        walkout = by_name(repository, "One-Kettlebell Hamstring Walkout")
        removed = next(c for c in diff.removed if c.exercise_id == walkout)
        assert removed.now_excluded is True
        assert "explicit_exclusion" in removed.rule_ids
        assert any("deadlifts" in reason for reason in removed.reasons)

    async def test_an_unselected_exercise_is_not_reported_as_a_safety_event(
        self, workflow
    ):
        """Losing a place in the ranking is not the same as becoming unsafe."""
        before = await _run(workflow, BASE_PROMPT)
        after = await _run(
            workflow, combine(BASE_PROMPT, "Make it 30 minutes."), duration=30, explicit=True
        )

        diff = build_adjustment_diff(
            previous_exercise_ids=_plan_ids(before),
            new_plan_ids=_plan_ids(after),
            decisions=after["safety_decisions"],
            baseline_candidates=before["eligible_exercises"],
            adjusted_candidates=after["eligible_exercises"],
            provenance=after["provenance"],
        )

        assert diff.removed
        assert all(not change.now_excluded for change in diff.removed)
        assert all(
            "no longer selected" in " ".join(change.reasons).lower()
            for change in diff.removed
        )

    async def test_added_entries_are_explained_by_their_own_reasons(self, workflow):
        """No fabricated "equivalent alternative" relationship."""
        before = await _run(workflow, BASE_PROMPT)
        after = await _run(workflow, combine(BASE_PROMPT, "Exclude deadlifts."))

        diff = build_adjustment_diff(
            previous_exercise_ids=_plan_ids(before),
            new_plan_ids=_plan_ids(after),
            decisions=after["safety_decisions"],
            baseline_candidates=before["eligible_exercises"],
            adjusted_candidates=after["eligible_exercises"],
            provenance=after["provenance"],
        )

        assert diff.added
        for change in diff.added:
            assert change.reasons
            joined = " ".join(change.reasons).lower()
            assert "equivalent" not in joined
            assert "replaces" not in joined

    async def test_downranking_reports_real_score_movement(self, workflow):
        before = await _run(workflow, BASE_PROMPT)
        after = await _run(
            workflow, combine(BASE_PROMPT, "Make it more quad focused.")
        )

        diff = build_adjustment_diff(
            previous_exercise_ids=_plan_ids(before),
            new_plan_ids=_plan_ids(after),
            decisions=after["safety_decisions"],
            baseline_candidates=before["eligible_exercises"],
            adjusted_candidates=after["eligible_exercises"],
            provenance=after["provenance"],
        )

        assert diff.downranked
        for change in diff.downranked:
            assert change.score_before is not None and change.score_after is not None
            assert change.score_after < change.score_before

    async def test_no_change_is_stated_rather_than_left_silent(self, workflow):
        before = await _run(workflow, BASE_PROMPT)
        after = await _run(
            workflow, combine(BASE_PROMPT, "Avoid exercises that stress her knee.")
        )

        diff = build_adjustment_diff(
            previous_exercise_ids=_plan_ids(before),
            new_plan_ids=_plan_ids(after),
            decisions=after["safety_decisions"],
            baseline_candidates=before["eligible_exercises"],
            adjusted_candidates=after["eligible_exercises"],
            provenance=after["provenance"],
        )

        if not (diff.removed or diff.added or diff.downranked):
            assert diff.notes
            assert "re-evaluated against the graph" in " ".join(diff.notes)


# --- provenance and grounding survive adjustment -----------------------------


class TestProvenanceAfterAdjustment:
    async def test_provenance_is_rebuilt_for_the_adjusted_plan(self, workflow):
        after = await _run(workflow, combine(BASE_PROMPT, "Exclude deadlifts."))
        bundle = after["provenance"]

        assert {i.exercise_id for i in bundle.included} == set(_plan_ids(after))
        assert any("explicit_exclusion" in i.rule_ids for i in bundle.filtered)

    async def test_ontology_grounding_survives_an_adjustment(self, workflow):
        after = await _run(
            workflow, combine(BASE_PROMPT, "Avoid exercises that stress her knee.")
        )
        knee = next(
            c
            for c in after["graph_reasoning"].prompt_concepts
            if c.canonical_id == "anatomy:knee"
        )
        assert knee.grounding is not None
        assert knee.grounding.ontology_code == "72696002"

    async def test_longitudinal_influence_survives_an_adjustment(self, workflow):
        after = await _run(workflow, combine(BASE_PROMPT, "Exclude deadlifts."))

        assert after["trajectory"].progression.state == "hold"
        assert after["provenance"].trajectory is not None
        assert any("Progression: hold" in f for f in after["provenance"].member_facts)


# --- HTTP contract -----------------------------------------------------------


class TestAdjustEndpoint:
    async def test_the_endpoint_returns_a_full_plan_plus_a_diff(self, monkeypatch):
        from fastapi.testclient import TestClient

        import app.mcp.server as mcp_server_module
        from app.main import create_app

        monkeypatch.setattr(mcp_server_module, "_asgi_app", None)

        with TestClient(create_app()) as client:
            generated = client.post(
                "/api/workouts/generate",
                json={
                    "member_id": MEMBER_ID,
                    "prompt": BASE_PROMPT,
                    "duration_minutes": 45,
                },
            ).json()
            previous = [
                item["exercise_id"]
                for section in generated["workout"]["sections"]
                for item in section["exercises"]
            ]

            response = client.post(
                "/api/workouts/adjust",
                json={
                    "member_id": MEMBER_ID,
                    "base_prompt": BASE_PROMPT,
                    "adjustment": "Exclude deadlifts.",
                    "duration_minutes": 45,
                    "previous_exercise_ids": previous,
                },
            )
            assert response.status_code == 200
            body = response.json()

        # An adjusted response is a superset of a generated one - same
        # provenance, same graph reasoning, same safety guarantees.
        assert body["adjustment"] == "Exclude deadlifts."
        assert "Exclude deadlifts" in body["effective_prompt"]
        assert body["safety"]["post_validation_passed"] is True
        assert body["graph_reasoning"] is not None
        assert body["trajectory"]["progression"]["state"] == "hold"
        assert body["diff"]["counts"]["newly_excluded"] >= 1
