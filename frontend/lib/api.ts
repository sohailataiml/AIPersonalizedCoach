import type {
  CopilotResponse,
  ExerciseProvenance,
  GenerateWorkoutResponse,
  HealthResponse,
  MemberHistory,
  MemberSummary,
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

  copilotChat: (body: { member_id: string; message: string }) =>
    request<CopilotResponse>('/copilot/chat', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  exerciseProvenance: (exerciseId: string) =>
    request<ExerciseProvenance>(
      `/graph/exercises/${encodeURIComponent(exerciseId)}/provenance`,
    ),
};

export { ApiError };
