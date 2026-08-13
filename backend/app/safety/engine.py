"""The deterministic safety engine.

This module is the authority on whether an exercise may appear in a plan. It
takes no LLM input and produces no prose: every decision is the result of a
graph traversal and every decision carries the traversal that justified it.

It runs twice per request - once to build the candidate set the LLM is allowed
to choose from, and once again after the LLM answers (see
``validate_generated_plan``). The second run is what makes safety a system
invariant rather than a prompt instruction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.exercise import Exercise
from app.domain.member import MemberContext
from app.domain.resolution import ResolvedConcept
from app.domain.safety import GraphPath, SafetyDecision, SafetyReason
from app.domain.workout import WorkoutIntent
from app.graph.repository import GraphRepository
from app.ontology.loader import Ontology
from app.safety import policies


@dataclass
class SafetyContext:
    """Everything the engine needs, all of it graph- or data-derived."""

    member: MemberContext
    intent: WorkoutIntent
    resolved_concepts: list[ResolvedConcept] = field(default_factory=list)
    available_equipment: set[str] = field(default_factory=set)
    excluded_patterns: dict[str, str] = field(default_factory=dict)
    """pattern -> the coach phrase that excluded it."""
    excluded_exercise_ids: dict[str, str] = field(default_factory=dict)
    excluded_equipment: dict[str, str] = field(default_factory=dict)
    injuries: list[dict] = field(default_factory=list)


class SafetyEngine:
    def __init__(self, repository: GraphRepository, ontology: Ontology) -> None:
        self._repo = repository
        self._ontology = ontology

    # --- context assembly -------------------------------------------------

    def build_context(
        self,
        member: MemberContext,
        intent: WorkoutIntent,
        resolved_concepts: list[ResolvedConcept],
    ) -> SafetyContext:
        member_id = member.profile.id
        context = SafetyContext(
            member=member,
            intent=intent,
            resolved_concepts=resolved_concepts,
            injuries=self._repo.injury_affected_regions(member_id),
        )

        context.available_equipment = self._resolve_available_equipment(
            member_id, intent, resolved_concepts
        )
        self._resolve_exclusions(intent, resolved_concepts, context)
        return context

    def _resolve_available_equipment(
        self,
        member_id: str,
        intent: WorkoutIntent,
        resolved: list[ResolvedConcept],
    ) -> set[str]:
        """Equipment the member can actually use for this session.

        The member graph is the baseline. When the coach phrases equipment as a
        closed set ("she only has dumbbells and a kettlebell"), that *narrows*
        the baseline for this request - bodyweight-only items the member owns
        (mat, bench) are retained because they are not what "only" is excluding.
        """
        baseline = self._repo.member_equipment(member_id)
        # Only equipment the coach declared as *available* counts here. Items
        # that landed in the exclusion bucket ("no barbell") must never be
        # re-admitted as availability just because they were mentioned.
        declared = {text.lower() for text in intent.equipment_mentions}
        mentioned = {
            concept.label
            for concept in resolved
            if concept.is_resolved
            and concept.concept_type == "equipment"
            and concept.label
            and concept.source_text.lower() in declared
        }
        if not intent.equipment_is_restrictive or not mentioned:
            return baseline | mentioned

        # "Only X and Y": keep the named items plus non-resistance staples.
        staples = {e for e in baseline if e in {"Yoga Mat", "Flat Bench"}}
        return (mentioned & baseline) | (mentioned - baseline) | staples

    def _resolve_exclusions(
        self,
        intent: WorkoutIntent,
        resolved: list[ResolvedConcept],
        context: SafetyContext,
    ) -> None:
        """Turn coach exclusion phrases into concrete graph targets.

        "Exclude deadlifts" is the interesting case: the supplied catalog has
        **no exercise whose name contains "deadlift"**, so string matching finds
        nothing at all. The phrase resolves to the hinge movement family, and
        the graph expands that family into the concrete patterns - and therefore
        the concrete exercises - that must be removed.
        """
        by_text = {c.source_text.lower(): c for c in resolved}

        for phrase in intent.explicit_exclusions:
            concept = by_text.get(phrase.lower())
            if concept is None or not concept.is_resolved:
                continue

            assert concept.canonical_id is not None
            kind, _, identifier = concept.canonical_id.partition(":")

            if kind == "movement_family":
                for pattern in self._repo.patterns_in_family(identifier):
                    context.excluded_patterns[pattern] = phrase
            elif kind == "equipment":
                context.excluded_equipment[concept.label or identifier] = phrase
            elif kind == "exercise":
                context.excluded_exercise_ids[identifier] = phrase

    # --- evaluation -------------------------------------------------------

    def evaluate_all(self, context: SafetyContext) -> list[SafetyDecision]:
        return [self.evaluate(exercise, context) for exercise in self._repo.list_exercises()]

    def evaluate(self, exercise: Exercise, context: SafetyContext) -> SafetyDecision:
        decision = SafetyDecision(
            exercise_id=exercise.id,
            exercise_name=exercise.name,
            status="allowed",
            decision_source="knowledge_graph",
        )

        self._rule_explicit_exclusion(exercise, context, decision)
        self._rule_equipment(exercise, context, decision)
        self._rule_injury(exercise, context, decision)
        self._rule_preferences(exercise, context, decision)

        return decision

    # --- Rule A: explicit exclusions --------------------------------------

    def _rule_explicit_exclusion(
        self, exercise: Exercise, context: SafetyContext, decision: SafetyDecision
    ) -> None:
        if exercise.id in context.excluded_exercise_ids:
            phrase = context.excluded_exercise_ids[exercise.id]
            decision.status = "excluded"
            decision.reasons.append(
                SafetyReason(
                    rule_id="explicit_exclusion",
                    message=f'Coach explicitly excluded this exercise ("{phrase}").',
                    graph_paths=[
                        GraphPath(
                            nodes=[exercise.name],
                            edges=[],
                            node_kinds=["Exercise"],
                            facts=[
                                f'Coach phrase "{phrase}" resolved directly to this exercise.'
                            ],
                        )
                    ],
                )
            )
            return

        for pattern in self._repo.exercise_patterns(exercise.id):
            if pattern not in context.excluded_patterns:
                continue
            phrase = context.excluded_patterns[pattern]
            family = self._ontology.family_for_pattern(pattern)
            family_label = family.label if family else pattern
            decision.status = "excluded"
            decision.reasons.append(
                SafetyReason(
                    rule_id="explicit_exclusion",
                    message=(
                        f'Coach excluded "{phrase}", which resolves to the '
                        f"{family_label}; this exercise belongs to that family."
                    ),
                    graph_paths=[
                        GraphPath(
                            nodes=[exercise.name, pattern, family_label],
                            edges=["HAS_PATTERN", "IN_FAMILY"],
                            node_kinds=["Exercise", "MovementPattern", "MovementFamily"],
                            edge_directions=["outgoing", "outgoing"],
                            facts=[
                                f'Coach phrase "{phrase}" resolved to the {family_label}.'
                            ],
                        )
                    ],
                )
            )
            return

    # --- Rule D: equipment -------------------------------------------------

    def _rule_equipment(
        self, exercise: Exercise, context: SafetyContext, decision: SafetyDecision
    ) -> None:
        required = self._repo.exercise_required_equipment(exercise.id)
        if not required:
            return  # bodyweight

        missing = [item for item in required if item not in context.available_equipment]
        explicitly_banned = [item for item in required if item in context.excluded_equipment]

        if explicitly_banned:
            item = explicitly_banned[0]
            decision.status = "excluded"
            decision.reasons.append(
                SafetyReason(
                    rule_id="explicit_exclusion",
                    message=(
                        f'Requires {item}, which the coach excluded '
                        f'("{context.excluded_equipment[item]}").'
                    ),
                    graph_paths=[
                        GraphPath(
                            nodes=[exercise.name, item],
                            edges=["REQUIRES"],
                            node_kinds=["Exercise", "Equipment"],
                            edge_directions=["outgoing"],
                            facts=[
                                f'Coach excluded "{context.excluded_equipment[item]}".'
                            ],
                        )
                    ],
                )
            )
            return

        if missing:
            item = missing[0]
            decision.status = "excluded"
            decision.reasons.append(
                SafetyReason(
                    rule_id="equipment_unavailable",
                    message=f"Requires {item}, which {context.member.profile.name} does not have.",
                    # Only ONE real traversal exists here: the exercise's REQUIRES
                    # edge. Absence of equipment is a set difference over the
                    # member's HAS_EQUIPMENT edges, not a relationship - so it is
                    # stated as a deterministic fact rather than drawn as a fake
                    # "DOES_NOT_HAVE" edge the graph does not contain.
                    graph_paths=[
                        GraphPath(
                            nodes=[exercise.name, item],
                            edges=["REQUIRES"],
                            node_kinds=["Exercise", "Equipment"],
                            edge_directions=["outgoing"],
                            facts=[
                                f"Required: {', '.join(required)}.",
                                "Available to member ("
                                f"{context.member.profile.name}): "
                                f"{', '.join(sorted(context.available_equipment)) or 'none'}.",
                                f"{item} is not in the available set.",
                            ],
                        )
                    ],
                )
            )

    # --- Rules B & C: injury anatomy and contraindications -----------------

    def _rule_injury(
        self, exercise: Exercise, context: SafetyContext, decision: SafetyDecision
    ) -> None:
        if not context.injuries:
            return

        patterns = self._repo.exercise_patterns(exercise.id)
        stressed = self._repo.exercise_stressed_regions(exercise.id)

        for injury in context.injuries:
            closure: set[str] = injury["closure"]
            hit_regions = [region for region in stressed if region in closure]

            # Rule C - explicit contraindication on a movement pattern.
            contraindicated = [p for p in patterns if p in injury["contraindicated_patterns"]]
            if contraindicated:
                self._apply_contraindication(
                    exercise, injury, contraindicated[0], decision, context
                )

            # Rule B - anatomical stress inside the injured region's closure.
            if hit_regions:
                self._apply_region_stress(exercise, injury, hit_regions[0], decision)

            # Side-aware escalation: a left_leg variant loading an injured LEFT
            # knee is loading the injured limb specifically.
            if hit_regions and self._loads_injured_side(exercise, injury):
                decision.score_adjustment += policies.PENALTY_INJURED_SIDE
                decision.reasons.append(
                    SafetyReason(
                        rule_id="injury_side_specific",
                        message=(
                            f"Unilateral variant loads the {injury['body_side']} side, which is "
                            f"the injured side ({injury['injury_name']})."
                        ),
                        # `side` is a PROPERTY on the Exercise node, not a
                        # relationship, so it is carried as a node property and a
                        # fact. The only real traversal backing this rule is the
                        # member's injury path, which establishes the injured side.
                        graph_paths=[
                            GraphPath(
                                nodes=[exercise.name],
                                edges=[],
                                node_kinds=["Exercise"],
                                facts=[
                                    f"Exercise property side = {exercise.side}.",
                                    f"Injury laterality = {injury['body_side']}.",
                                    "Unilateral variant loads the injured side.",
                                ],
                            ),
                            injury["member_path"],
                        ],
                    )
                )
                if decision.status == "allowed":
                    decision.status = "downranked"

            # Missing anatomy data: cannot certify, so do not pretend.
            if not exercise.has_anatomy_data:
                decision.score_adjustment += policies.PENALTY_UNKNOWN_ANATOMY
                decision.reasons.append(
                    SafetyReason(
                        rule_id="unknown_anatomy",
                        message=(
                            "Catalog lists no joints for this exercise, so it cannot be "
                            "certified against the member's injury. Down-ranked as a precaution."
                        ),
                        # There is genuinely no traversal here - that absence IS
                        # the finding. Stating it as a fact keeps the data gap
                        # visible instead of letting the exercise appear
                        # evidence-free and therefore unexamined.
                        graph_paths=[
                            GraphPath(
                                nodes=[exercise.name],
                                edges=[],
                                node_kinds=["Exercise"],
                                facts=[
                                    "Catalog lists no joints_loaded for this exercise.",
                                    "No STRESSES edges exist, so no anatomy traversal is possible.",
                                    f"Cannot be certified against {injury['injury_name']}.",
                                ],
                            )
                        ],
                    )
                )
                if decision.status == "allowed":
                    decision.status = "downranked"

    def _apply_contraindication(
        self,
        exercise: Exercise,
        injury: dict,
        pattern: str,
        decision: SafetyDecision,
        context: SafetyContext,
    ) -> None:
        family = self._ontology.family_for_pattern(pattern)
        family_id = family.id if family else ""
        policy = policies.policy_for(injury.get("severity"), injury.get("status"))

        # Read against the arrow on the second hop: the graph stores
        # Exercise -HAS_PATTERN-> Pattern, so reaching the exercise from the
        # pattern traverses that edge incoming. Recording the direction keeps the
        # rendered path honest about the real topology.
        path = GraphPath(
            nodes=[
                injury["condition_label"] or injury["injury_name"],
                pattern,
                exercise.name,
            ],
            edges=["CONTRAINDICATES", "HAS_PATTERN"],
            node_kinds=["InjuryCondition", "MovementPattern", "Exercise"],
            edge_directions=["outgoing", "incoming"],
        )

        always_excluded = family_id in policies.ALWAYS_EXCLUDED_FAMILIES
        if always_excluded or policy.hard_exclude_contraindicated:
            decision.status = "excluded"
            decision.reasons.append(
                SafetyReason(
                    rule_id="injury_contraindicated_pattern",
                    message=(
                        f"{injury['condition_label']} contraindicates the "
                        f"'{pattern}' pattern."
                    ),
                    graph_paths=[path, injury["member_path"]],
                )
            )
            return

        # Recovering / mild: keep it available but heavily down-ranked and
        # flagged, matching the member's "cleared for low-impact loading" note.
        decision.score_adjustment += policy.penalty_contraindicated
        if decision.status == "allowed":
            decision.status = "downranked"
        decision.reasons.append(
            SafetyReason(
                rule_id="injury_contraindicated_pattern",
                message=(
                    f"{injury['condition_label']} cautions against the '{pattern}' pattern; "
                    f"injury is {injury.get('severity')}/{injury.get('status')}, so this is "
                    "down-ranked and needs a range-of-motion caveat rather than removed."
                ),
                graph_paths=[path, injury["member_path"]],
            )
        )

    def _apply_region_stress(
        self, exercise: Exercise, injury: dict, region: str, decision: SafetyDecision
    ) -> None:
        patterns = self._repo.exercise_patterns(exercise.id)
        low_load = all(policies.is_low_load_pattern(p) for p in patterns) if patterns else False
        loaded = exercise.supports_weight and not low_load

        penalty = (
            policies.PENALTY_LOADED_INJURY_REGION
            if loaded
            else policies.PENALTY_UNLOADED_INJURY_REGION
        )
        decision.score_adjustment += penalty
        if decision.status == "allowed":
            decision.status = "downranked"

        paths: list[GraphPath] = []
        stresses_path = self._repo.stresses_path(exercise.id, region)
        if stresses_path:
            paths.append(stresses_path)

        # The PART_OF chain is the point of the whole exercise: the injury sits
        # at a sub-structure while the catalog annotates the parent joint.
        root = injury["root_region"]
        if root != region:
            part_of = self._repo.part_of_path(root, region)
            if part_of:
                paths.append(part_of)
        paths.append(injury["member_path"])

        decision.reasons.append(
            SafetyReason(
                rule_id="injury_region_stress",
                message=(
                    f"{'Loaded' if loaded else 'Low-load'} exercise stresses "
                    f"{region.replace('_', ' ')}, which is inside the region affected by "
                    f"{injury['injury_name']}."
                ),
                graph_paths=paths,
            )
        )

    @staticmethod
    def _loads_injured_side(exercise: Exercise, injury: dict) -> bool:
        injured_side = injury.get("body_side")
        if not injured_side or not exercise.side:
            return False
        return exercise.loaded_body_side == injured_side

    # --- Rule E: preferences ----------------------------------------------

    def _rule_preferences(
        self, exercise: Exercise, context: SafetyContext, decision: SafetyDecision
    ) -> None:
        """Preferences change ranking. They never become safety exclusions.

        A member disliking an exercise is not a clinical contraindication, and
        conflating the two would let a preference silently masquerade as a
        safety decision in the provenance trace.
        """
        dislikes = context.member.preferences.dislikes
        if not dislikes:
            return

        name = exercise.name.lower()
        patterns = self._repo.exercise_patterns(exercise.id)

        for dislike in dislikes:
            token = dislike.strip().lower()
            if not token:
                continue

            matched_by_name = token in name
            matched_by_family = False
            family = None
            matched_pattern = None
            for pattern in patterns:
                candidate = self._ontology.family_for_pattern(pattern)
                if candidate and token in candidate.aliases:
                    matched_by_family = True
                    family = candidate
                    matched_pattern = pattern
                    break

            if not (matched_by_name or matched_by_family):
                continue

            decision.score_adjustment += policies.PENALTY_PREFERENCE_DISLIKE
            if decision.status == "allowed":
                decision.status = "downranked"
            decision.reasons.append(
                SafetyReason(
                    rule_id="preference_dislike",
                    message=(
                        f'{context.member.profile.name} dislikes "{dislike}". '
                        "Preference affects ranking only - this is not a safety exclusion."
                    ),
                    graph_paths=[
                        GraphPath(
                            nodes=[context.member.profile.name, dislike],
                            edges=["DISLIKES"],
                            node_kinds=["Member", "Preference"],
                            edge_directions=["outgoing"],
                        )
                    ]
                    # The catalog links Exercise -HAS_PATTERN-> Pattern
                    # -IN_FAMILY-> Family. Render both hops rather than a
                    # single compressed Exercise -> Family edge, which does not
                    # exist in the graph.
                    + (
                        [
                            GraphPath(
                                nodes=[exercise.name, matched_pattern, family.label],
                                edges=["HAS_PATTERN", "IN_FAMILY"],
                                node_kinds=[
                                    "Exercise",
                                    "MovementPattern",
                                    "MovementFamily",
                                ],
                                edge_directions=["outgoing", "outgoing"],
                            )
                        ]
                        if family and matched_pattern
                        else []
                    ),
                )
            )
            return
