'use client';

import { cx } from '@/components/ui/primitives';
import type { GraphReasoningSummary, MemberTrajectory } from '@/lib/types';

/**
 * The request pipeline, stage by stage, with the boundary marked.
 *
 * Every count is read from the response. The stages are the real workflow
 * nodes — `analyze_longitudinal_context` appears here because it appears in the
 * LangGraph execution graph, not because it makes a nicer diagram.
 */

interface Stage {
  label: string;
  detail: string;
  zone: 'deterministic' | 'generative';
}

export function PipelineFlow({
  summary,
  trajectory,
  timings,
}: {
  summary: GraphReasoningSummary;
  trajectory?: MemberTrajectory | null;
  timings?: Record<string, number>;
}) {
  const stages: Stage[] = [
    { label: 'Coach request', detail: '1 prompt + duration', zone: 'deterministic' },
    {
      label: 'Concept resolution',
      detail: `${summary.concepts_resolved} resolved · ${summary.concepts_unresolved} unresolved`,
      zone: 'deterministic',
    },
    {
      // Named for the workflow node it represents, and deliberately distinct
      // from the "Longitudinal context" panel below - one is a pipeline stage,
      // the other is the reading that stage produced.
      label: 'Longitudinal analysis',
      detail: trajectory
        ? `progression: ${trajectory.progression.state}`
        : 'not computed',
      zone: 'deterministic',
    },
    {
      label: 'Knowledge graph traversal',
      detail: `${summary.traversal_count} traversals`,
      zone: 'deterministic',
    },
    {
      label: 'Safety decisions',
      detail: `${summary.excluded_count} excluded · ${summary.downranked_count} down-ranked`,
      zone: 'deterministic',
    },
    {
      label: 'Safe candidate set',
      detail: `${summary.eligible_count} approved`,
      zone: 'deterministic',
    },
    {
      label: 'LLM composition',
      detail: 'chooses only from approved ids',
      zone: 'generative',
    },
    {
      label: 'Final deterministic validation',
      detail: `${summary.in_plan_count} in plan`,
      zone: 'deterministic',
    },
  ];

  const boundaryBefore = stages.findIndex((stage) => stage.zone === 'generative');

  return (
    <section aria-label="Request pipeline">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <span className="label-caps">Request pipeline</span>
        {timings?.total ? (
          <span className="font-mono text-[9.5px] text-ink-400">
            {timings.total.toFixed(0)} ms end to end
          </span>
        ) : null}
      </div>

      <ol className="grid gap-1">
        {stages.map((stage, index) => (
          <li key={stage.label}>
            {index === boundaryBefore ? <Boundary /> : null}
            <div
              className={cx(
                'flex items-center justify-between gap-2 rounded-lg border px-3 py-1.5',
                stage.zone === 'deterministic'
                  ? 'border-graph-200 bg-graph-50/60'
                  : 'border-caution-200 bg-caution-50/70',
              )}
            >
              <span className="flex min-w-0 items-center gap-2">
                <span
                  aria-hidden
                  className={cx(
                    'flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[8px] font-bold text-white',
                    stage.zone === 'deterministic' ? 'bg-graph-600' : 'bg-caution-600',
                  )}
                  title={
                    stage.zone === 'deterministic'
                      ? 'Deterministic — no model involved'
                      : 'Generative — the model composes here'
                  }
                >
                  {stage.zone === 'deterministic' ? '=' : '~'}
                </span>
                <span className="truncate text-2xs font-medium text-navy-900">
                  {stage.label}
                </span>
              </span>
              <span className="shrink-0 text-[10px] text-ink-500">{stage.detail}</span>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Boundary() {
  return (
    <div className="my-1.5 flex items-center gap-2" role="separator">
      <span className="h-px flex-1 bg-navy-300" />
      <span className="whitespace-nowrap rounded-full bg-navy-800 px-2 py-0.5 text-[9.5px] font-semibold text-white">
        Only graph-approved candidates cross this boundary
      </span>
      <span className="h-px flex-1 bg-navy-300" />
    </div>
  );
}
