'use client';

import { Badge, Card, CardHead, EmptyState, cx } from '@/components/ui/primitives';
import type { EvaluationHistory } from '@/lib/types';

/**
 * Recent evaluation runs.
 *
 * History populates naturally as `make eval` is run. With a single run it shows
 * one row and says so — manufacturing a trend line from one point would be the
 * kind of invented data this whole surface exists to avoid.
 */
export function EvaluationHistoryPanel({ history }: { history: EvaluationHistory }) {
  const runs = history.runs;
  const trend = runs.slice().reverse();
  const maxP95 = Math.max(1, ...trend.map((run) => run.p95_ms ?? 0));

  return (
    <Card>
      <CardHead
        title="Evaluation history"
        right={<Badge tone="neutral">{history.count} run(s)</Badge>}
      />

      {runs.length ? (
        <div className="px-5 pb-4">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="text-[9.5px] uppercase tracking-wide text-ink-400">
                  <th className="py-1.5 font-medium">Run</th>
                  <th className="py-1.5 text-right font-medium">Cases</th>
                  <th className="py-1.5 text-right font-medium">Passed</th>
                  <th className="py-1.5 text-right font-medium">Failed</th>
                  <th className="py-1.5 text-right font-medium">Unsafe</th>
                  <th className="py-1.5 text-right font-medium">P95</th>
                  <th className="py-1.5 text-right font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr
                    key={run.run_id}
                    data-testid={`eval-run-${run.run_id}`}
                    className="border-t border-ink-100"
                  >
                    <td className="py-1.5 font-mono text-[9.5px] text-ink-500">
                      {run.started_at}
                    </td>
                    <td className="py-1.5 text-right font-mono text-[10px] tabular-nums text-ink-700">
                      {run.total_cases}
                    </td>
                    <td className="py-1.5 text-right font-mono text-[10px] tabular-nums text-safe-700">
                      {run.passed_cases}
                    </td>
                    <td
                      className={cx(
                        'py-1.5 text-right font-mono text-[10px] tabular-nums',
                        run.failed_cases ? 'text-danger-700' : 'text-ink-400',
                      )}
                    >
                      {run.failed_cases}
                    </td>
                    <td
                      className={cx(
                        'py-1.5 text-right font-mono text-[10px] tabular-nums',
                        run.unsafe_escapes ? 'text-danger-700' : 'text-ink-400',
                      )}
                    >
                      {run.unsafe_escapes}
                    </td>
                    <td className="py-1.5 text-right font-mono text-[10px] tabular-nums text-ink-500">
                      {run.p95_ms != null ? `${run.p95_ms.toFixed(0)} ms` : '—'}
                    </td>
                    <td className="py-1.5 text-right">
                      <Badge tone={run.status === 'pass' ? 'safe' : 'danger'}>
                        {run.status.toUpperCase()}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {runs.length > 1 ? (
            <div className="mt-3">
              <div className="label-caps mb-1">P95 case latency by run</div>
              <ul className="flex items-end gap-1" aria-label="P95 latency trend">
                {trend.map((run) => (
                  <li
                    key={run.run_id}
                    title={`${run.started_at}: ${run.p95_ms ?? 0} ms`}
                    className="w-6 rounded-t bg-graph-300"
                    style={{
                      height: `${Math.max(4, ((run.p95_ms ?? 0) / maxP95) * 48)}px`,
                    }}
                  />
                ))}
              </ul>
            </div>
          ) : (
            <p className="mt-2 text-[10.5px] text-ink-500">
              One run recorded. Trends appear once{' '}
              <code className="rounded bg-ink-100 px-1 font-mono text-[10px]">
                make eval
              </code>{' '}
              has run more than once — no history is manufactured.
            </p>
          )}
        </div>
      ) : (
        <EmptyState
          title="No evaluation runs yet"
          body="Run `make eval` to produce the first artifact."
        />
      )}
    </Card>
  );
}
