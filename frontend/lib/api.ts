import type {
  AdjustWorkoutResponse,
  CopilotResponse,
  EvaluationHistory,
  EvaluationRun,
  ExerciseProvenance,
  GenerateWorkoutResponse,
  GraphLegendResponse,
  GraphNodeView,
  GraphSafetyResponse,
  GraphSearchResponse,
  GraphStatsResponse,
  GraphSubgraph,
  HealthResponse,
  MemberHistory,
  MemberSummary,
  TraceListResponse,
} from './types';

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000/api';

/** The single synthetic member supplied with the assessment. */
export const DEFAULT_MEMBER_ID = 'mbr_01HX9JORDAN';

class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    });
  } catch {
    throw new ApiError(
      'Cannot reach the API. Is the backend running on port 8000?',
      0,
    );
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === 'string') detail = body.detail;
    } catch {
      /* keep the default message */
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>('/health'),

  member: (memberId: string) =>
    request<MemberSummary>(`/members/${encodeURIComponent(memberId)}`),

  memberHistory: (memberId: string) =>
    request<MemberHistory>(`/members/${encodeURIComponent(memberId)}/history`),

  generateWorkout: (body: {
    member_id: string;
    prompt: string;
    duration_minutes: number;
  }) =>
    request<GenerateWorkoutResponse>('/workouts/generate', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  /**
   * Apply a coach adjustment. The previous plan is sent as ids only — it is
   * used to compute the diff, never to seed the model. The backend re-runs the
   * whole deterministic pipeline.
   */
  adjustWorkout: (body: {
    member_id: string;
    base_prompt: string;
    adjustment: string;
    duration_minutes: number;
    previous_exercise_ids: string[];
  }) =>
    request<AdjustWorkoutResponse>('/workouts/adjust', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  copilotChat: (body: { member_id: string; message: string }) =>
    request<CopilotResponse>('/copilot/chat', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  /* --- Knowledge Graph Explorer (read-only) ---
   *
   * Every call names a node and a depth. There is deliberately no method that
   * sends a query language: the backend owns the shape of every traversal, and
   * no Bolt URI or credential exists on this side of the boundary.
   */

  graphSearch: (query: string, kinds?: string[], limit = 10) => {
    const params = new URLSearchParams({ q: query, limit: String(limit) });
    if (kinds?.length) params.set('kinds', kinds.join(','));
    return request<GraphSearchResponse>(`/graph/search?${params}`);
  },

  graphNode: (nodeId: string) =>
    request<GraphNodeView>(`/graph/nodes/${encodeURIComponent(nodeId)}`),

  graphNeighborhood: (
    nodeId: string,
    options: { depth?: number; relationships?: string[]; kinds?: string[] } = {},
  ) => {
    const params = new URLSearchParams({ depth: String(options.depth ?? 1) });
    if (options.relationships?.length)
      params.set('relationships', options.relationships.join(','));
    if (options.kinds?.length) params.set('kinds', options.kinds.join(','));
    return request<GraphSubgraph>(
      `/graph/nodes/${encodeURIComponent(nodeId)}/neighborhood?${params}`,
    );
  },

  graphSummary: () => request<GraphStatsResponse>('/graph/summary'),

  graphLegend: () => request<GraphLegendResponse>('/graph/legend'),

  graphSafety: (exerciseId: string) =>
    request<GraphSafetyResponse>(
      `/graph/safety/${encodeURIComponent(exerciseId)}`,
    ),

  /* --- System quality (read-only developer surface) --- */

  /** Null when no evaluation has been run yet — an honest empty state. */
  latestEvaluation: () =>
    request<EvaluationRun | null>('/system/evaluations/latest'),

  evaluationHistory: (limit = 10) =>
    request<EvaluationHistory>(`/system/evaluations?limit=${limit}`),

  traces: (limit = 25) =>
    request<TraceListResponse>(`/system/traces?limit=${limit}`),

  exerciseProvenance: (exerciseId: string) =>
    request<ExerciseProvenance>(
      `/graph/exercises/${encodeURIComponent(exerciseId)}/provenance`,
    ),
};

export { ApiError };
