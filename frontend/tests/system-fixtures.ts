/**
 * System-quality fixtures.
 *
 * The evaluation run is a real artifact produced by `python scripts/run_evals.py`,
 * trimmed to eight cases so the component tests stay fast. Using genuine output
 * matters here more than usual: these tests exist to prove the dashboard renders
 * *measured* values, and a hand-written fixture would quietly defeat that.
 */
import rawRun from './system-fixture.json';
import type { EvaluationHistory, EvaluationRun, RequestTrace } from '@/lib/types';

export const evaluationRun = rawRun as unknown as EvaluationRun;

export const evaluationHistory: EvaluationHistory = {
  count: 1,
  runs: [
    {
      run_id: evaluationRun.run_id,
      started_at: evaluationRun.started_at,
      status: evaluationRun.status,
      total_cases: evaluationRun.total_cases,
      passed_cases: evaluationRun.passed_cases,
      failed_cases: evaluationRun.failed_cases,
      unsafe_escapes: evaluationRun.unsafe_escapes,
      p95_ms: evaluationRun.latency.p95_ms,
      duration_ms: evaluationRun.duration_ms,
    },
  ],
};

/** Captured from GET /api/system/traces after a generate + copilot request. */
export const generateTrace: RequestTrace = {
  request_id: 'req8c31aa01',
  workflow: 'generate',
  member_id: 'mbr_01HX9JORDAN',
  total_duration_ms: 52.14,
  started_at: '2026-08-13T00:15:00+00:00',
  status: 'ok',
  error_kind: null,
  spans: [
    { name: 'load_member', duration_ms: 0.05, zone: 'deterministic', status: 'ok' },
    {
      name: 'parse_intent_and_resolve',
      duration_ms: 5.39,
      zone: 'deterministic',
      status: 'ok',
    },
    {
      name: 'analyze_longitudinal_context',
      duration_ms: 0.84,
      zone: 'deterministic',
      status: 'ok',
    },
    { name: 'evaluate_safety', duration_ms: 20.7, zone: 'deterministic', status: 'ok' },
    { name: 'rank_candidates', duration_ms: 1.67, zone: 'deterministic', status: 'ok' },
    { name: 'compose_workout_llm', duration_ms: 9.6, zone: 'generative', status: 'ok' },
    { name: 'validate_workout', duration_ms: 3.1, zone: 'deterministic', status: 'ok' },
    { name: 'build_provenance', duration_ms: 4.2, zone: 'deterministic', status: 'ok' },
  ],
  resolution: {
    resolved_count: 2,
    unresolved_count: 0,
    method_counts: { alias: 1, fuzzy: 1 },
  },
  safety: {
    catalog_count: 50,
    excluded_count: 34,
    downranked_count: 7,
    eligible_count: 16,
    in_plan_count: 9,
    rules_fired: ['equipment_unavailable', 'injury_region_stress'],
    rule_fire_count: 41,
    validation_corrections: 0,
    validation_passed: true,
    hallucinated_ids: 0,
  },
  adjustment: null,
  mcp: null,
  graph_query_count: 212,
  llm_provider: 'stub',
  llm_latency_ms: 9.6,
  llm_input_tokens: null,
  llm_output_tokens: null,
};

export const copilotTrace: RequestTrace = {
  request_id: 'req9aa2bb02',
  workflow: 'copilot',
  member_id: 'mbr_01HX9JORDAN',
  total_duration_ms: 18.3,
  started_at: '2026-08-13T00:15:04+00:00',
  status: 'ok',
  error_kind: null,
  spans: [],
  resolution: null,
  safety: null,
  adjustment: null,
  mcp: {
    intent: 'ADHERENCE_TREND',
    mode: 'mcp',
    tools_planned: ['get_member_metric_trend'],
    tools_called: ['get_member_metric_trend'],
    tool_duration_ms: null,
    authoritative_safety: true,
    safety_corrected: false,
    generator: 'stub',
  },
  graph_query_count: 4,
  llm_provider: 'stub',
  llm_latency_ms: null,
  llm_input_tokens: null,
  llm_output_tokens: null,
};

export const traces: RequestTrace[] = [generateTrace, copilotTrace];
