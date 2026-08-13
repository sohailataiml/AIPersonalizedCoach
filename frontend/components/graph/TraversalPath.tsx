'use client';

import { Badge, cx } from '@/components/ui/primitives';
import type { GraphNodeKind, GraphTraversal } from '@/lib/types';

/**
 * Renders one traversal as connected, typed nodes.
 *
 * Node types come from the backend (`node.type`) - the UI does not infer them
 * from edge names. That matters: an inferred type would be frontend-invented
 * data sitting inside a panel whose whole purpose is to show what the graph
 * actually holds.
 *
 * `direction: "incoming"` means the hop was read against the stored arrow, and
 * is drawn that way rather than being silently normalised.
 */

const NODE_STYLE: Record<GraphNodeKind, { className: string; glyph: string }> = {
  Member: { className: 'border-navy-300 bg-navy-50 text-navy-900', glyph: '👤' },
  Injury: { className: 'border-danger-300 bg-danger-50 text-danger-800', glyph: '⚕' },
  InjuryCondition: {
    className: 'border-danger-300 bg-danger-50 text-danger-800',
    glyph: '⚕',
  },
  Exercise: { className: 'border-brand-300 bg-brand-50 text-brand-800', glyph: '🏋' },
  AnatomicalRegion: {
    className: 'border-graph-300 bg-graph-50 text-graph-800',
    glyph: '🦴',
  },
  Equipment: { className: 'border-caution-300 bg-caution-50 text-caution-800', glyph: '🧰' },
  MovementPattern: { className: 'border-ink-300 bg-ink-50 text-ink-700', glyph: '➰' },
  MovementFamily: { className: 'border-ink-300 bg-ink-100 text-ink-700', glyph: '🗂' },
  Preference: { className: 'border-ink-300 bg-ink-50 text-ink-700', glyph: '☆' },
  Muscle: { className: 'border-graph-200 bg-graph-50 text-graph-700', glyph: '💪' },
};

export function TraversalPath({
  traversal,
  visibleNodes,
  activeEdge,
  showFacts = true,
}: {
  traversal: GraphTraversal;
  /** Reveal only the first N nodes. Defaults to the whole path. */
  visibleNodes?: number;
  /** Highlight the edge at this index (used by the replay player). */
  activeEdge?: number | null;
  showFacts?: boolean;
}) {
  const edgeFor = (nodeId: string) =>
    traversal.edges.find((edge) => edge.source_id === nodeId);

  const limit = visibleNodes ?? traversal.nodes.length;
  const nodes = traversal.nodes.slice(0, Math.max(0, limit));

  return (
    <div className="rounded-xl border border-ink-200 bg-white p-3">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <Badge tone={traversal.source === 'graph_traversal' ? 'graph' : 'neutral'}>
          {traversal.source === 'graph_traversal'
            ? 'Graph traversal'
            : 'Deterministic set operation'}
        </Badge>
        {traversal.rule_id ? (
          <span className="font-mono text-[9.5px] text-ink-400">{traversal.rule_id}</span>
        ) : null}
      </div>

      {nodes.length ? (
        <ol className="flex flex-col items-start">
          {nodes.map((node, index) => {
            const style = NODE_STYLE[node.type] ?? NODE_STYLE.Exercise;
            const edge = edgeFor(node.id);
            const isNewest = visibleNodes != null && index === nodes.length - 1;
            const edgeIsActive = activeEdge != null && activeEdge === index;
            return (
              <li key={node.id} className="flex w-full flex-col items-start">
                <div
                  className={cx(
                    'graph-node flex items-center gap-1.5 transition-shadow',
                    style.className,
                    isNewest && 'ring-2 ring-graph-400 ring-offset-1',
                  )}
                >
                  <span aria-hidden>{style.glyph}</span>
                  <span className="flex flex-col">
                    <span className="font-semibold">{node.label}</span>
                    <span className="text-[9px] font-normal opacity-70">{node.type}</span>
                  </span>
                </div>

                {edge && index < nodes.length - 1 ? (
                  <div
                    className={cx(
                      'flex items-center gap-1 py-1 pl-4',
                      edgeIsActive && 'rounded bg-graph-50',
                    )}
                  >
                    <svg
                      className={cx(
                        'h-3.5 w-3.5',
                        edgeIsActive ? 'text-graph-600' : 'text-ink-300',
                        edge.direction === 'incoming' && 'rotate-180',
                      )}
                      viewBox="0 0 12 14"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.4"
                      aria-hidden
                    >
                      <path
                        d="M6 1v12M2.5 9.5 6 13l3.5-3.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                    <span className="font-mono text-[9.5px] font-semibold tracking-wide text-graph-700">
                      {edge.relationship}
                    </span>
                    {edge.direction === 'incoming' ? (
                      <span
                        className="rounded bg-ink-100 px-1 text-[8.5px] text-ink-500"
                        title="This hop is read against the stored arrow"
                      >
                        reverse
                      </span>
                    ) : null}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ol>
      ) : null}

      {showFacts && traversal.facts.length ? (
        <ul className={cx('space-y-0.5', nodes.length ? 'mt-2.5' : '')}>
          {traversal.facts.map((fact, index) => (
            <li key={index} className="flex gap-1.5 text-[10.5px] leading-relaxed text-ink-600">
              <span aria-hidden className="text-ink-300">
                ▪
              </span>
              <span>{fact}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export const CONSTRAINT_TONE: Record<
  GraphTraversal['constraint_type'],
  'danger' | 'caution' | 'brand' | 'neutral' | 'graph'
> = {
  injury_anatomy: 'danger',
  contraindication: 'danger',
  equipment: 'caution',
  explicit_exclusion: 'brand',
  preference_ranking: 'neutral',
  data_gap: 'neutral',
};

export const CONSTRAINT_LABEL: Record<GraphTraversal['constraint_type'], string> = {
  injury_anatomy: 'Injury / anatomy',
  contraindication: 'Contraindication',
  equipment: 'Equipment',
  explicit_exclusion: 'Explicit exclusion',
  preference_ranking: 'Preference / ranking',
  data_gap: 'Missing catalog data',
};
