'use client';

import { useMemo } from 'react';

import { cx } from '@/components/ui/primitives';
import type { GraphNodeView, GraphSubgraph } from '@/lib/types';

/**
 * A focused neighborhood viewer.
 *
 * Deliberately **not** a force-directed graph, and deliberately no new
 * dependency. The layout is a deterministic radial one: the selected node at
 * the centre, first-hop neighbours on an inner ring, second-hop on an outer
 * ring, each ring sorted by relationship then label.
 *
 * Three reasons that beats a physics simulation here:
 *
 * 1. **It is explanatory.** The question is "how is this concept connected?",
 *    and a stable ring answers it. A hairball that settles differently on every
 *    render answers nothing.
 * 2. **It is testable.** Positions are pure functions of the payload, so a
 *    jsdom test can assert what is drawn.
 * 3. **It is accessible.** Every node is a real focusable element with a text
 *    label and a type badge, so the graph is navigable by keyboard and
 *    readable without relying on colour.
 *
 * Nothing here infers structure: nodes, edges, relationship names and
 * directions all come from the backend payload.
 */

const WIDTH = 720;
const HEIGHT = 460;
const CENTRE = { x: WIDTH / 2, y: HEIGHT / 2 };
const RING = [140, 210];

/** Restrained differentiation: a colour *and* a glyph, never colour alone. */
export const NODE_STYLE: Record<string, { className: string; glyph: string }> = {
  Member: { className: 'fill-navy-50 stroke-navy-400', glyph: '👤' },
  Exercise: { className: 'fill-brand-50 stroke-brand-400', glyph: '🏋' },
  Muscle: { className: 'fill-graph-50 stroke-graph-300', glyph: '💪' },
  AnatomicalRegion: { className: 'fill-graph-50 stroke-graph-400', glyph: '🦴' },
  MovementPattern: { className: 'fill-ink-50 stroke-ink-300', glyph: '➰' },
  MovementFamily: { className: 'fill-ink-100 stroke-ink-300', glyph: '🗂' },
  Equipment: { className: 'fill-caution-50 stroke-caution-400', glyph: '🧰' },
  InjuryCondition: { className: 'fill-danger-50 stroke-danger-400', glyph: '⚕' },
  Injury: { className: 'fill-danger-50 stroke-danger-300', glyph: '⚕' },
  OntologyConcept: { className: 'fill-safe-50 stroke-safe-400', glyph: '🔖' },
  Goal: { className: 'fill-navy-50 stroke-navy-300', glyph: '◎' },
  Preference: { className: 'fill-ink-50 stroke-ink-300', glyph: '☆' },
};

const FALLBACK = { className: 'fill-ink-50 stroke-ink-300', glyph: '•' };

interface Placed {
  node: GraphNodeView;
  x: number;
  y: number;
  ring: number;
}

export function layout(subgraph: GraphSubgraph): Placed[] {
  const root = subgraph.nodes.find((node) => node.id === subgraph.root_id);
  if (!root) return [];

  const relationshipOf = new Map<string, string>();
  for (const edge of subgraph.edges) {
    const other = edge.source === subgraph.root_id ? edge.target : edge.source;
    if (edge.source === subgraph.root_id || edge.target === subgraph.root_id) {
      relationshipOf.set(other, edge.relationship);
    }
  }

  const others = subgraph.nodes.filter((node) => node.id !== root.id);
  const inner = others.filter((node) => relationshipOf.has(node.id));
  const outer = others.filter((node) => !relationshipOf.has(node.id));

  const byRelThenLabel = (a: GraphNodeView, b: GraphNodeView) =>
    (relationshipOf.get(a.id) ?? '').localeCompare(relationshipOf.get(b.id) ?? '') ||
    a.label.localeCompare(b.label);

  const placed: Placed[] = [{ node: root, x: CENTRE.x, y: CENTRE.y, ring: 0 }];

  [inner.sort(byRelThenLabel), outer.sort(byRelThenLabel)].forEach((ring, index) => {
    const radius = RING[index] ?? RING[RING.length - 1];
    ring.forEach((node, position) => {
      // Offset each ring so nodes do not stack radially behind one another.
      const angle =
        (position / Math.max(1, ring.length)) * Math.PI * 2 - Math.PI / 2 + index * 0.25;
      placed.push({
        node,
        x: CENTRE.x + radius * Math.cos(angle),
        y: CENTRE.y + radius * Math.sin(angle) * 0.62,
        ring: index + 1,
      });
    });
  });

  return placed;
}

export function GraphCanvas({
  subgraph,
  selectedId,
  onSelect,
  onExpand,
}: {
  subgraph: GraphSubgraph;
  selectedId: string | null;
  onSelect: (nodeId: string) => void;
  onExpand: (nodeId: string) => void;
}) {
  const placed = useMemo(() => layout(subgraph), [subgraph]);
  const positions = useMemo(
    () => new Map(placed.map((entry) => [entry.node.id, entry])),
    [placed],
  );

  if (!placed.length) return null;

  return (
    <div className="relative">
      <svg
        role="img"
        aria-label={`Graph neighborhood of ${
          placed[0]?.node.label ?? subgraph.root_id
        }: ${subgraph.nodes.length} nodes, ${subgraph.edges.length} relationships`}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-[460px] w-full"
      >
        <defs>
          <marker
            id="graph-arrow"
            viewBox="0 0 8 8"
            refX="7"
            refY="4"
            markerWidth="5"
            markerHeight="5"
            orient="auto-start-reverse"
          >
            <path d="M0 0 L8 4 L0 8 z" className="fill-ink-300" />
          </marker>
        </defs>

        {subgraph.edges.map((edge) => {
          const from = positions.get(edge.source);
          const to = positions.get(edge.target);
          if (!from || !to) return null;
          const midX = (from.x + to.x) / 2;
          const midY = (from.y + to.y) / 2;
          const touchesSelection =
            selectedId === edge.source || selectedId === edge.target;

          return (
            <g key={edge.id}>
              <line
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                markerEnd="url(#graph-arrow)"
                className={cx(
                  'stroke-[1.2]',
                  touchesSelection ? 'stroke-graph-500' : 'stroke-ink-200',
                )}
              />
              {touchesSelection ? (
                <text
                  x={midX}
                  y={midY - 3}
                  textAnchor="middle"
                  className="fill-graph-700 font-mono text-[8px]"
                >
                  {edge.relationship}
                </text>
              ) : null}
            </g>
          );
        })}

        {placed.map(({ node, x, y }) => {
          const style = NODE_STYLE[node.kind] ?? FALLBACK;
          const isSelected = node.id === selectedId;
          const isRoot = node.id === subgraph.root_id;
          const width = Math.min(150, 34 + node.label.length * 5.4);

          return (
            <g
              key={node.id}
              role="button"
              tabIndex={0}
              aria-label={`${node.label}, ${node.kind}, ${node.degree} connections`}
              aria-pressed={isSelected}
              onClick={() => onSelect(node.id)}
              onDoubleClick={() => onExpand(node.id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onSelect(node.id);
                }
                if (event.key === 'e' || event.key === 'E') onExpand(node.id);
              }}
              className="cursor-pointer outline-none focus-visible:opacity-80"
            >
              <rect
                x={x - width / 2}
                y={y - 15}
                width={width}
                height={30}
                rx={8}
                className={cx(
                  style.className,
                  'stroke-[1.4]',
                  isSelected && 'stroke-[2.4] stroke-brand-600',
                  isRoot && !isSelected && 'stroke-[2]',
                )}
              />
              <text
                x={x}
                y={y - 2}
                textAnchor="middle"
                className="fill-navy-900 text-[9px] font-semibold"
              >
                <tspan aria-hidden>{style.glyph} </tspan>
                {node.label.length > 22 ? `${node.label.slice(0, 21)}…` : node.label}
              </text>
              <text
                x={x}
                y={y + 8}
                textAnchor="middle"
                className="fill-ink-500 text-[7px] uppercase tracking-wide"
              >
                {node.kind}
              </text>
            </g>
          );
        })}
      </svg>

      <p className="px-1 text-[10px] text-ink-400">
        Click a node to inspect · double-click (or press E) to expand its
        neighborhood · relationship labels appear on the selected node&apos;s edges.
      </p>
    </div>
  );
}
