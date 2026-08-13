'use client';

import type { GenerateWorkoutResponse, HealthResponse } from '@/lib/types';

/**
 * Diagnostics, deliberately collapsed.
 *
 * The timings and request ids are genuinely useful when defending the system,
 * but they are not the coach's job. They live in a closed accordion so the main
 * surface stays a product rather than a console.
 */
export function TechnicalDetails({
  result,
  health,
}: {
  result: GenerateWorkoutResponse | null;
  health?: HealthResponse;
}) {
  if (!result && !health) return null;

  const timings = Object.entries(result?.timings_ms ?? {}).sort(
    ([, a], [, b]) => b - a,
  );
  const slowest = timings[0]?.[1] ?? 1;

  return (
    <details className="group rounded-card border border-ink-200 bg-white">
      <summary
        className="flex cursor-pointer list-none items-center gap-2 px-5 py-2.5
                   text-2xs font-semibold text-ink-600 hover:text-ink-800"
      >
        <svg
          className="h-3 w-3 transition-transform group-open:rotate-90"
          viewBox="0 0 12 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          aria-hidden
        >
          <path d="m4 2 4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        Technical details
        <span className="font-normal text-ink-400">
          pipeline timing, request id, backend
        </span>
      </summary>

      <div className="grid gap-6 border-t border-ink-200 px-5 py-4 md:grid-cols-2">
        {timings.length ? (
          <div>
            <div className="label-caps mb-2">Pipeline timing</div>
            <div className="space-y-1">
              {timings.map(([label, ms]) => (
                <div key={label} className="flex items-center gap-2">
                  <span className="w-44 shrink-0 font-mono text-[10px] text-ink-500">
                    {label}
                  </span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-100">
                    <div
                      className="h-full rounded-full bg-brand-400"
                      style={{ width: `${Math.min(100, (ms / slowest) * 100)}%` }}
                    />
                  </div>
                  <span className="w-14 shrink-0 text-right font-mono text-[10px] text-ink-500">
                    {ms} ms
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        <div>
          <div className="label-caps mb-2">Run metadata</div>
          <dl className="space-y-1 text-[10.5px]">
            {result ? (
              <>
                <Row label="request id" value={result.request_id} mono />
                <Row label="graph backend" value={result.graph_backend} />
                <Row label="composer" value={result.generator} />
                <Row
                  label="post-validation"
                  value={
                    result.safety.post_validation_passed
                      ? 'passed'
                      : `${result.safety.post_validation_rejections} rejected, ${result.safety.post_validation_replacements} replaced`
                  }
                />
                <Row
                  label="catalog"
                  value={`${result.safety.eligible} eligible / ${result.safety.excluded} excluded / ${result.safety.downranked} down-ranked`}
                />
              </>
            ) : null}
            {health ? (
              <>
                <Row
                  label="exercises in graph"
                  value={String(health.graph_stats['node:Exercise'] ?? '—')}
                />
                {/* Deployment facts, reported by the backend. Deliberately no
                    hostname, URI or credential: "which environment, is the
                    graph seeded" is what an operator needs; where it lives is
                    not. */}
                <Row label="environment" value={health.environment ?? 'local'} />
                <Row
                  label="graph seeded"
                  value={health.graph_seeded ? 'yes' : 'no'}
                />
                <Row
                  label="ontology mappings"
                  value={`${health.ontology_mappings ?? 0} verified`}
                />
              </>
            ) : null}
          </dl>
        </div>
      </div>
    </details>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex gap-2">
      <dt className="w-32 shrink-0 text-ink-400">{label}</dt>
      <dd className={mono ? 'font-mono text-ink-600' : 'text-ink-600'}>{value}</dd>
    </div>
  );
}
