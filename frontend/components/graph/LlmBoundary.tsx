'use client';

import { cx } from '@/components/ui/primitives';
import type { GraphReasoningSummary } from '@/lib/types';

/**
 * The architectural claim, drawn.
 *
 * Reads left to right: everything before the boundary is deterministic, the
 * candidate set is the only thing that crosses it, and a deterministic gate
 * closes behind the model. Counts are the real ones from the response.
 */
export function LlmBoundary({ summary }: { summary: GraphReasoningSummary }) {
  return (
    <div className="rounded-xl border border-ink-200 bg-ink-50/60 p-3">
      <div className="grid items-stretch gap-2 lg:grid-cols-[1fr_auto_1fr_auto_1fr]">
        <Zone
          tone="deterministic"
          title="Deterministic zone"
          steps={[
            `${summary.concepts_resolved} concepts resolved`,
            `${summary.catalog_count} catalog exercises`,
            `${summary.traversal_count} graph traversals`,
            `${summary.excluded_count} excluded · ${summary.downranked_count} down-ranked`,
          ]}
        />

        <Gate label={`${summary.eligible_count} approved candidates`} />

        <Zone
          tone="generative"
          title="Generative zone"
          steps={[
            'LLM composes the session',
            'Chooses only from approved ids',
            'Assigns sets / reps / rest',
          ]}
        />

        <Gate label="Every id re-checked" />

        <Zone
          tone="deterministic"
          title="Final safety gate"
          steps={[
            'Excluded picks rejected',
            'Invented ids rejected',
            `${summary.in_plan_count} exercises in final plan`,
          ]}
        />
      </div>

      <p className="mt-2.5 text-center text-[10.5px] font-medium text-navy-800">
        Only graph-approved candidates cross this boundary — the model never sees
        a filtered exercise, and never decides safety.
      </p>
    </div>
  );
}

function Zone({
  tone,
  title,
  steps,
}: {
  tone: 'deterministic' | 'generative';
  title: string;
  steps: string[];
}) {
  const isDeterministic = tone === 'deterministic';
  return (
    <div
      className={cx(
        'rounded-lg border p-2.5',
        isDeterministic
          ? 'border-graph-200 bg-graph-50/70'
          : 'border-caution-200 bg-caution-50/70',
      )}
    >
      <div className="mb-1.5 flex items-center gap-1.5">
        <span
          aria-hidden
          className={cx(
            'flex h-3.5 w-3.5 items-center justify-center rounded-full text-[8px] font-bold text-white',
            isDeterministic ? 'bg-graph-600' : 'bg-caution-600',
          )}
        >
          {isDeterministic ? '=' : '~'}
        </span>
        <span
          className={cx(
            'text-[10px] font-semibold uppercase tracking-[0.07em]',
            isDeterministic ? 'text-graph-800' : 'text-caution-800',
          )}
        >
          {title}
        </span>
      </div>
      <ul className="space-y-0.5">
        {steps.map((step) => (
          <li key={step} className="text-[10.5px] leading-snug text-ink-600">
            {step}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Gate({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-center lg:flex-col lg:gap-1">
      <svg
        className="h-4 w-4 shrink-0 rotate-90 text-navy-400 lg:rotate-0"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        aria-hidden
      >
        <path d="M2 8h12M10 4l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="max-w-[92px] text-center text-[9px] font-semibold leading-tight text-navy-700">
        {label}
      </span>
    </div>
  );
}
