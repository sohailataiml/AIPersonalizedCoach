'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { Sidebar } from '@/components/app-shell/Sidebar';
import { GraphCanvas } from '@/components/graph-explorer/GraphCanvas';
import {
  GraphBackendBadge,
  GraphFilters,
  GraphLegend,
} from '@/components/graph-explorer/GraphLegend';
import { GraphSearch } from '@/components/graph-explorer/GraphSearch';
import { NodeInspector } from '@/components/graph-explorer/NodeInspector';
import { SafetyReasoningMode } from '@/components/graph-explorer/SafetyReasoningMode';
import { GroundingDetail } from '@/components/graph/OntologyGrounding';
import {
  Badge,
  Card,
  CardHead,
  EmptyState,
  ErrorNote,
  Spinner,
  cx,
} from '@/components/ui/primitives';
import { api } from '@/lib/api';
import type { GraphSearchHit } from '@/lib/types';

/**
 * Knowledge Graph Explorer — read-only inspection of the application's graph.
 *
 * This is **not** Neo4j Browser. There is no Cypher box, no Bolt URI, no
 * credential and no write path. Every view is served by a narrow API that owns
 * the shape of the traversal; the client only names a node and a depth.
 *
 * Three modes over one shared data model and one shared viewer:
 *
 *   Explore            — search and walk the neighborhood
 *   Safety Reasoning   — ask the real SafetyEngine why an exercise was excluded
 *   Ontology Grounding — local concept → SKOS mapping → published concept
 */

type Mode = 'explore' | 'safety' | 'ontology';

const MODES: Array<{ id: Mode; label: string }> = [
  { id: 'explore', label: 'Explore' },
  { id: 'safety', label: 'Safety reasoning' },
  { id: 'ontology', label: 'Ontology grounding' },
];

const SUGGESTIONS = ['knee', 'PFPS', 'Static Jump', 'dumbbell', 'plyometric'];

export default function GraphExplorerPage() {
  const [mode, setMode] = useState<Mode>('explore');
  const [query, setQuery] = useState('');
  const [rootId, setRootId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [depth, setDepth] = useState(1);
  const [kindFilter, setKindFilter] = useState<string[]>([]);
  const [relationshipFilter, setRelationshipFilter] = useState<string[]>([]);
  const [safetyExercise, setSafetyExercise] = useState<GraphSearchHit | null>(null);

  // Deep links: /graph?node=anatomy:knee or /graph?mode=safety&exercise=<id>
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    const requestedMode = params.get('mode');
    if (requestedMode === 'safety' || requestedMode === 'ontology') {
      setMode(requestedMode);
    }
    const node = params.get('node');
    if (node) {
      setRootId(node);
      setSelectedId(node);
    }
    const exercise = params.get('exercise');
    if (exercise) {
      setMode(requestedMode === 'ontology' ? 'ontology' : 'safety');
      setSafetyExercise({
        id: exercise,
        label: params.get('name') ?? exercise,
        kind: 'Exercise',
        canonical_id: null,
        match: 'id',
        score: 1,
        degree: 0,
      });
    }
  }, []);

  const summary = useQuery({ queryKey: ['graph', 'summary'], queryFn: api.graphSummary });
  const legend = useQuery({ queryKey: ['graph', 'legend'], queryFn: api.graphLegend });

  const search = useQuery({
    queryKey: ['graph', 'search', query, mode],
    queryFn: () =>
      api.graphSearch(query, mode === 'safety' ? ['Exercise'] : undefined, 12),
    enabled: query.trim().length > 0,
  });

  const neighborhood = useQuery({
    queryKey: ['graph', 'neighborhood', rootId, depth],
    queryFn: () => api.graphNeighborhood(rootId!, { depth }),
    enabled: Boolean(rootId) && mode !== 'safety',
  });

  const safety = useQuery({
    queryKey: ['graph', 'safety', safetyExercise?.id],
    queryFn: () => api.graphSafety(safetyExercise!.id),
    enabled: mode === 'safety' && Boolean(safetyExercise),
  });

  const subgraph = neighborhood.data ?? null;

  /** Filters apply to the loaded subgraph — no extra round trip. */
  const filtered = useMemo(() => {
    if (!subgraph) return null;
    if (!kindFilter.length && !relationshipFilter.length) return subgraph;

    const edges = subgraph.edges.filter(
      (edge) =>
        !relationshipFilter.length || relationshipFilter.includes(edge.relationship),
    );
    const keep = new Set<string>([subgraph.root_id]);
    for (const edge of edges) {
      keep.add(edge.source);
      keep.add(edge.target);
    }
    const nodes = subgraph.nodes.filter(
      (node) =>
        keep.has(node.id) &&
        (!kindFilter.length ||
          kindFilter.includes(node.kind) ||
          node.id === subgraph.root_id),
    );
    const visible = new Set(nodes.map((node) => node.id));

    return {
      ...subgraph,
      nodes,
      edges: edges.filter(
        (edge) => visible.has(edge.source) && visible.has(edge.target),
      ),
    };
  }, [subgraph, kindFilter, relationshipFilter]);

  const selectedNode =
    filtered?.nodes.find((node) => node.id === selectedId) ??
    filtered?.nodes.find((node) => node.id === filtered.root_id) ??
    null;

  const openNode = useCallback((hit: GraphSearchHit) => {
    setRootId(hit.id);
    setSelectedId(hit.id);
    setDepth(1);
  }, []);

  const expand = useCallback((nodeId: string) => {
    setRootId(nodeId);
    setSelectedId(nodeId);
  }, []);

  const reset = useCallback(() => {
    setKindFilter([]);
    setRelationshipFilter([]);
    setDepth(1);
    if (subgraph) setSelectedId(subgraph.root_id);
  }, [subgraph]);

  const groundedNodes = useMemo(
    () =>
      (filtered?.nodes ?? []).filter(
        (node) => node.ontology_grounding?.status === 'verified',
      ),
    [filtered],
  );

  return (
    <div className="flex min-h-screen">
      <Sidebar current="graph" />

      <div className="min-w-0 flex-1">
        <header className="border-b border-ink-200 bg-white px-6 py-5">
          <div className="mx-auto max-w-[1500px]">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h1 className="text-lg font-semibold tracking-tight text-navy-900">
                  Knowledge graph explorer
                </h1>
                <p className="mt-0.5 text-2xs text-ink-500">
                  Read-only inspection of the graph the application actually
                  reasons on. Not a database console — no query language, no
                  credentials, no writes.
                </p>
              </div>
              <GraphBackendBadge backend={summary.data?.graph_backend} />
            </div>

            <div role="tablist" aria-label="Explorer mode" className="mt-3 flex gap-1">
              {MODES.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  aria-selected={mode === item.id}
                  onClick={() => setMode(item.id)}
                  className={cx(
                    'rounded-lg px-3 py-1.5 text-2xs font-semibold transition-colors',
                    mode === item.id
                      ? 'bg-navy-900 text-white'
                      : 'text-ink-600 hover:bg-ink-100',
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-[1500px] space-y-4 px-6 py-5 pb-16">
          <Card>
            <div className="px-5 py-4">
              <GraphSearch
                value={query}
                onChange={setQuery}
                hits={search.data?.hits ?? []}
                isLoading={search.isFetching}
                selectedId={mode === 'safety' ? safetyExercise?.id ?? null : rootId}
                truncated={Boolean(search.data?.truncated)}
                onSelect={(hit) =>
                  mode === 'safety' ? setSafetyExercise(hit) : openNode(hit)
                }
              />
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <span className="text-[9.5px] uppercase tracking-wide text-ink-400">
                  Try
                </span>
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => setQuery(suggestion)}
                    className="rounded-full border border-ink-200 px-2 py-0.5 text-[10px] text-ink-600 hover:bg-ink-50"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          </Card>

          {mode === 'safety' ? (
            <Card>
              <CardHead title="Safety reasoning" />
              <div className="px-5 pb-4">
                <SafetyReasoningMode
                  safety={safety.data ?? null}
                  isLoading={safety.isFetching}
                  error={safety.error as Error | null}
                  exerciseName={safetyExercise?.label ?? null}
                />
              </div>
            </Card>
          ) : mode === 'ontology' ? (
            <Card>
              <CardHead
                title="Ontology grounding"
                right={
                  <Badge tone="neutral">
                    {summary.data?.ontology_mappings ?? 0} verified mappings
                  </Badge>
                }
              />
              <div className="px-5 pb-4">
                <p className="mb-3 text-2xs text-ink-500">
                  Local Future concept → SKOS mapping → published ontology
                  concept. Mappings are the verified set stored in the graph;
                  no terminology server is called while rendering this page.
                </p>
                {!rootId ? (
                  <EmptyState
                    title="Search a clinical concept"
                    body="Try “knee” or “PFPS”. Concepts grounded in a published ontology show their code, mapping relation and evidence."
                  />
                ) : groundedNodes.length ? (
                  <ul className="grid gap-2 lg:grid-cols-2">
                    {groundedNodes.map((node) => (
                      <li
                        key={node.id}
                        className="rounded-xl border border-ink-200 bg-white p-3"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-2xs font-semibold text-navy-900">
                            {node.label}
                          </span>
                          <Badge tone="neutral">{node.kind}</Badge>
                        </div>
                        <div className="font-mono text-[9.5px] text-ink-400">
                          {node.id}
                        </div>
                        <GroundingDetail grounding={node.ontology_grounding!} />
                      </li>
                    ))}
                  </ul>
                ) : (
                  <EmptyState
                    title="No published mapping in this neighborhood"
                    body="These concepts are part of the Future fitness ontology and keep their local ids by design — that is a recorded decision, not a gap."
                  />
                )}
              </div>
            </Card>
          ) : (
            <Card>
              <CardHead
                title="Explore"
                right={
                  filtered ? (
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge tone="neutral">
                        {filtered.nodes.length} nodes · {filtered.edges.length} edges
                      </Badge>
                      <button
                        type="button"
                        onClick={() => setDepth(depth === 1 ? 2 : 1)}
                        className="rounded-full border border-ink-200 px-2 py-0.5 text-[10px] text-ink-600 hover:bg-ink-50"
                      >
                        Depth {depth} · show {depth === 1 ? 2 : 1}
                      </button>
                      <button
                        type="button"
                        onClick={reset}
                        className="rounded-full border border-ink-200 px-2 py-0.5 text-[10px] text-ink-600 hover:bg-ink-50"
                      >
                        Reset
                      </button>
                    </div>
                  ) : null
                }
              />

              {neighborhood.isError ? (
                <div className="px-5 pb-4">
                  <ErrorNote
                    message={(neighborhood.error as Error).message}
                  />
                </div>
              ) : !rootId ? (
                <EmptyState
                  title="Search for a concept to begin"
                  body="The explorer never loads the whole graph. Choose a node and it loads a bounded neighborhood around it."
                />
              ) : neighborhood.isFetching && !filtered ? (
                <div className="px-5 pb-4">
                  <Spinner label="Loading neighborhood…" />
                </div>
              ) : filtered ? (
                <div className="grid gap-0 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
                  <div className="border-b border-ink-200 px-3 py-2 lg:border-b-0 lg:border-r">
                    <GraphCanvas
                      subgraph={filtered}
                      selectedId={selectedId}
                      onSelect={setSelectedId}
                      onExpand={expand}
                    />
                    {subgraph?.truncated ? (
                      <p className="px-1 text-[10px] text-caution-700">
                        Additional neighbours not displayed (
                        {subgraph.omitted_count} omitted).
                      </p>
                    ) : null}
                  </div>
                  <div className="scrollbar-slim max-h-[520px] overflow-y-auto bg-ink-50/50 p-4">
                    <NodeInspector
                      node={selectedNode}
                      subgraph={filtered}
                      onExpand={expand}
                      onOpenSafety={(nodeId) => {
                        const node = filtered.nodes.find((item) => item.id === nodeId);
                        setSafetyExercise({
                          id: nodeId,
                          label: node?.label ?? nodeId,
                          kind: 'Exercise',
                          canonical_id: null,
                          match: 'id',
                          score: 1,
                          degree: node?.degree ?? 0,
                        });
                        setMode('safety');
                      }}
                    />
                  </div>
                </div>
              ) : null}

              {filtered ? (
                <div className="border-t border-ink-200 px-5 py-2.5">
                  <GraphFilters
                    nodeKinds={Array.from(
                      new Set((subgraph?.nodes ?? []).map((node) => node.kind)),
                    ).sort()}
                    relationships={Array.from(
                      new Set((subgraph?.edges ?? []).map((edge) => edge.relationship)),
                    ).sort()}
                    activeKinds={kindFilter}
                    activeRelationships={relationshipFilter}
                    onToggleKind={(kind) =>
                      setKindFilter((current) =>
                        current.includes(kind)
                          ? current.filter((item) => item !== kind)
                          : [...current, kind],
                      )
                    }
                    onToggleRelationship={(relationship) =>
                      setRelationshipFilter((current) =>
                        current.includes(relationship)
                          ? current.filter((item) => item !== relationship)
                          : [...current, relationship],
                      )
                    }
                    onReset={reset}
                  />
                </div>
              ) : null}
            </Card>
          )}

          <GraphLegend legend={legend.data ?? null} stats={summary.data ?? null} />

          <footer className="pt-1 text-[10.5px] text-ink-400">
            React → FastAPI → GraphRepository → {summary.data?.graph_backend ?? '…'}.
            The browser never receives a Bolt URI, a credential or a query
            language, and no endpoint here can write.
          </footer>
        </main>
      </div>
    </div>
  );
}
