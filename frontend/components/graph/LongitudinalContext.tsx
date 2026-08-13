'use client';

import { Badge, cx } from '@/components/ui/primitives';
import type { MemberTrajectory, ProgressionState, TrendDirection } from '@/lib/types';

/**
 * The deterministic longitudinal reading behind a plan.
 *
 * Two things this component deliberately does not do:
 *
 * 1. **It does not compute.** Every value is rendered from the payload. The
 *    frontend never derives a direction or a progression state from raw
 *    observations — that would be a second implementation of the trend, which
 *    is exactly the drift the shared service exists to prevent.
 * 2. **It does not present a clinical assessment.** The injury row is labelled
 *    as a recorded status, because that is what it is.
 */

const DIRECTION_TONE: Record<TrendDirection, string> = {
  improving: 'text-safe-700',
  declining: 'text-danger-700',
  flat: 'text-ink-600',
  insufficient_data: 'text-ink-400',
};

const PROGRESSION_COPY: Record<ProgressionState, { label: string; hint: string }> = {
  progress: {
    label: 'Progress',
    hint: 'Adherence and training load support adding stimulus.',
  },
  hold: {
    label: 'Hold',
    hint: 'Signals argue against adding load this session.',
  },
  regress: {
    label: 'Regress',
    hint: 'Recorded injury status warrants reducing load.',
  },
  insufficient_data: {
    label: 'Insufficient data',
    hint: 'Not enough history to judge progression.',
  },
};

export function LongitudinalContext({ trajectory }: { trajectory: MemberTrajectory }) {
  const { progression, adherence, sleep, training_load: load, bias } = trajectory;
  const copy = PROGRESSION_COPY[progression.state];

  const signals = [
    {
      label: 'Adherence',
      value:
        adherence.direction === 'insufficient_data'
          ? 'insufficient data'
          : `${adherence.direction} · ${adherence.first}% → ${adherence.latest}% over ${adherence.observations} weeks`,
      tone: DIRECTION_TONE[adherence.direction],
    },
    {
      label: 'Sleep',
      value:
        sleep.direction === 'insufficient_data'
          ? 'insufficient data'
          : `${sleep.direction} · avg ${sleep.average_recent}h over ${sleep.nights} nights`,
      tone: DIRECTION_TONE[sleep.direction],
    },
    {
      label: 'Training load',
      value:
        load.state === 'insufficient_data'
          ? 'insufficient data'
          : `${load.state} · ${load.sessions_per_week}/week against a target of ${load.target_sessions_per_week}`,
      tone: load.state === 'low' ? 'text-caution-700' : 'text-ink-600',
    },
  ];

  return (
    <section aria-label="Longitudinal context">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="label-caps">Longitudinal context</span>
        <Badge
          tone={progression.state === 'hold' ? 'caution' : 'neutral'}
          title={copy.hint}
        >
          Progression: {copy.label}
        </Badge>
        {progression.state !== 'insufficient_data' ? (
          <Badge tone="neutral" title="How volume was biased for this session">
            {bias.volume_bias} volume
          </Badge>
        ) : null}
      </div>

      <dl className="grid gap-1.5 sm:grid-cols-3">
        {signals.map((signal) => (
          <div
            key={signal.label}
            className="rounded-lg border border-ink-200 bg-white px-3 py-2"
          >
            <dt className="text-[10px] uppercase tracking-wide text-ink-400">
              {signal.label}
            </dt>
            <dd className={cx('text-2xs font-medium', signal.tone)}>{signal.value}</dd>
          </div>
        ))}
      </dl>

      {progression.rationale.length ? (
        <ul className="mt-2 space-y-0.5">
          {progression.rationale.map((reason) => (
            <li key={reason} className="text-[10.5px] text-ink-500">
              · {reason}
            </li>
          ))}
        </ul>
      ) : null}

      <p className="mt-2 text-[10.5px] text-ink-500">
        Computed in Python from the member graph, then used for{' '}
        <strong className="font-medium">ranking and volume only</strong>. It never
        decides eligibility — hard safety exclusions are applied before any of this
        arithmetic runs.
        {trajectory.injury_trajectory.source === 'recorded_status' ? (
          <>
            {' '}
            Injury trajectory is{' '}
            <strong className="font-medium">
              {trajectory.injury_trajectory.state}
            </strong>
            , read from the recorded status — not inferred from adherence or sleep.
          </>
        ) : null}
      </p>
    </section>
  );
}
