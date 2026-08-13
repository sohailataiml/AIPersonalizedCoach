'use client';

import { Badge, cx } from '@/components/ui/primitives';
import type { GraphLegendResponse, GraphStatsResponse } from '@/lib/types';
import { NODE_STYLE } from './GraphCanvas';

/**
 * Collapsible legend and graph summary.
 *
 * Counts come from the seeded graph, never from the brief — if the seed
 * differs from the PRD's numbers, this shows the seed. Relationship
 * descriptions come from the backend glossary so they stay consistent with
 * ARCHITECTURE.md rather than being restated loosely in the UI.
 */
export function GraphLegend({
  legend,
  stats,
}: {
  legend: GraphLegendResponse | null;
  stats: GraphStatsResponse | null;
}) {
  return (
    <details className="group rounded-xl border border-ink-200 bg-white">
      <summary className="cursor-pointer list-none px-4 py-2.5 text-2xs font-semibold text-navy-900">
        <span className="group-open:hidden">Legend and graph summary</span>
        <span className="hidden group-open:inline">Hide legend</span>
        {stats ? (
          <span className="ml-2 font-normal text-ink-500">
            {stats.node_count} nodes · {stats.edge_count} relationships ·{' '}
            {stats.ontology_mappings} ontology mappings
          </span>
        ) : null}
      </summary>

      <div className="grid gap-4 border-t border-ink-200 px-4 py-3 lg:grid-cols-2">
        <div>
          <div className="label-caps mb-1.5">Node types</div>
          <ul className="grid gap-1 sm:grid-cols-2">
            {(legend?.node_kinds ?? []).map((kind) => {
              const style = NODE_STYLE[kind];
              return (
                <li key={kind} className="flex items-center gap-1.5 text-[10px]">
                  <span aria-hidden className="w-4 text-center">
                    {style?.glyph ?? '•'}
                  </span>
                  <span className="text-ink-700">{kind}</span>
                  {stats?.nodes_by_kind[kind] ? (
                    <span className="text-ink-400">
                      {stats.nodes_by_kind[kind]}
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>

        <div>
          <div className="label-caps mb-1.5">Relationship semantics</div>
          <ul className="space-y-1">
            {(legend?.relationships ?? []).map((entry) => (
              <li key={entry.relationship}>
                <div className="flex items-baseline gap-1.5">
                  <span className="font-mono text-[9.5px] font-semibold text-graph-700">
                    {entry.relationship}
                  </span>
                  <span className="text-[9px] text-ink-400">{entry.count}</span>
                </div>
                <p className="text-[10px] leading-snug text-ink-600">
                  {entry.description}
                </p>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </details>
  );
}

export function GraphFilters({
  nodeKinds,
  relationships,
  activeKinds,
  activeRelationships,
  onToggleKind,
  onToggleRelationship,
  onReset,
}: {
  nodeKinds: string[];
  relationships: string[];
  activeKinds: string[];
  activeRelationships: string[];
  onToggleKind: (kind: string) => void;
  onToggleRelationship: (relationship: string) => void;
  onReset: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-[9.5px] uppercase tracking-wide text-ink-400">
        Types
      </span>
      {nodeKinds.map((kind) => (
        <Chip
          key={kind}
          label={kind}
          active={activeKinds.includes(kind)}
          onClick={() => onToggleKind(kind)}
        />
      ))}
      <span aria-hidden className="mx-1 h-4 w-px bg-ink-200" />
      <span className="text-[9.5px] uppercase tracking-wide text-ink-400">
        Relationships
      </span>
      {relationships.map((relationship) => (
        <Chip
          key={relationship}
          label={relationship}
          active={activeRelationships.includes(relationship)}
          onClick={() => onToggleRelationship(relationship)}
          mono
        />
      ))}
      {activeKinds.length || activeRelationships.length ? (
        <button
          type="button"
          onClick={onReset}
          className="ml-1 rounded-full border border-ink-200 px-2 py-0.5 text-[10px] text-ink-600 hover:bg-ink-50"
        >
          Reset filters
        </button>
      ) : null}
    </div>
  );
}

function Chip({
  label,
  active,
  onClick,
  mono = false,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  mono?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cx(
        'rounded-full border px-2 py-0.5 text-[9.5px] transition-colors',
        mono && 'font-mono',
        active
          ? 'border-graph-300 bg-graph-50 text-graph-800'
          : 'border-ink-200 text-ink-600 hover:bg-ink-50',
      )}
    >
      {label}
    </button>
  );
}

export function GraphBackendBadge({ backend }: { backend: string | undefined }) {
  return (
    <Badge tone="neutral" title="Reported by the backend, not assumed by the UI">
      Graph backend: {backend ?? 'unknown'}
    </Badge>
  );
}
