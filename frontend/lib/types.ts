/**
 * Types mirroring the FastAPI response models in backend/app/api/schemas.py.
 *
 * Hand-written rather than generated: the surface is small, and keeping it
 * explicit makes the contract visible in review. If the backend schema changes,
 * `npm run typecheck` will not catch it - the integration test in the API layer
 * will. That trade-off is noted in the README.
 */

export type ResolutionMethod =
  | 'exact'
  | 'alias'
  | 'fuzzy'
  | 'embedding'
  | 'unresolved';

export interface ResolvedConcept {
  source_text: string;
  canonical_id: string | null;
  label: string | null;
  concept_type: string | null;
  method: ResolutionMethod;
  confidence: number;
  alternatives: string[];
}

export interface EvidencePath {
  path: string[];
  rendered: string;
}

/* ---- Ontology grounding (optional; added additively by the backend) ---- */

export type MappingRelation = 'exactMatch' | 'closeMatch' | 'broadMatch';

/**
 * A local concept's link to a published ontology concept.
 *
 * `local_id` is always the identity this system reasons on. The ontology fields
 * standardise clinical identity for interchange and are display-only — no
 * safety decision reads them, and the frontend never infers one from them.
 *
 * A concept reviewed and deliberately left ungrounded arrives with
 * `status: 'unmapped'`, no code and no relation, and keeps `mapping_evidence`
 * as the recorded reason.
 */
export interface ConceptGrounding {
  local_id: string;
  label: string;
  ontology_source: string | null;
  ontology_code: string | null;
  ontology_term: string | null;
  ontology_uri: string | null;
  browser_url: string | null;
  mapping_relation: MappingRelation | null;
  mapping_evidence: string | null;
  mapping_version: string | null;
  status: 'verified' | 'unmapped';
}

export interface OntologySourceInfo {
  id: string;
  label: string;
  version: string | null;
  used_for: string | null;
}

export interface OntologyGroundingReport {
  mapping_set_version: string | null;
  verified_on: string | null;
  method: string | null;
  sources: OntologySourceInfo[];
  mapped: ConceptGrounding[];
  unmapped: ConceptGrounding[];
  counts: Record<string, number>;
}

/* ---- Longitudinal trajectory (optional; added additively) ---- */

export type TrendDirection =
  | 'improving'
  | 'declining'
  | 'flat'
  | 'insufficient_data';

export type ProgressionState =
  | 'progress'
  | 'hold'
  | 'regress'
  | 'insufficient_data';

/**
 * The deterministic longitudinal reading that personalized a plan.
 *
 * Personalization input, never clinical truth. `injury_trajectory.source` is
 * `recorded_status` because that value is copied from the member's recorded
 * injury — nothing here is inferred from adherence or sleep, and the UI must
 * not present it as a clinical assessment.
 */
export interface MemberTrajectory {
  member_id: string;
  adherence: {
    direction: TrendDirection;
    first: number | null;
    latest: number | null;
    delta: number | null;
    observations: number;
  };
  sleep: {
    direction: TrendDirection;
    average_recent: number | null;
    nights: number;
  };
  training_load: {
    state: 'low' | 'moderate' | 'high' | 'insufficient_data';
    completed_sessions: number;
    sessions_per_week: number | null;
    target_sessions_per_week: number | null;
    ratio_to_target: number | null;
    average_session_minutes: number | null;
    average_rpe: number | null;
  };
  progression: {
    state: ProgressionState;
    rationale: string[];
  };
  injury_trajectory: {
    state: 'recovering' | 'worsening' | 'stable' | 'unknown';
    source: 'recorded_status' | 'absent';
    injury_name: string | null;
    recorded_status: string | null;
    severity: string | null;
  };
  bias: {
    volume_bias: 'conservative' | 'standard' | 'ambitious';
    novelty_bias: 'low' | 'standard' | 'high';
    familiar_movement_families: string[];
  };
}

/* ---- Graph reasoning (optional; added additively by the backend) ---- */

export type GraphNodeKind =
  | 'Member'
  | 'Injury'
  | 'InjuryCondition'
  | 'Exercise'
  | 'AnatomicalRegion'
  | 'Equipment'
  | 'MovementPattern'
  | 'MovementFamily'
  | 'Preference'
  | 'Muscle';

export type ConstraintType =
  | 'injury_anatomy'
  | 'contraindication'
  | 'equipment'
  | 'explicit_exclusion'
  | 'preference_ranking'
  | 'data_gap';

export interface GraphTraceNode {
  id: string;
  label: string;
  type: GraphNodeKind;
  properties: Record<string, string>;
}

export interface GraphTraceEdge {
  source_id: string;
  target_id: string;
  relationship: string;
  direction: 'outgoing' | 'incoming';
  rule_id: string | null;
}

/**
 * Which half of the reasoning a path belongs to.
 *
 * Classified by the **backend** from the node kinds the safety engine recorded.
 * The UI groups on this value and never infers it from edge names or reason
 * text — inferring it would be frontend-invented structure inside the one panel
 * whose purpose is to show only what the graph holds.
 */
export type PathKind =
  | 'member_context'
  | 'anatomy_hierarchy'
  | 'exercise_structure'
  | 'set_operation';

export interface GraphTraversal {
  id: string;
  constraint_type: ConstraintType;
  exercise_id: string;
  exercise_name: string;
  decision: 'allowed' | 'downranked' | 'excluded';
  reason: string;
  rule_id: string | null;
  source: 'graph_traversal' | 'deterministic_set_operation';
  /** Optional: older backends omit it, and the UI then shows one flat list. */
  path_kind?: PathKind;
  nodes: GraphTraceNode[];
  edges: GraphTraceEdge[];
  facts: string[];
  source_concept: string | null;
}

export interface PromptConcept {
  source_text: string;
  canonical_id: string | null;
  label: string | null;
  concept_type: string | null;
  method: ResolutionMethod;
  confidence: number;
  resolved: boolean;
  /** Optional: absent for concepts with no published mapping, and on older backends. */
  grounding?: ConceptGrounding | null;
}

export interface RuleCategoryCount {
  constraint_type: ConstraintType;
  label: string;
  exercises_affected: number;
  traversals: number;
}

export interface GraphReasoningSummary {
  catalog_count: number;
  excluded_count: number;
  downranked_count: number;
  eligible_count: number;
  in_plan_count: number;
  concepts_resolved: number;
  concepts_unresolved: number;
  traversal_count: number;
  exercises_with_evidence: number;
  counts_by_constraint: RuleCategoryCount[];
  note: string;
}

export interface GraphReasoning {
  trace_id: string;
  graph_backend: string;
  summary: GraphReasoningSummary;
  prompt_concepts: PromptConcept[];
  traversals: GraphTraversal[];
  member_facts: string[];
}

export type ProvenanceDecision =
  | 'included'
  | 'downranked'
  | 'filtered'
  | 'substituted';

export interface ProvenanceItem {
  exercise_id: string;
  exercise: string;
  decision: ProvenanceDecision;
  reasons: string[];
  rule_ids: string[];
  evidence: EvidencePath[];
  decision_source: 'knowledge_graph' | 'llm_composition' | 'post_validation';
  score: number | null;
  score_adjustment: number;
  in_plan: boolean;
  section: string | null;
  /** Longitudinal personalization, tracked apart from the safety adjustment. */
  longitudinal_adjustment?: number;
  longitudinal_reasons?: string[];
}

export interface WorkoutExercise {
  exercise_id: string;
  name: string;
  sets: number | null;
  reps: string | null;
  duration_seconds: number | null;
  rest_seconds: number | null;
  rationale: string;
  coaching_note: string | null;
  substituted_for: string | null;
}

export interface WorkoutSection {
  name: 'warmup' | 'main' | 'cooldown';
  exercises: WorkoutExercise[];
}

export interface GeneratedWorkout {
  title: string;
  duration_minutes: number;
  sections: WorkoutSection[];
  summary: string | null;
}

export interface SafetySummary {
  catalog_total: number;
  eligible: number;
  excluded: number;
  downranked: number;
  in_plan: number;
  post_validation_passed: boolean;
  post_validation_rejections: number;
  post_validation_replacements: number;
}

export interface PostValidationReport {
  passed: boolean;
  checked_exercise_ids: string[];
  rejected: Array<{
    exercise_id: string;
    name: string;
    section: string;
    reason: string;
    rule_id: string;
    graph_paths?: string[];
  }>;
  replacements: Array<{
    replaced_id: string;
    replaced_name: string;
    with_id: string;
    with_name: string;
    section: string;
  }>;
  hallucinated_ids: string[];
  notes: string[];
}

export interface GenerateWorkoutResponse {
  request_id: string;
  workout: GeneratedWorkout;
  resolved_concepts: ResolvedConcept[];
  unresolved_concepts: ResolvedConcept[];
  filtered_exercises: ProvenanceItem[];
  provenance: ProvenanceItem[];
  member_facts: string[];
  safety: SafetySummary;
  post_validation: PostValidationReport;
  timings_ms: Record<string, number>;
  generator: string;
  graph_backend: string;
  /** Optional: absent responses fall back to the provenance-only UI. */
  graph_reasoning?: GraphReasoning | null;
  /** Optional: the longitudinal reading that personalized this plan. */
  trajectory?: MemberTrajectory | null;
}

/* ---- Workout adjustment ---- */

export type ChangeKind = 'removed' | 'added' | 'downranked';

export interface PlanChange {
  exercise_id: string;
  exercise: string;
  kind: ChangeKind;
  reasons: string[];
  rule_ids: string[];
  score_before: number | null;
  score_after: number | null;
  /** True when the adjustment made this ineligible, not merely unselected. */
  now_excluded: boolean;
}

export interface AdjustmentDiff {
  removed: PlanChange[];
  added: PlanChange[];
  downranked: PlanChange[];
  retained_ids: string[];
  counts: Record<string, number>;
  notes: string[];
}

/**
 * An adjusted plan is a *superset* of a generated one: it went through the
 * identical pipeline, so it carries the same provenance and safety guarantees,
 * plus what changed.
 */
export interface AdjustWorkoutResponse extends GenerateWorkoutResponse {
  adjustment: string;
  effective_prompt: string;
  diff: AdjustmentDiff;
}

/* ---- Knowledge Graph Explorer (read-only) ---- */

/**
 * A node as the explorer API serves it.
 *
 * `id` is the graph's own key (`AnatomicalRegion:knee`). Properties are
 * allowlisted server-side — the frontend receives only what the API chose to
 * expose, and never a raw Neo4j object.
 */
export interface GraphNodeView {
  id: string;
  label: string;
  kind: string;
  properties: Record<string, string | number | boolean>;
  ontology_grounding: ConceptGrounding | null;
  degree: number;
}

export interface GraphEdgeView {
  id: string;
  source: string;
  target: string;
  relationship: string;
  direction: 'outgoing' | 'incoming';
  properties: Record<string, string>;
}

export interface GraphSubgraph {
  root_id: string;
  nodes: GraphNodeView[];
  edges: GraphEdgeView[];
  depth: number;
  truncated: boolean;
  omitted_count: number;
}

export interface GraphSearchHit {
  id: string;
  label: string;
  kind: string;
  canonical_id: string | null;
  match: 'label' | 'alias' | 'id' | 'substring';
  score: number;
  degree: number;
}

export interface GraphSearchResponse {
  query: string;
  hits: GraphSearchHit[];
  count: number;
  truncated: boolean;
}

export interface GraphStatsResponse {
  graph_backend: string;
  node_count: number;
  edge_count: number;
  nodes_by_kind: Record<string, number>;
  edges_by_relationship: Record<string, number>;
  ontology_mappings: number;
}

export interface RelationshipGlossaryEntry {
  relationship: string;
  description: string;
  count: number;
}

export interface GraphLegendResponse {
  node_kinds: string[];
  relationships: RelationshipGlossaryEntry[];
}

/**
 * A safety decision for one exercise, carrying the *same* traversals the coach
 * UI renders. The explorer computes no safety of its own.
 */
export interface GraphSafetyResponse {
  member_id: string;
  member_name: string;
  exercise_id: string;
  exercise_name: string;
  prompt: string;
  decision: string;
  rule_ids: string[];
  reasons: string[];
  traversals: GraphTraversal[];
  score_adjustment: number;
  longitudinal_adjustment: number;
  longitudinal_reasons: string[];
  eligible: boolean;
}

/* ---- System quality: offline evaluation ---- */

export type EvaluationCategory =
  | 'concept_resolution'
  | 'safety'
  | 'equipment'
  | 'exclusion'
  | 'longitudinal'
  | 'adjustment'
  | 'validation'
  | 'copilot_mcp';

export interface EvalGraphEvidence {
  exercise: string;
  decision: string;
  rule_ids: string[];
  rendered_paths: string[];
  facts: string[];
  /** The same traversals the coach UI renders — reused, not re-modelled. */
  traversals: GraphTraversal[];
}

export interface EvaluationCaseResult {
  case_id: string;
  category: EvaluationCategory;
  name: string;
  input_summary: string;
  expected: string;
  actual: string;
  passed: boolean;
  latency_ms: number;
  notes: string[];
  evidence: EvalGraphEvidence[];
  unsafe_escape: boolean;
}

/**
 * Every metric carries its ratio. `value` is derived server-side and is `null`
 * when nothing was measured — "no cases ran" and "everything failed" are
 * different facts and must not render the same.
 */
export interface EvaluationMetric {
  key: string;
  label: string;
  numerator: number;
  denominator: number;
  higher_is_better: boolean;
  detail: string | null;
  value: number | null;
}

export interface EvaluationInvariant {
  key: string;
  statement: string;
  holds: boolean;
  proven_by: string[];
  failed_by: string[];
  detail: string | null;
  evidence_count: number;
}

export interface EvaluationLatency {
  p50_ms: number | null;
  p95_ms: number | null;
  max_ms: number | null;
  total_ms: number;
}

export interface EvaluationRun {
  run_id: string;
  started_at: string;
  duration_ms: number;
  graph_backend: string;
  llm_provider: string;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  unsafe_escapes: number;
  metrics: EvaluationMetric[];
  invariants: EvaluationInvariant[];
  results: EvaluationCaseResult[];
  latency: EvaluationLatency;
  status: 'pass' | 'fail';
}

export interface EvaluationSummary {
  run_id: string;
  started_at: string;
  status: 'pass' | 'fail';
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  unsafe_escapes: number;
  p95_ms: number | null;
  duration_ms: number;
}

export interface EvaluationHistory {
  runs: EvaluationSummary[];
  count: number;
}

/* ---- System quality: runtime traces ---- */

export type TraceZone = 'deterministic' | 'generative' | 'mcp';

export interface NodeSpan {
  name: string;
  duration_ms: number;
  zone: TraceZone;
  status: 'ok' | 'error' | 'skipped';
}

export interface RequestTrace {
  request_id: string;
  workflow: 'generate' | 'adjust' | 'copilot' | 'evaluation';
  member_id: string | null;
  total_duration_ms: number;
  started_at: string | null;
  status: 'ok' | 'error';
  error_kind: string | null;
  spans: NodeSpan[];
  resolution: {
    resolved_count: number;
    unresolved_count: number;
    method_counts: Record<string, number>;
  } | null;
  safety: {
    catalog_count: number;
    excluded_count: number;
    downranked_count: number;
    eligible_count: number;
    in_plan_count: number;
    rules_fired: string[];
    rule_fire_count: number;
    validation_corrections: number;
    validation_passed: boolean;
    hallucinated_ids: number;
  } | null;
  adjustment: {
    removed_count: number;
    added_count: number;
    downranked_count: number;
    retained_count: number;
    newly_excluded_count: number;
    duration_minutes: number | null;
    baseline_rerun_ms: number | null;
  } | null;
  mcp: {
    intent: string | null;
    mode: 'mcp' | 'fallback' | null;
    tools_planned: string[];
    tools_called: string[];
    tool_duration_ms: number | null;
    authoritative_safety: boolean;
    safety_corrected: boolean;
    generator: string | null;
  } | null;
  graph_query_count: number | null;
  llm_provider: string | null;
  llm_latency_ms: number | null;
  llm_input_tokens: number | null;
  llm_output_tokens: number | null;
}

export interface TraceListResponse {
  traces: RequestTrace[];
  count: number;
  capacity: number;
}

export interface Goal {
  id: string;
  text: string;
  priority: number;
  target_date: string | null;
}

export interface Injury {
  id: string;
  region: string;
  joint: string | null;
  status: string | null;
  severity: string | null;
  since: string | null;
  notes: string | null;
}

export interface MemberSummary {
  id: string;
  name: string;
  tier: string | null;
  age: number | null;
  primary_goal: string | null;
  goals: Goal[];
  active_injuries: Injury[];
  equipment_available: string[];
  latest_adherence_pct: number | null;
  adherence_trend: string | null;
  churn_risk_level: string | null;
  churn_risk_reasons: string[];
  avg_sleep_hours: number | null;
  preferred_session_minutes: number | null;
  morning_tasks: Array<{ type: string; text: string }>;
  brief_date: string | null;
}

export interface MemberHistory {
  member_id: string;
  sessions: Array<{
    date: string;
    title: string;
    completed: boolean;
    planned: boolean;
    duration_min: number;
    rpe: number | null;
    exercises: string[];
  }>;
  chat: Array<{
    ts: string;
    from: string;
    text: string;
    attachments: Array<{ type: string; caption: string | null }>;
  }>;
  adherence: Array<{ week_of: string; pct: number }>;
  sleep: Array<{ label: string; hours: number }>;
}

export interface ChartPayload {
  type: 'line' | 'bar';
  title: string;
  x: string[];
  series: Array<{ name: string; values: number[] }>;
  y_label: string | null;
  y_domain: number[] | null;
}

export interface Grounding {
  mode: 'mcp' | 'fallback';
  tools_used: string[];
  authoritative_safety: boolean;
  safety_corrected: boolean;
}

export interface EvidenceReason {
  rule_id: string;
  message: string;
}

/**
 * Display-ready projection of an authoritative safety verdict.
 *
 * Every field is already rendered by the backend. The UI shows these strings;
 * it never interprets safety logic, and it never reads `evidence` (the raw tool
 * payloads) to work out what happened.
 */
export interface SafetyEvidence {
  exercise_name: string;
  decision: string;
  reasons: EvidenceReason[];
  rule_ids: string[];
  graph_paths: string[];
  evidence_note: string | null;
}

export interface CopilotResponse {
  intent: string;
  /** The only human-facing text. Always rendered as-is. */
  answer: string;
  citations: Array<{ source: string; detail: string }>;
  chart: ChartPayload | null;
  /** Verbatim tool payloads: debugging detail, never displayed as chat text. */
  evidence: Record<string, unknown>;
  generator: string;
  latency_ms: number;
  /** Optional: absent on older backends, so the UI must tolerate undefined. */
  grounding?: Grounding | null;
  safety_evidence?: SafetyEvidence | null;
}

export interface ExerciseProvenance {
  exercise_id: string;
  name: string;
  targets: string[];
  stresses: string[];
  anatomy_ancestors: string[];
  requires: string[];
  patterns: string[];
  families: string[];
  is_unilateral: boolean;
  side: string | null;
  /** Optional: grounding for the anatomy and muscles this exercise touches. */
  grounding?: ConceptGrounding[];
}

export interface HealthResponse {
  status: string;
  graph_backend: string;
  llm_provider: string;
  graph_stats: Record<string, number>;
  /**
   * Deployment facts. Optional so an older backend still parses. Deliberately
   * no hostname, URI or credential — the client is told *which* environment
   * and whether the graph is seeded, never where it lives.
   */
  environment?: string;
  graph_seeded?: boolean;
  seed_version?: string | null;
  ontology_mappings?: number;
}
