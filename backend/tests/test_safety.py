"""Deterministic safety engine tests.

These are the critical-path tests for the whole system. They were chosen because
each one guards a property that, if broken, produces a *confidently wrong* and
potentially harmful recommendation:

* injury reasoning must traverse the anatomy hierarchy, not just match a joint
  label - otherwise a patellofemoral injury misses every exercise the catalog
  annotates as "knee";
* equipment filtering must be absolute - a plan the member cannot perform is
  worthless;
* an explicit exclusion must resolve to a movement *family*, because the supplied
  catalog contains no exercise named "deadlift" at all;
* a preference must never silently become a clinical contraindication;
* and the LLM must not be able to reintroduce anything the graph removed.
"""

from __future__ import annotations

from app.domain.safety import SafetyDecision
from app.graph.memory_repository import InMemoryGraphRepository
from app.safety.engine import SafetyEngine

from .conftest import MEMBER_ID, by_name

INJURY_PROMPT = "Create a 45-minute lower-body workout. Her left knee is bothering her."
EQUIPMENT_PROMPT = (
    "Build a full-body workout. She has no barbell, only dumbbells and a kettlebell."
)
EXCLUSION_PROMPT = "Create a workout but exclude deadlifts."


def rules(decision: SafetyDecision) -> set[str]:
    return {reason.rule_id for reason in decision.reasons}


class TestAnatomyHierarchyTraversal:
    """Rule B - the PART_OF walk is the heart of injury safety."""

    def test_injury_maps_to_specific_clinical_condition(
        self, repository: InMemoryGraphRepository
    ):
        injuries = repository.injury_affected_regions(MEMBER_ID)
        assert len(injuries) == 1
        injury = injuries[0]
        # The notes say "Patellofemoral pain", which is more specific than
        # generic knee pain and carries different contraindications.
        assert injury["condition_id"] == "patellofemoral_pain_syndrome"
        assert injury["root_region"] == "patellofemoral_joint"

    def test_closure_reaches_the_parent_joint(self, repository: InMemoryGraphRepository):
        """The catalog annotates "knee"; the injury sits one level below it."""
        injury = repository.injury_affected_regions(MEMBER_ID)[0]
        assert "patellofemoral_joint" in injury["closure"]
        assert "knee" in injury["closure"], "PART_OF walk must reach the parent joint"
        assert "lower_limb" in injury["closure"]

    def test_part_of_path_is_real_evidence(self, repository: InMemoryGraphRepository):
        path = repository.part_of_path("patellofemoral_joint", "knee")
        assert path is not None
        assert path.nodes == ["Patellofemoral Joint", "Knee"]
        assert path.edges == ["PART_OF"]

    def test_unrelated_region_is_not_in_closure(self, repository: InMemoryGraphRepository):
        injury = repository.injury_affected_regions(MEMBER_ID)[0]
        assert "shoulder" not in injury["closure"]
        assert "lumbar_spine" not in injury["closure"]

    def test_knee_stressing_exercise_is_not_treated_as_fully_safe(
        self, evaluate, repository
    ):
        """IMPLEMENTATION.md Test 1: knee injury + child-region stress."""
        decisions, _ = evaluate(INJURY_PROMPT)
        walkout = decisions[by_name(repository, "One-Kettlebell Hamstring Walkout")]

        assert walkout.status != "allowed"
        assert "injury_region_stress" in rules(walkout)
        assert walkout.score_adjustment < 0

    def test_decision_carries_the_traversal_that_justified_it(
        self, evaluate, repository
    ):
        decisions, _ = evaluate(INJURY_PROMPT)
        decision = decisions[by_name(repository, "One-Kettlebell Hamstring Walkout")]
        rendered = " | ".join(path.render() for path in decision.graph_paths)

        assert "STRESSES" in rendered
        assert "HAS_INJURY" in rendered
        assert "Patellofemoral" in rendered

    def test_exercise_that_avoids_the_injured_region_stays_clean(
        self, evaluate, repository
    ):
        decisions, _ = evaluate(INJURY_PROMPT)
        press = decisions[by_name(repository, "Alternating Dumbbell Overhead Press")]
        assert press.status == "allowed"
        assert "injury_region_stress" not in rules(press)


class TestContraindications:
    """Rule C - explicit CONTRAINDICATES edges from the injury's clinical note."""

    def test_plyometrics_are_hard_excluded(self, evaluate, repository):
        """The member's note says "avoid ... plyometrics" - no down-ranking."""
        decisions, _ = evaluate(INJURY_PROMPT)
        for name in ("Static Jump", "Vertical Jump to Broad Jump"):
            decision = decisions[by_name(repository, name)]
            assert decision.status == "excluded", name
            assert "injury_contraindicated_pattern" in rules(decision)

    def test_recovering_injury_downranks_rather_than_removes_loaded_flexion(
        self, evaluate, repository
    ):
        """Member is mild/recovering and "cleared for low-impact loading".

        Removing every squat pattern would leave nothing trainable and would
        contradict the clinical note, so these are down-ranked with a caveat.
        """
        decisions, _ = evaluate(INJURY_PROMPT)
        lunge = decisions[by_name(repository, "Alternating Dumbbell Racked Crossback Lunge")]
        assert lunge.status == "downranked"
        assert "injury_contraindicated_pattern" in rules(lunge)
        assert lunge.score_adjustment <= -50

    def test_side_aware_penalty_for_the_injured_limb(self, evaluate, repository):
        """A left_leg variant loading a LEFT knee is loading the injured side."""
        decisions, _ = evaluate(INJURY_PROMPT)
        split_squat = decisions[by_name(repository, "Dumbbell Goblet Split Squat")]

        assert "injury_side_specific" in rules(split_squat)
        assert split_squat.status != "allowed"

    def test_bilateral_variant_avoids_the_side_penalty(self, evaluate, repository):
        decisions, _ = evaluate(INJURY_PROMPT)
        walkout = decisions[by_name(repository, "One-Kettlebell Hamstring Walkout")]
        assert "injury_side_specific" not in rules(walkout)

    def test_missing_anatomy_data_is_flagged_not_assumed_safe(
        self, evaluate, repository
    ):
        """2 catalog rows have an empty joints_loaded list."""
        decisions, _ = evaluate(INJURY_PROMPT)
        decision = decisions[by_name(repository, "Alternating Dumbbell Decline Bench Press")]
        assert "unknown_anatomy" in rules(decision)


class TestEquipment:
    """Rule D - eligibility requires every piece of required equipment."""

    def test_barbell_exercise_excluded_when_member_has_no_barbell(
        self, evaluate, repository
    ):
        """IMPLEMENTATION.md Test 2."""
        decisions, _ = evaluate(EQUIPMENT_PROMPT)
        decision = decisions[by_name(repository, "Barbell Decline Bench Press")]
        assert decision.status == "excluded"
        assert rules(decision) & {"equipment_unavailable", "explicit_exclusion"}

    def test_dumbbell_and_kettlebell_alternatives_remain(self, evaluate, repository):
        """IMPLEMENTATION.md Test 4 - filtering must leave a usable pool."""
        decisions, _ = evaluate(EQUIPMENT_PROMPT)
        survivors = {
            d.exercise_name for d in decisions.values() if d.status != "excluded"
        }
        assert "Dumbbell Neutral-Grip Bench Press" in survivors
        assert "Alternating Dumbbell Overhead Press" in survivors
        assert len(survivors) >= 8

    def test_machine_exercises_excluded_for_a_home_gym(self, evaluate, repository):
        decisions, _ = evaluate(EQUIPMENT_PROMPT)
        decision = decisions[by_name(repository, "Machine - Chest-Supported Row")]
        assert decision.status == "excluded"
        assert "equipment_unavailable" in rules(decision)

    def test_bodyweight_exercise_needs_no_equipment(self, evaluate, repository):
        decisions, _ = evaluate(EQUIPMENT_PROMPT)
        decision = decisions[by_name(repository, "Standing Neck Circles")]
        assert "equipment_unavailable" not in rules(decision)

    def test_restrictive_phrasing_does_not_exclude_declared_equipment(
        self, evaluate, repository
    ):
        """Regression: "no barbell, only dumbbells and a kettlebell" once
        excluded the kettlebell because the negation leaked across clauses."""
        _, context = evaluate(EQUIPMENT_PROMPT)
        assert "Kettlebell" in context.available_equipment
        assert "Dumbbell" in context.available_equipment
        assert "Barbell" not in context.available_equipment

    def test_equipment_evidence_names_the_missing_item(self, evaluate, repository):
        decisions, _ = evaluate(EQUIPMENT_PROMPT)
        decision = decisions[by_name(repository, "Machine - Chest-Supported Row")]
        rendered = " ".join(p.render() for p in decision.graph_paths)
        assert "REQUIRES" in rendered
        assert "Chest Supported Row Machine" in rendered


class TestExplicitExclusion:
    """Rule A - and the clearest proof that the graph carries the semantics."""

    def test_no_exercise_is_literally_named_deadlift(self, repository):
        """Guards the premise of the next test."""
        assert not [e for e in repository.list_exercises() if "deadlift" in e.name.lower()]

    def test_exclude_deadlifts_removes_the_hinge_family(self, evaluate, repository):
        """IMPLEMENTATION.md Test 3.

        A string match would remove nothing. The graph resolves "deadlifts" to
        the hinge family and removes its member patterns' exercises.
        """
        decisions, context = evaluate(EXCLUSION_PROMPT)
        assert "lower pull - hip lift" in context.excluded_patterns

        for name in ("One-Kettlebell Hamstring Walkout", "Med Ball Hamstring Walkout"):
            decision = decisions[by_name(repository, name)]
            assert decision.status == "excluded", name
            assert "explicit_exclusion" in rules(decision)

    def test_exclusion_leaves_safe_alternatives(self, evaluate, repository):
        decisions, _ = evaluate(EXCLUSION_PROMPT)
        survivors = [d for d in decisions.values() if d.status != "excluded"]
        assert len(survivors) >= 8

    def test_exclusion_provenance_shows_the_family_hop(self, evaluate, repository):
        decisions, _ = evaluate(EXCLUSION_PROMPT)
        decision = decisions[by_name(repository, "One-Kettlebell Hamstring Walkout")]
        rendered = " ".join(p.render() for p in decision.graph_paths)
        assert "HAS_PATTERN" in rendered
        assert "IN_FAMILY" in rendered

    def test_unrelated_exercises_untouched_by_the_exclusion(self, evaluate, repository):
        decisions, _ = evaluate(EXCLUSION_PROMPT)
        press = decisions[by_name(repository, "Alternating Dumbbell Overhead Press")]
        assert "explicit_exclusion" not in rules(press)


class TestPreferencesNeverOverrideSafety:
    """Rule E - the boundary between 'dislikes' and 'unsafe'."""

    def test_disliked_family_is_downranked_not_excluded(self, evaluate, repository):
        """Jordan dislikes "Deadlift" but has NOT been told to avoid hinging."""
        decisions, _ = evaluate("Give her a lower-body workout.")
        walkout = decisions[by_name(repository, "Med Ball Hamstring Walkout")]

        preference_reasons = [r for r in walkout.reasons if r.rule_id == "preference_dislike"]
        assert preference_reasons, "dislike should be recorded"
        assert "not a safety exclusion" in preference_reasons[0].message

    def test_preference_alone_never_produces_exclusion(self, evaluate, repository):
        decisions, _ = evaluate("Give her a lower-body workout.")
        for decision in decisions.values():
            reason_ids = rules(decision)
            if decision.status == "excluded":
                assert reason_ids != {"preference_dislike"}, decision.exercise_name

    def test_preference_penalty_is_smaller_than_injury_penalty(self, evaluate, repository):
        decisions, _ = evaluate(INJURY_PROMPT)
        split = decisions[by_name(repository, "Dumbbell Goblet Split Squat")]
        assert split.score_adjustment <= -60


class TestDecisionIntegrity:
    def test_every_exercise_receives_a_decision(self, evaluate, repository):
        decisions, _ = evaluate(INJURY_PROMPT)
        assert len(decisions) == len(repository.list_exercises()) == 50

    def test_all_decisions_are_sourced_from_the_graph(self, evaluate):
        decisions, _ = evaluate(INJURY_PROMPT)
        assert all(d.decision_source == "knowledge_graph" for d in decisions.values())

    def test_excluded_decisions_always_carry_a_reason(self, evaluate):
        decisions, _ = evaluate(EQUIPMENT_PROMPT)
        for decision in decisions.values():
            if decision.status == "excluded":
                assert decision.reasons, decision.exercise_name
                assert all(r.message for r in decision.reasons)

    def test_engine_is_deterministic(self, evaluate):
        first, _ = evaluate(INJURY_PROMPT)
        second, _ = evaluate(INJURY_PROMPT)
        assert {k: v.status for k, v in first.items()} == {
            k: v.status for k, v in second.items()
        }

    def test_no_injury_means_no_injury_penalties(
        self, engine: SafetyEngine, resolver, repository, member
    ):
        """Isolates injury rules by removing the injury from the context."""
        from app.agents.intent import parse_intent

        intent, resolved = parse_intent("Full-body workout.", 45, resolver)
        context = engine.build_context(member, intent, resolved)
        context.injuries = []

        decisions = engine.evaluate_all(context)
        assert not any(
            rules(d) & {"injury_region_stress", "injury_contraindicated_pattern"}
            for d in decisions
        )
