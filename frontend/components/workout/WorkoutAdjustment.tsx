'use client';

import { useState } from 'react';

import { Badge, Button, ErrorNote, cx } from '@/components/ui/primitives';
import type { AdjustmentDiff, PlanChange } from '@/lib/types';

/**
 * Coach-facing adjustment input.
 *
 * The wording matters: this does not "edit" the plan. Every adjustment re-runs
 * the whole deterministic pipeline server-side, so a constraint expressed here
 * is enforced by graph traversal rather than by a model reading the sentence.
 * The UI says so, because a coach reasonably assumes the opposite.
 */

export const ADJUSTMENT_PRESETS = [
  'Exclude deadlifts',
  'Only use dumbbells',
  'Make it more quad focused without aggravating her knee',
  'Make it 30 minutes',
  'Avoid exercises that stress her knee',
] as const;

export function WorkoutAdjustment({
  onAdjust,
  isPending,
  error,
  disabled,
}: {
  onAdjust: (adjustment: string) => void;
  isPending: boolean;
  error: Error | null;
  disabled: boolean;
}) {
  const [text, setText] = useState('');

  const submit = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed || isPending || disabled) return;
    onAdjust(trimmed);
    setText('');
  };

  return (
    <section
      aria-label="Adjust this workout"
      className="border-t border-ink-200 px-5 py-4"
    >
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <span className="label-caps">Adjust this workout</span>
        <span className="text-[9.5px] text-ink-400">
          Re-runs concept resolution, graph safety and the final gate
        </span>
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          submit(text);
        }}
        className="flex gap-2"
      >
        <label className="sr-only" htmlFor="adjustment-input">
          Adjustment
        </label>
        <input
          id="adjustment-input"
          type="text"
          value={text}
          disabled={disabled}
          onChange={(event) => setText(event.target.value)}
          placeholder="e.g. exclude deadlifts, or make it 30 minutes"
          className={cx(
            'min-w-0 flex-1 rounded-lg border border-ink-200 px-3 py-2 text-2xs',
            'placeholder:text-ink-400 focus:border-brand-400 focus:outline-none',
            'disabled:bg-ink-50 disabled:text-ink-400',
          )}
        />
        <Button type="submit" size="sm" disabled={disabled || isPending || !text.trim()}>
          {isPending ? 'Re-running…' : 'Apply'}
        </Button>
      </form>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {ADJUSTMENT_PRESETS.map((preset) => (
          <button
            key={preset}
            type="button"
            disabled={disabled || isPending}
            onClick={() => submit(preset)}
            className={cx(
              'rounded-full border border-ink-200 px-2 py-0.5 text-[10px] text-ink-600',
              'transition-colors hover:border-brand-300 hover:bg-brand-50 hover:text-brand-800',
              'disabled:cursor-not-allowed disabled:opacity-50',
            )}
          >
            {preset}
          </button>
        ))}
      </div>

      {disabled ? (
        <p className="mt-2 text-[10.5px] text-ink-400">
          Generate a workout first — an adjustment needs a plan to compare against.
        </p>
      ) : null}

      {error ? (
        <div className="mt-2">
          <ErrorNote message={error.message} />
        </div>
      ) : null}
    </section>
  );
}

/**
 * What the adjustment changed, and why.
 *
 * Every reason is rendered from the backend diff. Nothing here claims an added
 * exercise *replaces* a removed one — the graph encodes no such equivalence,
 * and the ranker simply scored differently once the constraints changed.
 */
export function AdjustmentDiffView({
  diff,
  adjustment,
}: {
  diff: AdjustmentDiff;
  adjustment: string;
}) {
  const sections: Array<{
    key: string;
    title: string;
    items: PlanChange[];
    tone: 'danger' | 'safe' | 'caution';
  }> = [
    { key: 'removed', title: 'Removed', items: diff.removed, tone: 'danger' },
    { key: 'added', title: 'Added', items: diff.added, tone: 'safe' },
    { key: 'downranked', title: 'Down-ranked', items: diff.downranked, tone: 'caution' },
  ];

  return (
    <section aria-label="Adjustment result" className="border-t border-ink-200 px-5 py-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="label-caps">Adjustment applied</span>
        <Badge tone="brand">“{adjustment}”</Badge>
        <span className="text-[10px] text-ink-500">
          {diff.counts.removed ?? 0} removed · {diff.counts.added ?? 0} added ·{' '}
          {diff.counts.downranked ?? 0} down-ranked · {diff.counts.retained ?? 0} kept
        </span>
      </div>

      {diff.notes.map((note) => (
        <p key={note} className="mb-2 text-[10.5px] leading-relaxed text-ink-600">
          {note}
        </p>
      ))}

      <div className="grid gap-2 lg:grid-cols-3">
        {sections.map((section) =>
          section.items.length ? (
            <div key={section.key}>
              <div className="mb-1 flex items-center gap-1.5">
                <Badge tone={section.tone}>{section.title}</Badge>
                <span className="text-[10px] text-ink-400">{section.items.length}</span>
              </div>
              <ul className="space-y-1.5">
                {section.items.map((change) => (
                  <li
                    key={`${section.key}-${change.exercise_id}`}
                    className="rounded-lg border border-ink-200 bg-white p-2"
                  >
                    <div className="flex flex-wrap items-baseline justify-between gap-1">
                      <span className="text-2xs font-medium text-navy-900">
                        {change.exercise}
                      </span>
                      {change.score_before != null && change.score_after != null ? (
                        <span className="font-mono text-[9.5px] text-ink-400">
                          {change.score_before} → {change.score_after}
                        </span>
                      ) : null}
                    </div>

                    {change.now_excluded ? (
                      <div className="mt-0.5">
                        <Badge tone="danger">Now ineligible</Badge>
                      </div>
                    ) : null}

                    {change.reasons.length ? (
                      <p className="mt-1 text-[10px] leading-relaxed text-ink-600">
                        {change.reasons[0]}
                      </p>
                    ) : null}

                    {change.rule_ids.length ? (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {change.rule_ids.slice(0, 2).map((ruleId) => (
                          <span
                            key={ruleId}
                            className="rounded bg-ink-100 px-1 font-mono text-[9px] text-ink-500"
                          >
                            {ruleId}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null,
        )}
      </div>

      <p className="mt-2 text-[10.5px] text-ink-500">
        The model never edited the previous plan. The adjustment became part of a
        new coach request and the whole deterministic pipeline ran again, so every
        exclusion here was re-derived from the graph.
      </p>
    </section>
  );
}
