'use client';

import { useState } from 'react';

import {
  Badge,
  Card,
  CardHead,
  EmptyState,
  cx,
} from '@/components/ui/primitives';
import type { NodeSpan, RequestTrace, TraceZone } from '@/lib/types';

/**
 * Runtime observability.
 *
 * Traces answer "what happened during this request?" — as opposed to the
 * evaluation sections above, which answer "does the system behave correctly
 * across known scenarios?". The page shows both and never blends them.
 *
 * These payloads carry ids, durations and aggregate counts only: no member
 * payload, no prompt body, no coach question, no MCP protocol content. That is
 * enforced by the backend contract, not by this component choosing what to
 * render.
 */

/** The node after which only graph-approved candidates continue. */
const BOUNDARY_NODE = 'rank_candidates';

const ZONE_LABEL: Record<TraceZone, string> = {
  deterministic: 'Deterministic',
  generative: 'Generative',
  mcp: 'MCP',
};

const NODE_LABEL: Record<string, string> = {
  load_member: 'load_member',
  parse_intent_and_resolve: 'parse_intent + resolve',
  analyze_longitudinal_context: 'analyze_longitudinal',
  evaluate_safety: 'evaluate_safety',
  rank_candidates: 'rank_candidates',
  compose_workout_llm: 'compose_workout (LLM)',
  validate_workout: 'validate_workout',
  build_provenance: 'build_provenance',
  mcp_tool_calls: 'mcp tool calls',
};

export function ExecutionTraces({ traces }: { traces: RequestTrace[] }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected =
    traces.find((trace) => trace.request_id === selectedId) ?? traces[0] ?? null;

  return (
    <Card>
      <CardHead
        title="Recent execution traces"
        right={<Badge tone="neutral">{traces.length} in buffer</Badge>}
      />

      {traces.length ? (
        <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div
            role="region"
            aria-label="Trace list"
            className="scrollbar-slim max-h-[440px] overflow-y-auto border-b border-ink-200 lg:border-b-0 lg:border-r"
          >
            <table className="w-full border-collapse">
              <thead className="sticky top-0 z-10 bg-ink-50">
                <tr className="text-left text-[9.5px] uppercase tracking-wide text-ink-400">
                  <th className="px-4 py-1.5 font-medium">Request</th>
                  <th className="px-2 py-1.5 font-medium">Workflow</th>
                  <th className="px-2 py-1.5 text-right font-medium">Safety</th>
                  <th className="px-2 py-1.5 text-right font-medium">LLM</th>
                  <th className="px-4 py-1.5 text-right font-medium">Total</th>
                </tr>
              </thead>
              <tbody>
                {traces.map((trace) => (
                  <tr key={trace.request_id}>
                    <td colSpan={5} className="p-0">
                      <button
                        type="button"
                        onClick={() => setSelectedId(trace.request_id)}
                        aria-label={`Inspect request ${trace.request_id}`}
                        className={cx(
                          'flex w-full items-center gap-2 border-b border-ink-100 px-4 py-1.5 text-left',
                          selected?.request_id === trace.request_id
                            ? 'bg-brand-50'
                            : 'hover:bg-ink-50',
                        )}
                      >
                        <span className="w-24 shrink-0 truncate font-mono text-[9.5px] text-ink-500">
                          {trace.request_id}
                        </span>
                        <span className="w-16 shrink-0 text-[10px] text-navy-900">
                          {trace.workflow}
                        </span>
                        <span className="flex-1 text-right font-mono text-[9.5px] tabular-nums text-ink-500">
                          {spanMs(trace.spans, 'evaluate_safety')}
                        </span>
                        <span className="w-14 text-right font-mono text-[9.5px] tabular-nums text-ink-500">
                          {trace.llm_latency_ms != null
                            ? `${trace.llm_latency_ms.toFixed(1)} ms`
                            : '—'}
                        </span>
                        <span className="w-16 text-right font-mono text-[9.5px] tabular-nums text-navy-900">
                          {trace.total_duration_ms.toFixed(1)} ms
                        </span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="scrollbar-slim max-h-[440px] overflow-y-auto bg-ink-50/50 p-4">
            {selected ? <TraceDetail trace={selected} /> : null}
          </div>
        </div>
      ) : (
        <EmptyState
          title="No requests traced yet"
          body="Generate a workout or ask the copilot something, then return here. Traces are held in memory for this process only."
        />
      )}
    </Card>
  );
}

function spanMs(spans: NodeSpan[], name: string): string {
  const span = spans.find((candidate) => candidate.name === name);
  return span ? `${span.duration_ms.toFixed(1)} ms` : '—';
}

export function TraceDetail({ trace }: { trace: RequestTrace }) {
  const longest = Math.max(1, ...trace.spans.map((span) => span.duration_ms));
  const zones = trace.spans.reduce<Record<string, number>>((acc, span) => {
    acc[span.zone] = (acc[span.zone] ?? 0) + span.duration_ms;
    return acc;
  }, {});

  return (
    <section aria-label="Trace detail" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-mono text-xs font-semibold text-navy-900">
          {trace.request_id}
        </h3>
        <Badge tone={trace.status === 'ok' ? 'safe' : 'danger'}>
          {trace.workflow} · {trace.status}
        </Badge>
      </div>

      <ol className="space-y-0.5">
        {trace.spans.map((span, index) => (
          <li key={span.name}>
            {span.name !== BOUNDARY_NODE && index > 0 &&
            trace.spans[index - 1]?.name === BOUNDARY_NODE ? (
              <Boundary />
            ) : null}
            <div className="flex items-center gap-2">
              <span className="w-40 shrink-0 truncate text-[10px] text-ink-600">
                {NODE_LABEL[span.name] ?? span.name}
              </span>
              <span className="h-2 flex-1 overflow-hidden rounded-full bg-ink-100">
                <span
                  className={cx(
                    'block h-full rounded-full',
                    span.zone === 'generative'
                      ? 'bg-caution-400'
                      : span.zone === 'mcp'
                        ? 'bg-brand-400'
                        : 'bg-graph-400',
                  )}
                  style={{ width: `${(span.duration_ms / longest) * 100}%` }}
                />
              </span>
              <span className="w-16 shrink-0 text-right font-mono text-[9.5px] tabular-nums text-ink-500">
                {span.duration_ms.toFixed(2)} ms
              </span>
            </div>
          </li>
        ))}
      </ol>

      <div className="flex items-center justify-between border-t border-ink-200 pt-1.5">
        <span className="text-2xs font-medium text-navy-900">Total</span>
        <span className="font-mono text-[10px] tabular-nums text-navy-900">
          {trace.total_duration_ms.toFixed(2)} ms
        </span>
      </div>

      <div>
        <div className="label-caps mb-1">Where the time went</div>
        <ul className="space-y-0.5">
          {Object.entries(zones).map(([zone, ms]) => (
            <li key={zone} className="flex justify-between text-[10px]">
              <span className="text-ink-600">
                {ZONE_LABEL[zone as TraceZone] ?? zone}
              </span>
              <span className="font-mono tabular-nums text-ink-700">
                {ms.toFixed(2)} ms
              </span>
            </li>
          ))}
        </ul>
      </div>

      {trace.safety ? (
        <div>
          <div className="label-caps mb-1">Safety</div>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px]">
            <Stat label="Catalog" value={trace.safety.catalog_count} />
            <Stat label="Excluded" value={trace.safety.excluded_count} />
            <Stat label="Down-ranked" value={trace.safety.downranked_count} />
            <Stat label="Eligible" value={trace.safety.eligible_count} />
            <Stat label="Final plan" value={trace.safety.in_plan_count} />
            <Stat
              label="Validation corrections"
              value={trace.safety.validation_corrections}
            />
            <Stat label="Rules fired" value={trace.safety.rule_fire_count} />
            <Stat
              label="Graph queries"
              value={trace.graph_query_count ?? '—'}
            />
          </dl>
          {trace.safety.rules_fired.length ? (
            <div className="mt-1 flex flex-wrap gap-1">
              {trace.safety.rules_fired.map((rule) => (
                <span
                  key={rule}
                  className="rounded bg-ink-100 px-1 font-mono text-[9px] text-ink-500"
                >
                  {rule}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {trace.adjustment ? (
        <div>
          <div className="label-caps mb-1">Adjustment</div>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px]">
            <Stat label="Removed" value={trace.adjustment.removed_count} />
            <Stat label="Added" value={trace.adjustment.added_count} />
            <Stat label="Down-ranked" value={trace.adjustment.downranked_count} />
            <Stat
              label="Newly ineligible"
              value={trace.adjustment.newly_excluded_count}
            />
            <Stat
              label="Baseline re-run"
              value={
                trace.adjustment.baseline_rerun_ms != null
                  ? `${trace.adjustment.baseline_rerun_ms.toFixed(1)} ms`
                  : '—'
              }
            />
            <Stat
              label="Duration"
              value={
                trace.adjustment.duration_minutes != null
                  ? `${trace.adjustment.duration_minutes} min`
                  : '—'
              }
            />
          </dl>
        </div>
      ) : null}

      <p className="text-[10px] text-ink-400">
        Execution telemetry only. No member payload, prompt body or model
        reasoning is recorded.
      </p>
    </section>
  );
}

function Boundary() {
  return (
    <div className="my-1 flex items-center gap-2" role="separator">
      <span className="h-px flex-1 bg-navy-300" />
      <span className="whitespace-nowrap text-[9px] font-semibold uppercase tracking-wide text-navy-700">
        Safe candidate boundary
      </span>
      <span className="h-px flex-1 bg-navy-300" />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <>
      <dt className="text-ink-500">{label}</dt>
      <dd className="text-right font-mono tabular-nums text-ink-700">{value}</dd>
    </>
  );
}

export function McpObservability({ traces }: { traces: RequestTrace[] }) {
  const copilot = traces.filter((trace) => trace.mcp !== null);

  return (
    <Card>
      <CardHead
        title="MCP observability"
        right={<Badge tone="neutral">{copilot.length} copilot request(s)</Badge>}
      />
      {copilot.length ? (
        <div className="scrollbar-slim max-h-[280px] overflow-x-auto px-5 pb-4">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="text-[9.5px] uppercase tracking-wide text-ink-400">
                <th className="py-1.5 font-medium">Intent</th>
                <th className="py-1.5 font-medium">Tools called</th>
                <th className="py-1.5 font-medium">Mode</th>
                <th className="py-1.5 font-medium">Authoritative</th>
                <th className="py-1.5 font-medium">Corrected</th>
                <th className="py-1.5 text-right font-medium">Duration</th>
              </tr>
            </thead>
            <tbody>
              {copilot.map((trace) => (
                <tr
                  key={trace.request_id}
                  data-testid={`mcp-row-${trace.request_id}`}
                  className="border-t border-ink-100"
                >
                  <td className="py-1.5 text-2xs text-navy-900">
                    {trace.mcp?.intent ?? '—'}
                  </td>
                  <td className="py-1.5">
                    <span className="flex flex-wrap gap-1">
                      {(trace.mcp?.tools_called ?? []).map((tool) => (
                        <span
                          key={tool}
                          className="rounded bg-ink-100 px-1 font-mono text-[9px] text-ink-600"
                        >
                          {tool}
                        </span>
                      ))}
                      {!trace.mcp?.tools_called.length ? (
                        <span className="text-[10px] text-ink-400">none</span>
                      ) : null}
                    </span>
                  </td>
                  <td className="py-1.5">
                    <Badge tone={trace.mcp?.mode === 'mcp' ? 'graph' : 'caution'}>
                      {trace.mcp?.mode ?? 'unknown'}
                    </Badge>
                  </td>
                  <td className="py-1.5 text-[10px] text-ink-600">
                    {trace.mcp?.authoritative_safety ? 'yes' : 'no'}
                  </td>
                  <td className="py-1.5 text-[10px] text-ink-600">
                    {trace.mcp?.safety_corrected ? 'yes' : 'no'}
                  </td>
                  <td className="py-1.5 text-right font-mono text-[9.5px] tabular-nums text-ink-500">
                    {trace.total_duration_ms.toFixed(1)} ms
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[10px] text-ink-400">
            The coach&apos;s question is never recorded — only its classified
            intent and the tool names that ran.
          </p>
        </div>
      ) : (
        <EmptyState
          title="No copilot requests traced"
          body="Ask the copilot a question on the coach dashboard to populate this table."
        />
      )}
    </Card>
  );
}
