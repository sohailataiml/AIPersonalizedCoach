'use client';

import { GroundingDetail } from '@/components/graph/OntologyGrounding';
import { Badge, Button, EmptyState, cx } from '@/components/ui/primitives';
import type { GraphNodeView, GraphSubgraph } from '@/lib/types';

/**
 * Right-hand inspector for the selected node.
 *
 * Renders only fields the API actually returned. A node without ontology
 * grounding says so plainly rather than showing an empty mapping — a
 * deliberately unmapped concept is a recorded decision, not a gap.
 *
 * Ontology grounding reuses the Phase 1 `GroundingDetail` component, so the
 * explorer and the coach dashboard show a mapping identically.
 */

const PROPERTY_LABEL: Record<string, string> = {
  id: 'Local ID',
  name: 'Name',
  priority_tier: 'Priority tier',
  is_unilateral: 'Unilateral',
  side: 'Side',
  loaded_body_side: 'Loads side',
  supports_weight: 'Supports load',
  estimated_rep_duration: 'Est. rep duration',
  has_anatomy_data: 'Has joint data',
  status: 'Status',
  severity: 'Severity',
  body_side: 'Body side',
  contraindication_note: 'Clinical note',
  note: 'Note',
  source: 'Ontology source',
  code: 'Code',
  uri: 'URI',
  version: 'Version',
  tier: 'Tier',
  priority: 'Priority',
  unmapped: 'Unmapped catalog joint',
};

/** Ontology fields already shown by the grounding block. */
const REDUNDANT = new Set([
  'ontology_source',
  'ontology_code',
  'ontology_term',
  'ontology_status',
  'mapping_predicate',
  'mapping_version',
]);

export function NodeInspector({
  node,
  subgraph,
  onExpand,
  onOpenSafety,
}: {
  node: GraphNodeView | null;
  subgraph: GraphSubgraph | null;
  onExpand: (nodeId: string) => void;
  onOpenSafety?: (nodeId: string) => void;
}) {
  if (!node) {
    return (
      <EmptyState
        title="No node selected"
        body="Search for a concept, or click a node in the graph to inspect what it holds."
      />
    );
  }

  const connections =
    subgraph?.edges.filter(
      (edge) => edge.source === node.id || edge.target === node.id,
    ) ?? [];

  const properties = Object.entries(node.properties).filter(
    ([key]) => !REDUNDANT.has(key) && key !== 'name',
  );

  return (
    <section aria-label="Node inspector" className="space-y-3">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold tracking-tight text-navy-900">
            {node.label}
          </h3>
          <Badge tone="neutral">{node.kind}</Badge>
        </div>
        <div className="mt-0.5 font-mono text-[9.5px] text-ink-400">{node.id}</div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        <Button size="sm" variant="secondary" onClick={() => onExpand(node.id)}>
          Expand neighborhood
        </Button>
        {node.kind === 'Exercise' && onOpenSafety ? (
          <Button size="sm" variant="secondary" onClick={() => onOpenSafety(node.id)}>
            Show safety reasoning
          </Button>
        ) : null}
      </div>

      <div>
        <div className="label-caps mb-1">Ontology grounding</div>
        {node.ontology_grounding && node.ontology_grounding.status === 'verified' ? (
          <GroundingDetail grounding={node.ontology_grounding} />
        ) : (
          <p className="text-[10.5px] leading-relaxed text-ink-500">
            No published mapping recorded. This concept is part of the Future
            fitness ontology and keeps its local id by design — see the
            <span className="font-mono"> unmapped </span>
            register for the reason.
          </p>
        )}
      </div>

      {properties.length ? (
        <div>
          <div className="label-caps mb-1">Properties</div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
            {properties.map(([key, value]) => (
              <div key={key} className="contents">
                <dt className="text-[10px] text-ink-400">
                  {PROPERTY_LABEL[key] ?? key}
                </dt>
                <dd
                  className={cx(
                    'min-w-0 break-words text-[10px] text-ink-700',
                    key === 'id' && 'font-mono',
                  )}
                >
                  {String(value)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}

      <div>
        <div className="mb-1 flex items-baseline justify-between gap-2">
          <span className="label-caps">Connections</span>
          <span className="text-[10px] text-ink-500">
            {connections.length} shown · {node.degree} in the graph
          </span>
        </div>
        {connections.length ? (
          <ul className="space-y-0.5">
            {connections.map((edge) => {
              const outgoing = edge.source === node.id;
              const otherId = outgoing ? edge.target : edge.source;
              const other = subgraph?.nodes.find((item) => item.id === otherId);
              return (
                <li
                  key={edge.id}
                  className="flex items-center gap-1.5 text-[10px] text-ink-600"
                >
                  <span aria-hidden className="text-ink-300">
                    {outgoing ? '→' : '←'}
                  </span>
                  <span className="font-mono text-[9.5px] text-graph-700">
                    {edge.relationship}
                  </span>
                  <span className="min-w-0 truncate text-navy-900">
                    {other?.label ?? otherId}
                  </span>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-[10px] text-ink-400">
            No relationships in the loaded neighborhood.
          </p>
        )}
      </div>
    </section>
  );
}
