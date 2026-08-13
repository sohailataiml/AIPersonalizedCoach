"""Post-generation safety gate tests - the project's most important assertion.

Everything else in the safety architecture is prevention: the LLM is handed a
pre-filtered candidate list and told not to deviate. These tests cover what
happens when that prevention *fails* - a jailbroken, buggy, or simply
badly-behaved model that returns an exercise the graph excluded.

The property under test is an invariant, not a best effort:

    no exercise excluded by graph traversal can appear in a returned plan,
    regardless of what the model produced.

We prove it by driving the real workflow with an adversarial LLM client rather
than by asserting on the prompt.
"""

from __future__ import annotations

import pytest

from app.agents.intent import parse_intent
from app.agents.workout_graph import WorkoutWorkflow
from app.domain.workout import (
    LLMWorkoutDraft,
    WorkoutExercise,
    WorkoutRequest,
    WorkoutSection,
)
from app.safety.ranking import rank_candidates
from app.safety.validator import UnsafePlanError, validate_and_repair

from .conftest import MEMBER_ID, by_name

INJURY_PROMPT = "Create a 45-minute lower-body workout. Her left knee is bothering her."
EQUIPMENT_PROMPT = (
    "Build a full-body workout. She has no barbell, only dumbbells and a kettlebell."
)


class AdversarialLLM:
    """A model that ignores the candidate list and returns unsafe picks."""

    name = "adversarial-test-double"

    def __init__(self, exercises: list[tuple[str, str]]) -> None:
        self._exercises = exercises

    async def generate_structured(self, *, schema, system, user, max_tokens=2000):
        return LLMWorkoutDraft(
            title="Jailbroken Plan",
            sections=[
                WorkoutSection(
                    name="main",
                    exercises=[
                        WorkoutExercise(
                            exercise_id=exercise_id,
                            name=name,
                            sets=3,
                            reps="10",
                            rest_seconds=60,
                            rationale="Model decided this was fine.",
                        )
                        for exercise_id, name in self._exercises
                    ],
                )
            ],
        )

    async def answer_grounded(self, *, system, user, evidence, max_tokens=700):
        return "unused"


@pytest.fixture
def prepared(evaluate, repository, member, resolver, ontology):
    """Safety decisions + ranked candidates for the injury scenario."""

    def _prepare(prompt: str = INJURY_PROMPT):
        decisions, context = evaluate(prompt)
        intent, resolved = parse_intent(prompt, 45, resolver)
        candidates = rank_candidates(
            repository.list_exercises(), decisions, member, intent, resolved, ontology
        )
        return decisions, candidates

    return _prepare


class TestExcludedExerciseIsRejected:
    def test_excluded_exercise_never_survives_validation(self, prepared, repository):
        """The headline invariant."""
        decisions, candidates = prepared()
        banned_id = by_name(repository, "Static Jump")  # plyometric, hard-excluded
        assert decisions[banned_id].is_excluded

        draft = LLMWorkoutDraft(
            title="Unsafe",
            sections=[
                WorkoutSection(
                    name="main",
                    exercises=[
                        WorkoutExercise(exercise_id=banned_id, name="Static Jump", sets=3)
                    ],
                )
            ],
        )

        workout, report = validate_and_repair(draft, decisions, candidates, 45)

        assert banned_id not in {e.exercise_id for e in workout.all_exercises()}
        assert report.passed is False
        assert report.rejected[0]["exercise_id"] == banned_id

    def test_rejection_records_why_and_the_graph_path(self, prepared, repository):
        decisions, candidates = prepared()
        banned_id = by_name(repository, "Static Jump")
        draft = _draft([(banned_id, "Static Jump")])

        _, report = validate_and_repair(draft, decisions, candidates, 45)

        rejection = report.rejected[0]
        assert rejection["rule_id"] == "injury_contraindicated_pattern"
        assert any("CONTRAINDICATES" in p for p in rejection["graph_paths"])

    def test_rejected_exercise_is_replaced_from_the_safe_pool(self, prepared, repository):
        decisions, candidates = prepared()
        banned_id = by_name(repository, "Static Jump")
        draft = _draft([(banned_id, "Static Jump")])

        workout, report = validate_and_repair(draft, decisions, candidates, 45)

        assert report.replacements
        replacement_id = report.replacements[0]["with_id"]
        assert not decisions[replacement_id].is_excluded
        substituted = [e for e in workout.all_exercises() if e.substituted_for]
        assert substituted and substituted[0].substituted_for == "Static Jump"

    def test_equipment_exclusion_also_blocked(self, prepared, repository):
        """A barbell lift the member cannot perform must not survive either."""
        decisions, candidates = prepared(EQUIPMENT_PROMPT)
        banned_id = by_name(repository, "Barbell Decline Bench Press")
        assert decisions[banned_id].is_excluded

        workout, report = validate_and_repair(
            _draft([(banned_id, "Barbell Decline Bench Press")]), decisions, candidates, 45
        )
        assert banned_id not in {e.exercise_id for e in workout.all_exercises()}
        assert report.passed is False

    def test_every_excluded_exercise_is_blocked(self, prepared):
        """Not just the convenient examples - all of them."""
        decisions, candidates = prepared()
        excluded = [d for d in decisions.values() if d.is_excluded]
        assert len(excluded) > 5

        draft = _draft([(d.exercise_id, d.exercise_name) for d in excluded])
        workout, report = validate_and_repair(draft, decisions, candidates, 45)

        planned = {e.exercise_id for e in workout.all_exercises()}
        assert not planned & {d.exercise_id for d in excluded}
        assert len(report.rejected) == len(excluded)


class TestHallucinatedIds:
    def test_invented_id_is_rejected(self, prepared):
        decisions, candidates = prepared()
        draft = _draft([("totally-made-up-id", "Imaginary Squat")])

        workout, report = validate_and_repair(draft, decisions, candidates, 45)

        assert "totally-made-up-id" not in {e.exercise_id for e in workout.all_exercises()}
        assert report.hallucinated_ids == ["totally-made-up-id"]
        assert report.passed is False

    def test_all_surviving_ids_exist_in_the_catalog(self, prepared, repository):
        decisions, candidates = prepared()
        catalog_ids = {e.id for e in repository.list_exercises()}
        draft = _draft([("fake-1", "Fake"), ("fake-2", "Also Fake")])

        workout, _ = validate_and_repair(draft, decisions, candidates, 45)
        assert {e.exercise_id for e in workout.all_exercises()} <= catalog_ids


class TestFailClosed:
    def test_raises_when_nothing_can_be_made_safe(self, prepared):
        """With no safe pool to draw from, we fail rather than return junk."""
        decisions, _ = prepared()
        excluded_id = next(d.exercise_id for d in decisions.values() if d.is_excluded)

        with pytest.raises(UnsafePlanError):
            validate_and_repair(_draft([(excluded_id, "x")]), decisions, [], 45)

    def test_repair_can_be_disabled_for_strict_callers(self, prepared, repository):
        decisions, candidates = prepared()
        banned_id = by_name(repository, "Static Jump")

        with pytest.raises(UnsafePlanError):
            validate_and_repair(
                _draft([(banned_id, "Static Jump")]),
                decisions,
                candidates,
                45,
                allow_repair=False,
            )


class TestCleanPlansAreUntouched:
    def test_safe_plan_passes_without_corrections(self, prepared, repository):
        decisions, candidates = prepared()
        safe = candidates[:3]
        draft = _draft([(c.exercise.id, c.exercise.name) for c in safe])

        workout, report = validate_and_repair(draft, decisions, candidates, 45)

        assert report.passed is True
        assert not report.rejected
        assert len(workout.all_exercises()) == 3

    def test_duplicates_are_dropped_without_being_a_safety_event(
        self, prepared, repository
    ):
        decisions, candidates = prepared()
        first = candidates[0]
        draft = _draft([(first.exercise.id, first.exercise.name)] * 2)

        workout, report = validate_and_repair(draft, decisions, candidates, 45)

        assert len(workout.all_exercises()) == 1
        assert report.passed is True


class TestEndToEndWithAdversarialModel:
    """Drive the real LangGraph workflow with a hostile model."""

    async def test_workflow_sanitizes_a_jailbroken_plan(
        self, repository, ontology, resolver, engine
    ):
        banned = [
            (by_name(repository, "Static Jump"), "Static Jump"),
            (by_name(repository, "Barbell Decline Bench Press"), "Barbell Decline Bench Press"),
            ("hallucinated-id-9000", "Nonexistent Lift"),
        ]
        workflow = WorkoutWorkflow(
            repository, ontology, resolver, engine, AdversarialLLM(banned)
        )

        state = await workflow.run(
            WorkoutRequest(member_id=MEMBER_ID, prompt=INJURY_PROMPT, duration_minutes=45)
        )

        planned = {e.exercise_id for e in state["generated_workout"].all_exercises()}
        report = state["post_validation"]

        assert not planned & {exercise_id for exercise_id, _ in banned}
        assert report.passed is False
        assert len(report.rejected) == 3
        assert "hallucinated-id-9000" in report.hallucinated_ids

        # And the correction is visible in provenance, not silently swallowed.
        assert state["provenance"].counts["post_validation_rejections"] == 3

    async def test_workflow_marks_substitutions_in_provenance(
        self, repository, ontology, resolver, engine
    ):
        banned = [(by_name(repository, "Static Jump"), "Static Jump")]
        workflow = WorkoutWorkflow(
            repository, ontology, resolver, engine, AdversarialLLM(banned)
        )
        state = await workflow.run(
            WorkoutRequest(member_id=MEMBER_ID, prompt=INJURY_PROMPT, duration_minutes=45)
        )

        substituted = [i for i in state["provenance"].included if i.decision == "substituted"]
        assert substituted
        assert substituted[0].decision_source == "post_validation"


def _draft(exercises: list[tuple[str, str]]) -> LLMWorkoutDraft:
    return LLMWorkoutDraft(
        title="Test Plan",
        sections=[
            WorkoutSection(
                name="main",
                exercises=[
                    WorkoutExercise(exercise_id=exercise_id, name=name, sets=3, reps="10")
                    for exercise_id, name in exercises
                ],
            )
        ],
    )
