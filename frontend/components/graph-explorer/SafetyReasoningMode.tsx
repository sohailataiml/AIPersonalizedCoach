'use client';

import { DecisionPaths } from '@/components/graph/DecisionPaths';
import {
  Badge,
  EmptyState,
  ErrorNote,
  Spinner,
  StatusPill,
} from '@/components/ui/primitives';
import type { GraphSafetyResponse } from '@/lib/types';

/**
 * Safety Reasoning mode.
 *
 * The explorer derives **no** safety of its own. It asks the backend, which
 * calls the same `SafetyEngine` the workout pipeline calls, and renders the
 * result with `DecisionPaths` — the same component the coach's graph panel
 * uses. There is deliberately no second interpretation of provenance here.
 *
 * Longitudinal personalization is shown in its own block, because it moves
 * ranking and never eligibility. Folding it into the decision would blur the
 * boundary this project exists to keep sharp.
 */
export function SafetyReasoningMode({
  safety,
  isLoading,
  error,
  exerciseName,
}: {
  safety: GraphSafetyResponse | null;
  isLoading: boolean;
  error: Error | null;
  exerciseName: string | null;
}) {
  if (error) {
    return <ErrorNote message={error.message} />;
  }
  if (isLoading) {
    return <Spinner label="Asking the safety engine…" />;
  }
  if (!safety) {
    return (
      <EmptyState
        title="Select an exercise"
        body="Search for an exercise above — the explorer will ask the deterministic safety engine for its decision and show the graph paths behind it."
      />
    );
  }

  const status =
    safety.decision === 'excluded'
      ? 'excluded'
      : safety.decision === 'downranked'
        ? 'cautioned'
        : 'safe';

  return (
    <section aria-label="Safety reasoning" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-ink-200 bg-white px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] uppercase tracking-wide text-ink-400">
            Member
          </span>
          <span className="text-2xs font-medium text-navy-900">
            {safety.member_name}
          </span>
          <span aria-hidden className="h-4 w-px bg-ink-200" />
          <span className="text-[10px] uppercase tracking-wide text-ink-400">
            Exercise
          </span>
          <span className="text-2xs font-medium text-navy-900">
            {exerciseName ?? safety.exercise_name}
          </span>
        </div>
        <StatusPill status={status} />
      </div>

      <p className="text-[10.5px] text-ink-500">
        Evaluated against the request:{' '}
        <span className="italic">“{safety.prompt}”</span>
      </p>

      {safety.reasons.length ? (
        <ul className="space-y-1">
          {safety.reasons.map((reason) => (
            <li key={reason} className="text-2xs leading-relaxed text-ink-600">
              {reason}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-2xs text-ink-600">
          No safety rule fired for this exercise against this request.
        </p>
      )}

      {safety.traversals.length ? (
        <DecisionPaths traversals={safety.traversals} />
      ) : (
        <p className="text-[10.5px] text-ink-500">
          No graph evidence: nothing in the member&apos;s graph constrains this
          exercise for this request.
        </p>
      )}

      {safety.longitudinal_reasons.length ? (
        <div className="rounded-xl border border-ink-200 bg-ink-50/60 p-3">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="label-caps">Longitudinal personalization</span>
            <Badge tone="neutral">
              {safety.longitudinal_adjustment > 0 ? '+' : ''}
              {safety.longitudinal_adjustment.toFixed(0)} ranking
            </Badge>
          </div>
          <ul className="space-y-0.5">
            {safety.longitudinal_reasons.map((reason) => (
              <li key={reason} className="text-[10.5px] text-ink-600">
                {reason}
              </li>
            ))}
          </ul>
          <p className="mt-1 text-[10px] text-ink-500">
            Shown separately because it moves ranking only — it never decides
            eligibility.
          </p>
        </div>
      ) : null}

      <p className="text-[10px] text-ink-400">
        Computed by the same deterministic SafetyEngine the workout pipeline
        uses. The explorer only asks.
      </p>
    </section>
  );
}
