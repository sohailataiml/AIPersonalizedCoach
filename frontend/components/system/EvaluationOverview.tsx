'use client';

import { Badge, Card, CardHead, cx } from '@/components/ui/primitives';
import type {
  EvaluationInvariant,
  EvaluationMetric,
  EvaluationRun,
} from '@/lib/types';

/**
 * The top of the System Quality page: "is the AI system behaving safely?".
 *
 * Every number here is read from the evaluation artifact. Nothing is
 * hard-coded, and nothing is averaged across categories — a blended score would
 * let a safety escape hide behind a good resolver run.
 */

function metricOf(run: EvaluationRun, key: string): EvaluationMetric | undefined {
  return run.metrics.find((metric) => metric.key === key);
}

function percent(metric: EvaluationMetric | undefined): string {
  if (!metric || metric.value === null) return 'n/a';
  return `${(metric.value * 100).toFixed(metric.value === 1 ? 0 : 1)}%`;
}

export function KpiCards({ run }: { run: EvaluationRun }) {
  const safety = metricOf(run, 'hard_safety_satisfaction');
  const resolver = metricOf(run, 'concept_resolution_accuracy');
  const provenance = metricOf(run, 'provenance_coverage');
  const parity = metricOf(run, 'mcp_safety_parity');

  const cards = [
    {
      key: 'cases',
      label: 'Evaluation cases',
      value: `${run.passed_cases} / ${run.total_cases}`,
      sub: `${run.failed_cases} failing`,
      tone: run.failed_cases === 0 ? 'safe' : 'danger',
    },
    {
      key: 'safety',
      label: 'Safety constraints',
      value: safety ? `${safety.numerator} / ${safety.denominator}` : 'n/a',
      sub: percent(safety),
      tone: safety && safety.numerator === safety.denominator ? 'safe' : 'danger',
    },
    {
      key: 'unsafe',
      label: 'Unsafe escapes',
      value: `${run.unsafe_escapes}`,
      sub: 'survived final validation',
      tone: run.unsafe_escapes === 0 ? 'safe' : 'danger',
    },
    {
      key: 'resolver',
      label: 'Concept resolution',
      value: resolver ? `${resolver.numerator} / ${resolver.denominator}` : 'n/a',
      sub: percent(resolver),
      tone: resolver && resolver.numerator === resolver.denominator ? 'safe' : 'caution',
    },
    {
      key: 'provenance',
      label: 'Provenance coverage',
      value: provenance ? `${provenance.numerator} / ${provenance.denominator}` : 'n/a',
      sub: percent(provenance),
      tone:
        provenance && provenance.numerator === provenance.denominator
          ? 'safe'
          : 'caution',
    },
    {
      key: 'parity',
      label: 'MCP safety parity',
      value: parity ? `${parity.numerator} / ${parity.denominator}` : 'n/a',
      sub: percent(parity),
      tone: parity && parity.numerator === parity.denominator ? 'safe' : 'danger',
    },
    {
      key: 'latency',
      label: 'Case latency',
      value: run.latency.p95_ms != null ? `${run.latency.p95_ms.toFixed(0)} ms` : 'n/a',
      sub: `p50 ${run.latency.p50_ms?.toFixed(0) ?? '—'} ms · p95`,
      tone: 'neutral',
    },
  ] as const;

  return (
    <ul
      aria-label="Evaluation KPIs"
      className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7"
    >
      {cards.map((card) => (
        <li
          key={card.key}
          data-testid={`kpi-${card.key}`}
          className={cx(
            'rounded-xl border bg-white p-3',
            card.tone === 'danger' ? 'border-danger-300' : 'border-ink-200',
          )}
        >
          <div className="text-[10px] uppercase tracking-wide text-ink-400">
            {card.label}
          </div>
          <div
            className={cx(
              'mt-1 text-lg font-semibold tabular-nums',
              card.tone === 'danger' ? 'text-danger-700' : 'text-navy-900',
            )}
          >
            {card.value}
          </div>
          <div className="text-[10px] text-ink-500">{card.sub}</div>
        </li>
      ))}
    </ul>
  );
}

export function SafetyInvariants({ invariants }: { invariants: EvaluationInvariant[] }) {
  // Failing invariants first: a broken guarantee must not sit below eight
  // green ticks where a reader could miss it.
  const ordered = [...invariants].sort(
    (a, b) => Number(a.holds) - Number(b.holds),
  );
  const broken = ordered.filter((invariant) => !invariant.holds);

  return (
    <Card>
      <CardHead
        title="Safety invariants"
        right={
          <Badge tone={broken.length ? 'danger' : 'safe'}>
            {invariants.length - broken.length} / {invariants.length} proven
          </Badge>
        }
      />
      <div className="px-5 pb-4">
        <p className="mb-2 text-[10.5px] text-ink-500">
          Each status is computed from executed evaluation cases — a tick always
          traces back to evidence, never to an author&apos;s confidence.
        </p>
        <ul className="space-y-1">
          {ordered.map((invariant) => (
            <li
              key={invariant.key}
              data-testid={`invariant-${invariant.key}`}
              className={cx(
                'flex items-start gap-2 rounded-lg border px-3 py-1.5',
                invariant.holds
                  ? 'border-ink-200 bg-white'
                  : 'border-danger-300 bg-danger-50',
              )}
            >
              <span
                aria-hidden
                className={cx(
                  'mt-px font-bold',
                  invariant.holds ? 'text-safe-600' : 'text-danger-600',
                )}
              >
                {invariant.holds ? '✓' : '✕'}
              </span>
              <span className="min-w-0 flex-1">
                <span
                  className={cx(
                    'block text-2xs',
                    invariant.holds ? 'text-ink-700' : 'font-semibold text-danger-800',
                  )}
                >
                  {invariant.statement}
                </span>
                <span className="block text-[9.5px] text-ink-400">
                  {invariant.holds
                    ? `proven by ${invariant.proven_by.length} case(s)`
                    : invariant.detail ??
                      `failing: ${invariant.failed_by.join(', ')}`}
                </span>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  );
}

const BAR_WIDTH = 18;

export function QualityByCategory({ metrics }: { metrics: EvaluationMetric[] }) {
  const measured = metrics.filter((metric) => metric.denominator > 0);

  return (
    <Card>
      <CardHead title="Quality by category" />
      <div className="px-5 pb-4">
        <ul className="space-y-1.5">
          {measured.map((metric) => {
            const ratio = metric.value ?? 0;
            const good = metric.higher_is_better
              ? metric.numerator === metric.denominator
              : metric.numerator === 0;
            const filled = Math.round(BAR_WIDTH * ratio);
            return (
              <li
                key={metric.key}
                data-testid={`metric-${metric.key}`}
                className="flex items-center gap-2"
              >
                <span className="w-44 shrink-0 text-2xs text-ink-600">
                  {metric.label}
                </span>
                <span className="w-16 shrink-0 text-right font-mono text-[10px] tabular-nums text-ink-700">
                  {metric.numerator}/{metric.denominator}
                </span>
                <span
                  aria-hidden
                  className={cx(
                    'font-mono text-[11px] leading-none',
                    good ? 'text-safe-600' : 'text-caution-600',
                  )}
                >
                  {'█'.repeat(filled)}
                  <span className="text-ink-200">
                    {'█'.repeat(BAR_WIDTH - filled)}
                  </span>
                </span>
                <span className="w-12 shrink-0 text-right text-[10px] tabular-nums text-ink-500">
                  {percent(metric)}
                </span>
              </li>
            );
          })}
        </ul>
        <p className="mt-2 text-[10.5px] text-ink-500">
          Ratios, not a blended score. Categories measure different things, so
          they are never averaged into one number.
        </p>
      </div>
    </Card>
  );
}
