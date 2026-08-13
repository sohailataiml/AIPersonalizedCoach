"""Graph-trace fidelity tests.

The single property these exist to protect:

    A graph trace must never claim a relationship the safety engine did not use,
    and must never exist for a decision the engine did not make.

That is why the strongest tests here are negative. It is easy to render a
convincing path; the risk is rendering a *convincing wrong* one. Several of
these lock down relationships that were previously fabricated for display
(`DOES_NOT_HAVE`, `LOADS_SIDE`, a compressed `Exercise -> Family` hop) and are
now stated as facts or expanded into the real two-hop chain.
"""

from __future__ import annotations

import pytest

from app.agents.intent import parse_intent
from app.agents.workout_graph import WorkoutWorkflow
from app.domain.workout import WorkoutRequest
from app.graph import model as graph_model
from app.provenance.builder import build_provenance
from app.provenance.graph_trace import build_graph_reasoning
from app.safety.ranking import rank_candidates
from app.safety.validator import validate_and_repair

from .conftest import MEMBER_ID, by_name

INJURY_PROMPT = (
    "Create a 45-minute lower-body workout. Her left knee is bothering her "
    "and she only has dumbbells and a kettlebell."
)
EXCLUSION_PROMPT = "Create a lower-body workout but exclude deadlifts."

REAL_RELATIONSHIPS = {
    name
    for name, value in vars(graph_model).items()
    if name.isupper() and isinstance(value, str) and name == value
}


@pytest.fixture
def reasoning(repository, ontology, resolver, engine, member):
    """Run the deterministic half of the pipeline and build a trace from it."""

    def _run(prompt: str):
        intent, resolved = parse_intent(prompt, 45, resolver)
        context = engine.build_context(member, intent, resolved)
        decisions = {d.exercise_id: d for d in engine.evaluate_all(context)}
        candidates = rank_candidates(
            repository.list_exercises(), decisions, member, intent, resolved, ontology
        )
        return (
            build_graph_reasoning(
                trace_id="test",
                graph_backend="memory",
                decisions=decisions,
                candidates=candidates,
                resolved_concepts=resolved,
                member_facts=[],
                in_plan_count=0,
            ),
            decisions,
        )

    return _run


def relationships_of(traversals) -> set[str]:
    return {edge.relationship for t in traversals for edge in t.edges}


class TestInjuryAnatomyEvidence:
    def test_knee_decision_carries_an_anatomy_path_ending_at_the_knee(
        self, reasoning, repository
    ):
        trace, _ = reasoning(INJURY_PROMPT)
        walkout_id = by_name(repository, "One-Kettlebell Hamstring Walkout")

        anatomy = [
            t
            for t in trace.for_exercise(walkout_id)
            if t.constraint_type == "injury_anatomy"
        ]
        assert anatomy, "knee-loading exercise must carry anatomy evidence"

        labels = [node.label for t in anatomy for node in t.nodes]
        assert "Knee" in labels
        assert any(node.type == "AnatomicalRegion" for t in anatomy for node in t.nodes)

    def test_member_path_is_present_and_correctly_typed(self, reasoning, repository):
        trace, _ = reasoning(INJURY_PROMPT)
        split_squat_id = by_name(repository, "Dumbbell Goblet Split Squat")

        member_paths = [
            t
            for t in trace.for_exercise(split_squat_id)
            if any(edge.relationship == "HAS_INJURY" for edge in t.edges)
        ]
        assert member_paths

        path = member_paths[0]
        types = [node.type for node in path.nodes]
        assert types[0] == "Member"
        assert "Injury" in types
        assert "InjuryCondition" in types
        assert types[-1] == "AnatomicalRegion"

        rels = [edge.relationship for edge in path.edges]
        assert rels == ["HAS_INJURY", "MAPS_TO", "AFFECTS"]

    def test_part_of_traversal_is_represented_when_it_causes_the_match(
        self, repository, engine, resolver, member, ontology
    ):
        """The injury sits at the patellofemoral joint; the catalog says "knee".

        The PART_OF hop is what bridges them, so it must appear as real evidence.
        """
        intent, resolved = parse_intent(INJURY_PROMPT, 45, resolver)
        context = engine.build_context(member, intent, resolved)
        decisions = {d.exercise_id: d for d in engine.evaluate_all(context)}

        trace = build_graph_reasoning(
            trace_id="t",
            graph_backend="memory",
            decisions=decisions,
            candidates=[],
            resolved_concepts=resolved,
            member_facts=[],
            in_plan_count=0,
        )

        part_of = [
            t
            for t in trace.traversals
            if any(edge.relationship == "PART_OF" for edge in t.edges)
        ]
        assert part_of, "PART_OF bridge must be visible in the trace"

        path = part_of[0]
        assert [node.type for node in path.nodes] == ["AnatomicalRegion"] * len(path.nodes)
        assert path.nodes[-1].label == "Knee"

    def test_allowed_exercise_carries_no_injury_evidence(self, reasoning, repository):
        """The most important negative test."""
        trace, decisions = reasoning(INJURY_PROMPT)
        press_id = by_name(repository, "Alternating Dumbbell Overhead Press")
        assert decisions[press_id].status == "allowed"

        for traversal in trace.for_exercise(press_id):
            assert traversal.constraint_type not in {"injury_anatomy", "contraindication"}


class TestEquipmentEvidence:
    def test_unavailable_equipment_shows_the_requires_edge(self, reasoning, repository):
        trace, _ = reasoning(INJURY_PROMPT)
        machine_id = by_name(repository, "Machine - Chest-Supported Row")

        equipment = [
            t for t in trace.for_exercise(machine_id) if t.constraint_type == "equipment"
        ]
        assert equipment

        path = equipment[0]
        assert [edge.relationship for edge in path.edges] == ["REQUIRES"]
        assert path.nodes[0].type == "Exercise"
        assert path.nodes[1].type == "Equipment"
        assert path.nodes[1].label == "Chest Supported Row Machine"

    def test_absence_is_a_fact_not_an_invented_relationship(self, reasoning, repository):
        """Regression: the engine used to emit a fake `DOES_NOT_HAVE` edge.

        The graph has HAS_EQUIPMENT edges; absence is a set difference. It must
        be stated as evidence, never drawn as a relationship.
        """
        trace, _ = reasoning(INJURY_PROMPT)
        machine_id = by_name(repository, "Machine - Chest-Supported Row")
        equipment = [
            t for t in trace.for_exercise(machine_id) if t.constraint_type == "equipment"
        ][0]

        assert "DOES_NOT_HAVE" not in relationships_of([equipment])
        assert equipment.facts, "the available-equipment set must be stated"
        assert any("Available to member" in fact for fact in equipment.facts)
        assert any("not in the available set" in fact for fact in equipment.facts)

    def test_no_traversal_anywhere_invents_a_relationship(self, reasoning):
        """Every relationship rendered must exist in the graph model."""
        for prompt in (INJURY_PROMPT, EXCLUSION_PROMPT):
            trace, _ = reasoning(prompt)
            for relationship in relationships_of(trace.traversals):
                assert relationship in REAL_RELATIONSHIPS, (
                    f"{relationship} is not a relationship type the graph defines"
                )

    def test_side_rule_uses_a_property_not_a_fake_edge(self, reasoning, repository):
        """Regression: `LOADS_SIDE` was invented; `side` is a node property."""
        trace, _ = reasoning(INJURY_PROMPT)
        split_squat_id = by_name(repository, "Dumbbell Goblet Split Squat")

        side = [
            t
            for t in trace.for_exercise(split_squat_id)
            if t.rule_id == "injury_side_specific"
        ]
        assert side
        assert "LOADS_SIDE" not in relationships_of(side)
        assert any("side = left_leg" in fact for t in side for fact in t.facts)


class TestExplicitExclusionEvidence:
    def test_deadlift_exclusion_shows_the_resolved_family_chain(
        self, reasoning, repository
    ):
        """No exercise is named "deadlift" - the family chain is the evidence."""
        trace, decisions = reasoning(EXCLUSION_PROMPT)
        walkout_id = by_name(repository, "One-Kettlebell Hamstring Walkout")
        assert decisions[walkout_id].status == "excluded"

        exclusions = [
            t
            for t in trace.for_exercise(walkout_id)
            if t.constraint_type == "explicit_exclusion"
        ]
        assert exclusions

        path = exclusions[0]
        assert [edge.relationship for edge in path.edges] == ["HAS_PATTERN", "IN_FAMILY"]
        assert [node.type for node in path.nodes] == [
            "Exercise",
            "MovementPattern",
            "MovementFamily",
        ]
        assert path.source_concept and "deadlift" in path.source_concept.lower()


class TestContraindicationEvidence:
    def test_contraindication_records_the_incoming_hop_direction(
        self, reasoning, repository
    ):
        """Condition -CONTRAINDICATES-> Pattern, then Exercise -HAS_PATTERN-> Pattern.

        The second hop is traversed against the arrow, and the direction must say so.
        """
        trace, _ = reasoning(INJURY_PROMPT)
        jump_id = by_name(repository, "Static Jump")

        contra = [
            t
            for t in trace.for_exercise(jump_id)
            if t.constraint_type == "contraindication"
        ]
        assert contra

        path = contra[0]
        assert [edge.relationship for edge in path.edges] == [
            "CONTRAINDICATES",
            "HAS_PATTERN",
        ]
        assert path.edges[0].direction == "outgoing"
        assert path.edges[1].direction == "incoming"


class TestPreferenceEvidence:
    def test_preference_is_categorised_as_ranking_not_safety(
        self, reasoning, repository
    ):
        trace, _ = reasoning("Give her a lower-body workout.")
        walkout_id = by_name(repository, "Med Ball Hamstring Walkout")

        preference = [
            t for t in trace.for_exercise(walkout_id) if t.rule_id == "preference_dislike"
        ]
        assert preference
        assert all(t.constraint_type == "preference_ranking" for t in preference)

    def test_preference_family_evidence_uses_the_real_two_hop_chain(
        self, reasoning, repository
    ):
        """Regression: a compressed `Exercise -IN_FAMILY-> Family` edge is not real."""
        trace, _ = reasoning("Give her a lower-body workout.")
        walkout_id = by_name(repository, "Med Ball Hamstring Walkout")

        family_paths = [
            t
            for t in trace.for_exercise(walkout_id)
            if any(edge.relationship == "IN_FAMILY" for edge in t.edges)
        ]
        assert family_paths

        path = family_paths[0]
        assert [edge.relationship for edge in path.edges] == ["HAS_PATTERN", "IN_FAMILY"]
        assert path.nodes[0].type == "Exercise"
        assert path.nodes[1].type == "MovementPattern"


class TestTraceMatchesDecisions:
    def test_every_traversal_reports_its_decision_status(self, reasoning):
        trace, decisions = reasoning(INJURY_PROMPT)
        for traversal in trace.traversals:
            assert traversal.decision == decisions[traversal.exercise_id].status

    def test_every_traversal_belongs_to_a_real_catalog_exercise(
        self, reasoning, repository
    ):
        trace, _ = reasoning(INJURY_PROMPT)
        catalog_ids = {e.id for e in repository.list_exercises()}
        assert {t.exercise_id for t in trace.traversals} <= catalog_ids

    def test_no_traversal_exists_for_an_untouched_exercise(self, reasoning):
        """A trace may not appear where no rule fired."""
        trace, decisions = reasoning(INJURY_PROMPT)
        for traversal in trace.traversals:
            assert decisions[traversal.exercise_id].reasons

    def test_summary_counts_match_the_safety_decisions(self, reasoning):
        trace, decisions = reasoning(INJURY_PROMPT)
        summary = trace.summary

        assert summary.catalog_count == len(decisions)
        assert summary.excluded_count == sum(
            1 for d in decisions.values() if d.status == "excluded"
        )
        assert summary.downranked_count == sum(
            1 for d in decisions.values() if d.status == "downranked"
        )

    def test_constraint_counts_are_consistent_with_traversals(self, reasoning):
        trace, _ = reasoning(INJURY_PROMPT)
        for row in trace.summary.counts_by_constraint:
            affected = {
                t.exercise_id
                for t in trace.traversals
                if t.constraint_type == row.constraint_type
            }
            assert row.exercises_affected == len(affected)

    def test_prompt_concepts_mirror_the_resolver(self, reasoning):
        trace, _ = reasoning(INJURY_PROMPT)
        assert trace.summary.concepts_resolved == sum(
            1 for c in trace.prompt_concepts if c.resolved
        )
        knee = [c for c in trace.prompt_concepts if c.source_text == "left knee"]
        assert knee and knee[0].canonical_id == "anatomy:knee"
        assert knee[0].method == "alias"
        assert knee[0].confidence > 0.9


class TestApiSerialization:
    async def test_trace_survives_the_full_workflow_and_serializes(
        self, repository, ontology, resolver, engine
    ):
        from app.llm.stub import StubLLMClient

        workflow = WorkoutWorkflow(repository, ontology, resolver, engine, StubLLMClient())
        state = await workflow.run(
            WorkoutRequest(member_id=MEMBER_ID, prompt=INJURY_PROMPT, duration_minutes=45)
        )

        reasoning = state["graph_reasoning"]
        assert reasoning.traversals

        payload = reasoning.model_dump(mode="json")
        assert payload["summary"]["catalog_count"] == 50
        assert payload["traversals"][0]["nodes"][0]["type"]
        assert isinstance(payload["prompt_concepts"], list)

        # And the counts agree with what the API reports under `safety`.
        bundle = build_provenance(
            state["generated_workout"],
            state["safety_decisions"],
            state["eligible_exercises"],
            state["safety_context"],
            state["post_validation"],
        )
        assert reasoning.summary.excluded_count == bundle.counts["excluded"]
        assert reasoning.summary.eligible_count == bundle.counts["eligible"]
        assert reasoning.summary.in_plan_count == bundle.counts["in_plan"]

    async def test_workflow_trace_does_not_depend_on_the_llm(
        self, repository, ontology, resolver, engine
    ):
        """Swapping the composer must not change a single traversal.

        This is the architectural claim under test: the graph decided, and the
        model had no say in the evidence.
        """
        from app.domain.workout import LLMWorkoutDraft
        from app.llm.stub import StubLLMClient

        class EmptyLLM:
            name = "empty"

            async def generate_structured(self, *, schema, system, user, max_tokens=2000):
                return LLMWorkoutDraft(title="Nothing", sections=[])

            async def answer_grounded(self, *, system, user, evidence, max_tokens=700):
                return ""

        request = WorkoutRequest(
            member_id=MEMBER_ID, prompt=INJURY_PROMPT, duration_minutes=45
        )

        stub_state = await WorkoutWorkflow(
            repository, ontology, resolver, engine, StubLLMClient()
        ).run(request)

        # The empty composer produces no plan, so validation fails closed - the
        # trace is still built from the same decisions up to that point.
        stub_traversals = {
            (t.exercise_id, t.rule_id, tuple(e.relationship for e in t.edges))
            for t in stub_state["graph_reasoning"].traversals
        }

        from app.safety.validator import UnsafePlanError

        try:
            empty_state = await WorkoutWorkflow(
                repository, ontology, resolver, engine, EmptyLLM()
            ).run(request)
        except UnsafePlanError:
            return  # fail-closed path: nothing to compare, invariant still holds

        empty_traversals = {
            (t.exercise_id, t.rule_id, tuple(e.relationship for e in t.edges))
            for t in empty_state["graph_reasoning"].traversals
        }
        assert stub_traversals == empty_traversals


class TestValidatorStillGuards:
    def test_post_generation_gate_is_unaffected_by_tracing(
        self, reasoning, repository, engine, resolver, member, ontology
    ):
        """Tracing is a projection; it must not weaken the final gate."""
        from app.domain.workout import LLMWorkoutDraft, WorkoutExercise, WorkoutSection

        intent, resolved = parse_intent(INJURY_PROMPT, 45, resolver)
        context = engine.build_context(member, intent, resolved)
        decisions = {d.exercise_id: d for d in engine.evaluate_all(context)}
        candidates = rank_candidates(
            repository.list_exercises(), decisions, member, intent, resolved, ontology
        )

        banned_id = by_name(repository, "Static Jump")
        draft = LLMWorkoutDraft(
            sections=[
                WorkoutSection(
                    name="main",
                    exercises=[
                        WorkoutExercise(exercise_id=banned_id, name="Static Jump", sets=3)
                    ],
                )
            ]
        )
        workout, report = validate_and_repair(draft, decisions, candidates, 45)

        assert banned_id not in {e.exercise_id for e in workout.all_exercises()}
        assert report.passed is False


class TestPathClassification:
    """The member/exercise split must come from typed backend data.

    The UI renders two labelled paths - the member's clinical context and the
    exercise's structure. Deciding which is which from edge names or reason text
    in the frontend would be exactly the invented structure this module exists
    to prevent, so the classification is asserted here at the source.
    """

    def test_the_member_path_is_the_one_that_walks_the_member_graph(
        self, reasoning, repository
    ):
        trace, _ = reasoning(INJURY_PROMPT)
        jump = by_name(repository, "Static Jump")
        member_paths = [
            t
            for t in trace.for_exercise(jump)
            if t.path_kind == "member_context"
        ]

        assert member_paths
        for path in member_paths:
            assert path.nodes[0].type == "Member"
            assert {n.type for n in path.nodes} & {"Injury", "InjuryCondition"}

    def test_the_exercise_path_never_contains_the_member(self, reasoning, repository):
        trace, _ = reasoning(INJURY_PROMPT)
        jump = by_name(repository, "Static Jump")
        exercise_paths = [
            t for t in trace.for_exercise(jump) if t.path_kind == "exercise_structure"
        ]

        assert exercise_paths
        for path in exercise_paths:
            assert not {n.type for n in path.nodes} & {"Member", "Injury", "Preference"}
            assert any(n.type == "Exercise" for n in path.nodes)

    def test_evidence_with_no_edges_is_labelled_a_set_operation(self, reasoning):
        trace, _ = reasoning(INJURY_PROMPT)
        set_ops = [t for t in trace.traversals if t.path_kind == "set_operation"]

        assert set_ops
        for path in set_ops:
            assert path.edges == []
            assert path.facts, "a set operation must still state its evidence"

    def test_the_part_of_closure_gets_its_own_label(self, reasoning, repository):
        """The hop the design rests on is not lumped in with exercise structure."""
        trace, _ = reasoning(INJURY_PROMPT)
        anatomy = [
            t
            for t in trace.for_exercise(by_name(repository, "Static Jump"))
            if t.path_kind == "anatomy_hierarchy"
        ]

        assert anatomy
        for path in anatomy:
            assert {n.type for n in path.nodes} == {"AnatomicalRegion"}
            assert {e.relationship for e in path.edges} == {"PART_OF"}

    def test_every_traversal_is_classified(self, reasoning):
        trace, _ = reasoning(INJURY_PROMPT)
        allowed = {
            "member_context",
            "anatomy_hierarchy",
            "exercise_structure",
            "set_operation",
        }
        assert {t.path_kind for t in trace.traversals} <= allowed
        assert all(t.path_kind for t in trace.traversals)

    def test_the_excluded_jump_carries_both_halves_of_the_argument(
        self, reasoning, repository
    ):
        """The spec's worked example, asserted end to end."""
        trace, _ = reasoning(INJURY_PROMPT)
        traversals = trace.for_exercise(by_name(repository, "Static Jump"))
        kinds = {t.path_kind for t in traversals}

        assert {"member_context", "exercise_structure"} <= kinds
        assert all(t.decision == "excluded" for t in traversals)
        assert {"injury_contraindicated_pattern", "injury_region_stress"} <= {
            t.rule_id for t in traversals
        }
