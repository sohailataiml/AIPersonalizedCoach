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

export interface GraphTraversal {
  id: string;
  constraint_type: ConstraintType;
  exercise_id: string;
  exercise_name: string;
  decision: 'allowed' | 'downranked' | 'excluded';
  reason: string;
  rule_id: string | null;
  source: 'graph_traversal' | 'deterministic_set_operation';
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
}

export interface HealthResponse {
  status: string;
  graph_backend: string;
  llm_provider: string;
  graph_stats: Record<string, number>;
}
