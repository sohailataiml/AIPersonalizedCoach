"""The evaluation corpus.

Cases are **data**, not code: each declares its inputs and its deterministic
expectations, and the runner knows how to execute each kind. That separation is
what makes the suite reviewable - a clinician or a reviewer can read what the
system is expected to do without reading the harness.

Two rules the corpus follows:

* **Expectations are exact where the data allows it.** "Static Jump is excluded
  by injury_contraindicated_pattern" is checkable; "the plan looks sensible" is
  not, so it is not a case.
* **Negative cases carry the weight.** A suite that only asserts good paths
  measures nothing about the failure modes that matter: an unresolved phrase
  being force-matched, an excluded exercise surviving composition, a
  personalization signal outranking an injury.

All inputs are synthetic and derive from the supplied member and catalog.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.evaluation import EvaluationCategory

BASE_INJURY_PROMPT = (
    "Create a 45-minute lower-body workout. Her left knee is bothering her."
)
BASE_EQUIPMENT_PROMPT = (
    "Build a full-body workout. She has no barbell, only dumbbells and a kettlebell."
)
BASE_ADJUSTMENT_PROMPT = (
    "Create a 45-minute lower-body workout. Her left knee is bothering her "
    "and she only has dumbbells and a kettlebell."
)


@dataclass(frozen=True)
class EvalCase:
    id: str
    category: EvaluationCategory
    name: str
    kind: str
    """Dispatch key for the runner."""
    input_summary: str
    expectation: str
    params: dict = field(default_factory=dict)


# --- concept resolution ------------------------------------------------------
# Covers every resolver pass plus the two failure modes that matter: a phrase
# that must NOT resolve, and one that must not be force-matched onto a clinical
# concept.

RESOLUTION_CASES = [
    EvalCase(
        id="res-exact-kettlebell",
        category="concept_resolution",
        name="Exact label match",
        kind="resolve",
        input_summary='"kettlebell"',
        expectation="equipment:kettlebell via exact, confidence 1.0",
        params={"text": "kettlebell", "canonical_id": "equipment:kettlebell",
                "method": "exact", "min_confidence": 1.0},
    ),
    EvalCase(
        id="res-alias-db",
        category="concept_resolution",
        name="Coach shorthand reaches the canonical item",
        kind="resolve",
        # "DBs" normalises onto the canonical label itself, so the resolver
        # reports `exact` rather than `alias`. The method is not asserted here;
        # res-alias-knee covers the alias pass specifically.
        input_summary='"DBs"',
        expectation="equipment:dumbbell with confidence >= 0.98",
        params={"text": "DBs", "canonical_id": "equipment:dumbbell",
                "min_confidence": 0.98},
    ),
    EvalCase(
        id="res-alias-equipment",
        category="concept_resolution",
        name="Curated equipment alias",
        kind="resolve",
        input_summary='"dumbbells"',
        expectation="equipment:dumbbell via alias (0.98)",
        params={"text": "dumbbells", "canonical_id": "equipment:dumbbell",
                "method": "alias", "min_confidence": 0.98},
    ),
    EvalCase(
        id="res-alias-knee",
        category="concept_resolution",
        name="Anatomy alias with laterality",
        kind="resolve",
        input_summary='"left knee"',
        expectation="anatomy:knee via alias",
        params={"text": "left knee", "canonical_id": "anatomy:knee", "method": "alias"},
    ),
    EvalCase(
        id="res-alias-deadlift-family",
        category="concept_resolution",
        name="Movement family alias",
        kind="resolve",
        input_summary='"deadlifts"',
        expectation="movement_family:hinge via alias",
        params={"text": "deadlifts", "canonical_id": "movement_family:hinge",
                "method": "alias"},
    ),
    EvalCase(
        id="res-fuzzy-typo",
        category="concept_resolution",
        name="Fuzzy typo",
        kind="resolve",
        input_summary='"kettlebel"',
        expectation="equipment:kettlebell via fuzzy",
        params={"text": "kettlebel", "canonical_id": "equipment:kettlebell",
                "method": "fuzzy"},
    ),
    EvalCase(
        id="res-fuzzy-plural",
        category="concept_resolution",
        name="Morphological variant",
        kind="resolve",
        input_summary='"patellofemoral pain syndrome"',
        expectation="injury:patellofemoral_pain_syndrome",
        params={"text": "patellofemoral pain syndrome",
                "canonical_id": "injury:patellofemoral_pain_syndrome"},
    ),
    EvalCase(
        id="res-vector-fallback",
        category="concept_resolution",
        name="Lexical-vector fallback",
        kind="resolve_with_thresholds",
        input_summary='"dumbell" with fuzzy disabled',
        expectation="equipment:dumbbell via embedding",
        params={"text": "dumbell", "canonical_id": "equipment:dumbbell",
                "method": "embedding", "fuzzy_threshold": 1.01,
                "embedding_threshold": 0.30},
    ),
    EvalCase(
        id="res-unresolved-nonsense",
        category="concept_resolution",
        name="Unresolved is reported, not guessed",
        kind="resolve",
        input_summary='"zorblatt machine"',
        expectation="unresolved",
        params={"text": "zorblatt machine", "canonical_id": None},
    ),
    EvalCase(
        id="res-unresolved-vague-clinical",
        category="concept_resolution",
        name="Vague clinical phrase is not force-matched",
        kind="resolve",
        input_summary='"weird knee-ish thing"',
        expectation="unresolved - must not become anatomy:knee",
        params={"text": "weird knee-ish thing", "canonical_id": None},
    ),
    EvalCase(
        id="res-ambiguous-pronoun",
        category="concept_resolution",
        name="Pronoun carries no concept",
        kind="intent_resolves",
        input_summary='"make it 30 minutes"',
        expectation="no equipment concept resolved from 'it'",
        params={"prompt": "make it 30 minutes", "forbidden_prefixes": ["equipment:"]},
    ),
    EvalCase(
        id="res-ambiguous-back",
        category="concept_resolution",
        name="Ambiguous term resolves to one concept, not several",
        kind="resolve",
        input_summary='"lower back"',
        expectation="anatomy:lumbar_spine",
        params={"text": "lower back", "canonical_id": "anatomy:lumbar_spine"},
    ),
    EvalCase(
        id="res-threshold-guard",
        category="concept_resolution",
        name="Near-threshold match is rejected, not rounded up",
        kind="resolve_with_thresholds",
        input_summary='"kettlebel" with a 0.99 fuzzy gate',
        expectation="unresolved",
        params={"text": "kettlebel", "canonical_id": None,
                "fuzzy_threshold": 0.99, "embedding_threshold": 0.99},
    ),
]

# --- safety ------------------------------------------------------------------

SAFETY_CASES = [
    EvalCase(
        id="safe-knee-plyometric",
        category="safety",
        name="Contraindicated pattern is hard-excluded",
        kind="safety",
        input_summary=BASE_INJURY_PROMPT,
        expectation="Static Jump EXCLUDED by injury_contraindicated_pattern",
        params={"prompt": BASE_INJURY_PROMPT,
                "excluded": ["Static Jump", "Vertical Jump to Broad Jump"],
                "rules": ["injury_contraindicated_pattern"], "require_evidence": True},
    ),
    EvalCase(
        id="safe-part-of-closure",
        category="safety",
        name="PART_OF closure reaches the parent joint",
        kind="anatomy_closure",
        input_summary="injury at patellofemoral_joint",
        expectation="closure = {patellofemoral_joint, knee, lower_limb}",
        params={"region": "patellofemoral_joint",
                "closure": ["patellofemoral_joint", "knee", "lower_limb"]},
    ),
    EvalCase(
        id="safe-region-stress",
        category="safety",
        name="Knee-loading work is down-ranked with evidence",
        kind="safety",
        input_summary=BASE_INJURY_PROMPT,
        expectation="Dumbbell Goblet Split Squat DOWN-RANKED by injury_region_stress",
        params={"prompt": BASE_INJURY_PROMPT,
                "downranked": ["Dumbbell Goblet Split Squat"],
                "rules": ["injury_region_stress"], "require_evidence": True},
    ),
    EvalCase(
        id="safe-side-aware",
        category="safety",
        name="Unilateral variant loading the injured side is penalised",
        kind="safety",
        input_summary=BASE_INJURY_PROMPT,
        expectation="injury_side_specific fires somewhere in the catalog",
        params={"prompt": BASE_INJURY_PROMPT, "rules_present": ["injury_side_specific"]},
    ),
    EvalCase(
        id="safe-unknown-anatomy",
        category="safety",
        name="Missing joint data is not treated as safe",
        kind="safety",
        input_summary=BASE_INJURY_PROMPT,
        expectation="unknown_anatomy fires and down-ranks",
        params={"prompt": BASE_INJURY_PROMPT, "rules_present": ["unknown_anatomy"]},
    ),
    EvalCase(
        id="safe-alternative-remains",
        category="safety",
        name="A safe alternative survives the injury filter",
        kind="safety",
        input_summary=BASE_INJURY_PROMPT,
        expectation="at least 10 eligible candidates remain",
        params={"prompt": BASE_INJURY_PROMPT, "min_eligible": 10},
    ),
    EvalCase(
        id="safe-set-operation-equipment",
        category="safety",
        name="Equipment absence is stated as a fact, not drawn as a fake edge",
        kind="evidence_shape",
        input_summary=BASE_EQUIPMENT_PROMPT,
        expectation="evidence carries facts; only REQUIRES is traversed",
        params={"prompt": BASE_EQUIPMENT_PROMPT, "rule": "equipment_unavailable",
                "require_facts": True, "allowed_relationships": ["REQUIRES"]},
    ),
    EvalCase(
        id="safe-preference-never-excludes",
        category="safety",
        name="A dislike never becomes a safety exclusion",
        kind="safety",
        input_summary=BASE_INJURY_PROMPT,
        expectation="no exercise is excluded by preference_dislike",
        params={"prompt": BASE_INJURY_PROMPT,
                "rule_never_excludes": "preference_dislike"},
    ),
    EvalCase(
        id="safe-counts-injury",
        category="safety",
        name="Injury scenario filtering counts are stable",
        kind="counts",
        input_summary=BASE_INJURY_PROMPT,
        expectation="eligible=18 excluded=32 downranked=8",
        params={"prompt": BASE_INJURY_PROMPT, "eligible": 18, "excluded": 32,
                "downranked": 8},
    ),
    EvalCase(
        id="safe-provenance-coverage",
        category="safety",
        name="Every excluded exercise carries evidence",
        kind="provenance_coverage",
        input_summary=BASE_INJURY_PROMPT,
        expectation="100% of exclusions carry a rule and evidence",
        params={"prompt": BASE_INJURY_PROMPT},
    ),
    EvalCase(
        id="safe-ontology-neutral",
        category="safety",
        name="Ontology metadata does not alter safety output",
        kind="ontology_neutrality",
        input_summary=BASE_INJURY_PROMPT,
        expectation="stripping every SNOMED mapping leaves all 50 decisions identical",
        params={"prompt": BASE_INJURY_PROMPT},
    ),
]

# --- equipment ---------------------------------------------------------------

EQUIPMENT_CASES = [
    EvalCase(
        id="equip-no-barbell",
        category="equipment",
        name="Negated equipment is excluded",
        kind="equipment",
        input_summary=BASE_EQUIPMENT_PROMPT,
        expectation="no eligible exercise requires a Barbell",
        params={"prompt": BASE_EQUIPMENT_PROMPT, "forbidden": ["Barbell"]},
    ),
    EvalCase(
        id="equip-restrictive-set",
        category="equipment",
        name="Restrictive phrasing narrows the available set",
        kind="equipment",
        input_summary=BASE_EQUIPMENT_PROMPT,
        expectation="no machine-based exercise survives",
        params={"prompt": BASE_EQUIPMENT_PROMPT,
                "forbidden": ["Cable Resistance Machine",
                              "Seated Lat Pulldown Machine",
                              "Horizontal Leg Press Machine"]},
    ),
    EvalCase(
        id="equip-negation-does-not-leak",
        category="equipment",
        name="Negation does not leak across clauses",
        kind="equipment_available",
        input_summary='"no barbell, only dumbbells and a kettlebell"',
        expectation="Kettlebell remains available; Barbell does not",
        params={"prompt": BASE_EQUIPMENT_PROMPT, "available": ["Kettlebell", "Dumbbell"],
                "unavailable": ["Barbell"]},
    ),
    EvalCase(
        id="equip-dumbbell-only",
        category="equipment",
        name="Dumbbell-only request",
        kind="equipment",
        input_summary='"lower body, only dumbbells"',
        expectation="no eligible exercise requires a Kettlebell or Barbell",
        params={"prompt": "Lower-body workout, only dumbbells.",
                "forbidden": ["Kettlebell", "Barbell"]},
    ),
    EvalCase(
        id="equip-kettlebell-only",
        category="equipment",
        name="Kettlebell-only request",
        kind="equipment",
        input_summary='"full body, only a kettlebell"',
        expectation="no eligible exercise requires a Dumbbell or Barbell",
        params={"prompt": "Full-body workout, only a kettlebell.",
                "forbidden": ["Dumbbell", "Barbell"]},
    ),
    EvalCase(
        id="equip-restrictive-correction",
        category="equipment",
        name="A later restrictive clause supersedes an earlier one",
        kind="equipment",
        input_summary='"...only dumbbells and a kettlebell. Only use dumbbells."',
        expectation="Kettlebell work becomes ineligible",
        params={"prompt": BASE_ADJUSTMENT_PROMPT + " Only use dumbbells.",
                "forbidden": ["Kettlebell"]},
    ),
    EvalCase(
        id="equip-bodyweight-survives",
        category="equipment",
        name="Bodyweight work is never filtered by equipment",
        kind="equipment_bodyweight",
        input_summary='"only dumbbells"',
        expectation="bodyweight exercises remain eligible",
        params={"prompt": "Lower-body workout, only dumbbells."},
    ),
]

# --- explicit exclusions -----------------------------------------------------

EXCLUSION_CASES = [
    EvalCase(
        id="excl-deadlift-family",
        category="exclusion",
        name="Deadlift exclusion reaches the hinge family",
        kind="exclusion",
        input_summary='"lower body but exclude deadlifts"',
        expectation="both hamstring walkouts EXCLUDED by explicit_exclusion",
        params={"prompt": "Create a lower-body workout but exclude deadlifts.",
                "excluded": ["One-Kettlebell Hamstring Walkout",
                             "Med Ball Hamstring Walkout"],
                "rule": "explicit_exclusion"},
    ),
    EvalCase(
        id="excl-no-literal-deadlift",
        category="exclusion",
        name="No catalog exercise is literally named deadlift",
        kind="catalog_premise",
        input_summary="catalog scan",
        expectation="0 exercises contain 'deadlift' in their name",
        params={"substring": "deadlift", "expected_count": 0},
    ),
    EvalCase(
        id="excl-squat-family",
        category="exclusion",
        name="A second family excludes correctly",
        kind="exclusion",
        input_summary='"full body, avoid squats"',
        expectation="squat-family work EXCLUDED by explicit_exclusion",
        params={"prompt": "Full-body workout, avoid squats.",
                "excluded": ["Dumbbell Goblet Split Squat"],
                "rule": "explicit_exclusion"},
    ),
    EvalCase(
        id="excl-plyometric-family",
        category="exclusion",
        name="Plyometric family exclusion",
        kind="exclusion",
        input_summary='"full body, no plyometrics"',
        expectation="Static Jump EXCLUDED",
        params={"prompt": "Full-body workout, no plyometrics.",
                "excluded": ["Static Jump"], "rule": None},
    ),
    EvalCase(
        id="excl-equipment-ban",
        category="exclusion",
        name="Equipment ban is an explicit exclusion",
        kind="exclusion",
        input_summary='"no barbell"',
        expectation="barbell work EXCLUDED by explicit_exclusion",
        params={"prompt": "Full-body workout, no barbell.",
                "excluded": ["Barbell Decline Bench Press"],
                "rule": "explicit_exclusion"},
    ),
    EvalCase(
        id="excl-does-not-overreach",
        category="exclusion",
        name="Exclusion does not remove unrelated work",
        kind="exclusion_scope",
        input_summary='"lower body but exclude deadlifts"',
        expectation="upper-body pressing remains eligible",
        params={"prompt": "Create a lower-body workout but exclude deadlifts.",
                "still_eligible": ["Alternating Dumbbell Overhead Press"]},
    ),
]

# --- longitudinal ------------------------------------------------------------

LONGITUDINAL_CASES = [
    EvalCase(
        id="long-declining-adherence",
        category="longitudinal",
        name="Declining adherence is read from the observations",
        kind="trajectory",
        input_summary="4 adherence weeks: 100, 100, 75, 50",
        expectation="direction=declining, delta=-50",
        params={"adherence_direction": "declining", "adherence_delta": -50.0},
    ),
    EvalCase(
        id="long-sleep-flat",
        category="longitudinal",
        name="Sleep reads flat because the data is flat",
        kind="trajectory",
        input_summary="7 nights averaging 6.27h",
        expectation="direction=flat - not 'declining'",
        params={"sleep_direction": "flat"},
    ),
    EvalCase(
        id="long-training-load-low",
        category="longitudinal",
        name="Training load is measured against the member's own target",
        kind="trajectory",
        input_summary="3 completed sessions, target 4/week",
        expectation="state=low",
        params={"load_state": "low"},
    ),
    EvalCase(
        id="long-progression-hold",
        category="longitudinal",
        name="Progression holds and states why",
        kind="trajectory",
        input_summary="declining adherence + low load",
        expectation="progression=hold with rationale",
        params={"progression": "hold", "require_rationale": True},
    ),
    EvalCase(
        id="long-stable-adherence",
        category="longitudinal",
        name="Stable adherence does not force a hold",
        kind="trajectory_variant",
        input_summary="4 weeks at 90%, target 2/week",
        expectation="progression=progress",
        params={"variant": "stable", "progression": "progress"},
    ),
    EvalCase(
        id="long-insufficient-history",
        category="longitudinal",
        name="One week of history is insufficient, not flat",
        kind="trajectory_variant",
        input_summary="1 adherence observation",
        expectation="progression=insufficient_data",
        params={"variant": "sparse", "progression": "insufficient_data"},
    ),
    EvalCase(
        id="long-injury-not-inferred",
        category="longitudinal",
        name="Injury trajectory is recorded, never inferred",
        kind="trajectory_variant",
        input_summary="adherence driven to 10%",
        expectation="injury_trajectory stays 'recovering' from recorded status",
        params={"variant": "collapsing_adherence", "injury_state": "recovering",
                "injury_source": "recorded_status"},
    ),
    EvalCase(
        id="long-familiar-boost",
        category="longitudinal",
        name="Familiar movement families are boosted while adherence declines",
        kind="longitudinal_ranking",
        input_summary=BASE_INJURY_PROMPT,
        expectation="at least one candidate carries a familiarity bonus",
        params={"prompt": BASE_INJURY_PROMPT, "expect_boost": True},
    ),
    EvalCase(
        id="long-safety-precedence",
        category="longitudinal",
        name="Hard safety overrides a longitudinal boost",
        kind="longitudinal_precedence",
        input_summary='"exclude deadlifts" (hinge is the most familiar family)',
        expectation="no excluded exercise appears in the ranked set",
        params={"prompt": "Create a lower-body workout but exclude deadlifts."},
    ),
    EvalCase(
        id="long-bounded-adjustment",
        category="longitudinal",
        name="Personalization is bounded below the smallest safety penalty",
        kind="longitudinal_bound",
        input_summary="policy constants",
        expectation="MAX_LONGITUDINAL_ADJUSTMENT < SMALLEST_SAFETY_PENALTY",
        params={},
    ),
]

# --- adjustment --------------------------------------------------------------

ADJUSTMENT_CASES = [
    EvalCase(
        id="adj-exclude-deadlifts",
        category="adjustment",
        name="Exclude deadlifts",
        kind="adjustment",
        input_summary='base + "Exclude deadlifts."',
        expectation="hinge family newly ineligible; plan excludes it",
        params={"adjustment": "Exclude deadlifts.",
                "newly_excluded_names": ["One-Kettlebell Hamstring Walkout"],
                "min_newly_excluded": 1},
    ),
    EvalCase(
        id="adj-only-dumbbells",
        category="adjustment",
        name="Only use dumbbells",
        kind="adjustment",
        input_summary='base + "Only use dumbbells."',
        expectation="no plan exercise requires a Kettlebell",
        params={"adjustment": "Only use dumbbells.",
                "plan_forbids_equipment": ["Kettlebell", "Barbell"]},
    ),
    EvalCase(
        id="adj-quad-focus",
        category="adjustment",
        name="More quad focused",
        kind="adjustment",
        input_summary='base + "Make it more quad focused..."',
        expectation="ranking moves; eligible set unchanged",
        params={"adjustment": "Make it more quad focused without aggravating her knee.",
                "expect_downranking": True, "eligible_set_unchanged": True},
    ),
    EvalCase(
        id="adj-duration",
        category="adjustment",
        name="Make it 30 minutes",
        kind="adjustment",
        input_summary='base + "Make it 30 minutes."',
        expectation="validated plan is 30 minutes",
        params={"adjustment": "Make it 30 minutes.", "duration": 30},
    ),
    EvalCase(
        id="adj-knee-safety",
        category="adjustment",
        name="Avoid exercises that stress her knee",
        kind="adjustment",
        input_summary='base + "Avoid exercises that stress her knee."',
        expectation="knee rules still fire; plan stays safe",
        params={"adjustment": "Avoid exercises that stress her knee.",
                "still_excluded_names": ["Static Jump"]},
    ),
    EvalCase(
        id="adj-noop",
        category="adjustment",
        name="A no-op adjustment reports no change honestly",
        kind="adjustment",
        input_summary='base + "Keep it as it is."',
        expectation="diff is empty and carries an explanatory note",
        params={"adjustment": "Keep it as it is.", "expect_no_change_note": True},
    ),
    EvalCase(
        id="adj-safety-never-weakened",
        category="adjustment",
        name="No adjustment reintroduces an excluded exercise",
        kind="adjustment_safety_sweep",
        input_summary="all six adjustments",
        expectation="every adjusted plan is disjoint from its exclusion set",
        params={},
    ),
    EvalCase(
        id="adj-diff-honesty",
        category="adjustment",
        name="The diff never claims an equivalence the graph lacks",
        kind="adjustment_diff_honesty",
        input_summary='base + "Exclude deadlifts."',
        expectation="'equivalent' / 'replaces' never appear in diff reasons",
        params={"adjustment": "Exclude deadlifts."},
    ),
]

# --- workout validation (adversarial) ---------------------------------------
# The post-generation gate is the single most important module, so every case
# here drives the REAL workflow with a model that ignores the candidate list.

VALIDATION_CASES = [
    EvalCase(
        id="val-excluded-exercise",
        category="validation",
        name="Model returns an excluded exercise",
        kind="adversarial",
        input_summary=BASE_INJURY_PROMPT,
        expectation="rejected and replaced; not in the final plan",
        params={"prompt": BASE_INJURY_PROMPT, "mode": "excluded"},
    ),
    EvalCase(
        id="val-all-excluded",
        category="validation",
        name="Model returns every excluded exercise at once",
        kind="adversarial",
        input_summary=BASE_INJURY_PROMPT,
        expectation="none survive final validation",
        params={"prompt": BASE_INJURY_PROMPT, "mode": "all_excluded"},
    ),
    EvalCase(
        id="val-hallucinated-id",
        category="validation",
        name="Model invents an exercise id",
        kind="adversarial",
        input_summary=BASE_INJURY_PROMPT,
        expectation="rejected as hallucinated_id",
        params={"prompt": BASE_INJURY_PROMPT, "mode": "hallucinated"},
    ),
    EvalCase(
        id="val-unavailable-equipment",
        category="validation",
        name="Model returns an exercise needing absent equipment",
        kind="adversarial",
        input_summary=BASE_EQUIPMENT_PROMPT,
        expectation="rejected; plan requires no unavailable equipment",
        params={"prompt": BASE_EQUIPMENT_PROMPT, "mode": "unavailable_equipment"},
    ),
    EvalCase(
        id="val-outside-candidates",
        category="validation",
        name="Model picks outside the approved candidate set",
        kind="adversarial",
        input_summary=BASE_INJURY_PROMPT,
        expectation="only approved ids survive",
        params={"prompt": BASE_INJURY_PROMPT, "mode": "outside_candidates"},
    ),
    EvalCase(
        id="val-empty-plan-fails-closed",
        category="validation",
        name="Nothing survivable fails closed",
        kind="adversarial",
        input_summary="draft of hallucinated ids only, no repair pool",
        expectation="UnsafePlanError - never an unvalidated plan",
        params={"mode": "fail_closed"},
    ),
    EvalCase(
        id="val-duration-preserved",
        category="validation",
        name="Requested duration survives composition",
        kind="duration_validation",
        input_summary='"30-minute lower-body workout"',
        expectation="validated plan reports 30 minutes",
        params={"prompt": "Create a 30-minute lower-body workout.", "duration": 30},
    ),
    EvalCase(
        id="val-schema-valid",
        category="validation",
        name="Generated plan matches the published schema",
        kind="schema",
        input_summary=BASE_INJURY_PROMPT,
        expectation="sections named warmup/main/cooldown, every id in the catalog",
        params={"prompt": BASE_INJURY_PROMPT},
    ),
]

# --- copilot / MCP -----------------------------------------------------------

COPILOT_CASES = [
    EvalCase(
        id="mcp-metric-trend",
        category="copilot_mcp",
        name="Adherence question routes to the metric-trend tool",
        kind="copilot",
        input_summary='"How is adherence trending?"',
        expectation="intent=ADHERENCE_TREND, MCP mode, grounded answer",
        params={"question": "How's adherence trending?", "intent": "ADHERENCE_TREND",
                "expect_tools": ["get_member_metric_trend"], "expect_mode": "mcp"},
    ),
    EvalCase(
        id="mcp-exercise-safety",
        category="copilot_mcp",
        name="Safety question uses the authoritative tool",
        kind="copilot",
        input_summary='"Is Static Jump safe for her?"',
        expectation="authoritative_safety=True",
        params={"question": "Is Static Jump safe for her?",
                "expect_authoritative": True, "expect_mode": "mcp"},
    ),
    EvalCase(
        id="mcp-safety-parity",
        category="copilot_mcp",
        name="MCP safety matches a direct SafetyEngine call",
        kind="mcp_parity",
        input_summary="every catalog exercise",
        expectation="tool verdict == engine verdict for all 50",
        params={},
    ),
    EvalCase(
        id="mcp-provenance-tool",
        category="copilot_mcp",
        name="Provenance tool returns real ordered paths",
        kind="mcp_provenance",
        input_summary="Static Jump",
        expectation="graph path present with real relationships",
        params={"exercise": "Static Jump"},
    ),
    EvalCase(
        id="mcp-safe-candidates",
        category="copilot_mcp",
        name="Safe-candidate tool never returns an excluded exercise",
        kind="mcp_candidates",
        input_summary=BASE_INJURY_PROMPT,
        expectation="candidate set disjoint from the exclusion set",
        params={"prompt": BASE_INJURY_PROMPT},
    ),
    EvalCase(
        id="mcp-workout-evaluation",
        category="copilot_mcp",
        name="Workout-request evaluation is read-only",
        kind="mcp_evaluate",
        input_summary=BASE_INJURY_PROMPT,
        expectation="composed_workout is null; counts match the engine",
        params={"prompt": BASE_INJURY_PROMPT},
    ),
    EvalCase(
        id="mcp-fallback",
        category="copilot_mcp",
        name="MCP outage falls back to the deterministic dispatcher",
        kind="copilot_fallback",
        input_summary='"How is adherence trending?" with MCP unreachable',
        expectation="mode=fallback, answer still grounded in real numbers",
        params={"question": "How's adherence trending?"},
    ),
    EvalCase(
        id="mcp-missing-data-admission",
        category="copilot_mcp",
        name="Missing data produces an admission, not an improvisation",
        kind="copilot_missing_data",
        input_summary='"Show me her labs" with labs removed',
        expectation="answer says there are no lab results",
        params={},
    ),
]


ALL_CASES: list[EvalCase] = [
    *RESOLUTION_CASES,
    *SAFETY_CASES,
    *EQUIPMENT_CASES,
    *EXCLUSION_CASES,
    *LONGITUDINAL_CASES,
    *ADJUSTMENT_CASES,
    *VALIDATION_CASES,
    *COPILOT_CASES,
]


def cases_by_category() -> dict[str, list[EvalCase]]:
    grouped: dict[str, list[EvalCase]] = {}
    for case in ALL_CASES:
        grouped.setdefault(case.category, []).append(case)
    return grouped
