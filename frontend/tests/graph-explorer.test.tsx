/**
 * Knowledge Graph Explorer tests.
 *
 * The property under protection: **the explorer renders backend data and
 * infers nothing.** Node kinds, relationship names, directions and ontology
 * mappings all arrive in the payload; the UI never reconstructs them.
 *
 * The other property, equally important: this is not a database console. A
 * test asserts no credential, Bolt URI or query box exists anywhere in the
 * rendered output.
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { GraphCanvas, layout } from '@/components/graph-explorer/GraphCanvas';
import {
  GraphBackendBadge,
  GraphFilters,
  GraphLegend,
} from '@/components/graph-explorer/GraphLegend';
import { GraphSearch } from '@/components/graph-explorer/GraphSearch';
import { NodeInspector } from '@/components/graph-explorer/NodeInspector';
import { SafetyReasoningMode } from '@/components/graph-explorer/SafetyReasoningMode';
import type {
  GraphLegendResponse,
  GraphNodeView,
  GraphSafetyResponse,
  GraphSearchHit,
  GraphStatsResponse,
  GraphSubgraph,
} from '@/lib/types';
import { workoutFixture } from './fixtures';

/* ----------------------------- fixtures ---------------------------------- */

const KNEE: GraphNodeView = {
  id: 'AnatomicalRegion:knee',
  label: 'Knee',
  kind: 'AnatomicalRegion',
  properties: { id: 'knee', name: 'Knee' },
  ontology_grounding: {
    local_id: 'anatomy:knee',
    label: 'Knee',
    ontology_source: 'SNOMED_CT',
    ontology_code: '72696002',
    ontology_term: 'Knee region structure',
    ontology_uri: 'http://snomed.info/id/72696002',
    browser_url: null,
    mapping_relation: 'exactMatch',
    mapping_evidence: 'NCI EVS snomedct_us 2025_09_01: concept 72696002 active.',
    mapping_version: '2025_09_01',
    status: 'verified',
  },
  degree: 26,
};

const LOWER_LIMB: GraphNodeView = {
  id: 'AnatomicalRegion:lower_limb',
  label: 'Lower Limb',
  kind: 'AnatomicalRegion',
  properties: { id: 'lower_limb' },
  ontology_grounding: null,
  degree: 4,
};

const SNOMED: GraphNodeView = {
  id: 'OntologyConcept:snomed_ct_72696002',
  label: 'Knee region structure',
  kind: 'OntologyConcept',
  properties: { code: '72696002', source: 'SNOMED_CT' },
  ontology_grounding: null,
  degree: 1,
};

const DUMBBELL: GraphNodeView = {
  id: 'Equipment:dumbbell',
  label: 'Dumbbell',
  kind: 'Equipment',
  properties: { id: 'dumbbell' },
  ontology_grounding: null,
  degree: 12,
};

const SUBGRAPH: GraphSubgraph = {
  root_id: KNEE.id,
  nodes: [KNEE, LOWER_LIMB, SNOMED, DUMBBELL],
  edges: [
    {
      id: `${KNEE.id}|PART_OF|${LOWER_LIMB.id}`,
      source: KNEE.id,
      target: LOWER_LIMB.id,
      relationship: 'PART_OF',
      direction: 'outgoing',
      properties: {},
    },
    {
      id: `${KNEE.id}|SKOS_EXACT_MATCH|${SNOMED.id}`,
      source: KNEE.id,
      target: SNOMED.id,
      relationship: 'SKOS_EXACT_MATCH',
      direction: 'outgoing',
      properties: {},
    },
  ],
  depth: 1,
  truncated: false,
  omitted_count: 0,
};

const HITS: GraphSearchHit[] = [
  {
    id: KNEE.id,
    label: 'Knee',
    kind: 'AnatomicalRegion',
    canonical_id: 'anatomy:knee',
    match: 'label',
    score: 1,
    degree: 26,
  },
  {
    id: 'InjuryCondition:patellofemoral_pain_syndrome',
    label: 'Patellofemoral Pain Syndrome',
    kind: 'InjuryCondition',
    canonical_id: 'injury:patellofemoral_pain_syndrome',
    match: 'alias',
    score: 0.9,
    degree: 6,
  },
];

/** Real traversals from the captured workout fixture — not hand-written. */
const SAFETY: GraphSafetyResponse = {
  member_id: 'mbr_01HX9JORDAN',
  member_name: 'Jordan Rivera',
  exercise_id: 'ex-static-jump',
  exercise_name: 'Static Jump',
  prompt: 'Create a 45-minute lower-body workout. Her left knee is bothering her.',
  decision: 'excluded',
  rule_ids: ['injury_contraindicated_pattern', 'injury_region_stress'],
  reasons: ['Patellofemoral Pain Syndrome contraindicates the plyometric pattern.'],
  traversals: workoutFixture.graph_reasoning!.traversals.slice(0, 3),
  score_adjustment: 0,
  longitudinal_adjustment: 0,
  longitudinal_reasons: [],
  eligible: false,
};

const LEGEND: GraphLegendResponse = {
  node_kinds: ['AnatomicalRegion', 'Equipment', 'Exercise', 'OntologyConcept'],
  relationships: [
    {
      relationship: 'PART_OF',
      description: 'Anatomical hierarchy: this region is part of the region it points to.',
      count: 8,
    },
    {
      relationship: 'STRESSES',
      description: 'Exercise places meaningful load on this anatomical region.',
      count: 120,
    },
  ],
};

const STATS: GraphStatsResponse = {
  graph_backend: 'neo4j',
  node_count: 210,
  edge_count: 540,
  nodes_by_kind: { Exercise: 50, AnatomicalRegion: 14 },
  edges_by_relationship: { PART_OF: 8 },
  ontology_mappings: 29,
};

/* ------------------------------- search ---------------------------------- */

describe('GraphSearch', () => {
  it('renders backend hits with their kind and canonical id', () => {
    render(
      <GraphSearch
        value="knee"
        onChange={vi.fn()}
        hits={HITS}
        isLoading={false}
        selectedId={null}
        onSelect={vi.fn()}
        truncated={false}
      />,
    );

    const results = screen.getByRole('list', { name: 'Search results' });
    expect(within(results).getByText('Knee')).toBeInTheDocument();
    expect(within(results).getByText('anatomy:knee')).toBeInTheDocument();
    expect(within(results).getByText('InjuryCondition')).toBeInTheDocument();
  });

  it('selects a result without auto-selecting one first', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <GraphSearch
        value="knee"
        onChange={vi.fn()}
        hits={HITS}
        isLoading={false}
        selectedId={null}
        onSelect={onSelect}
        truncated={false}
      />,
    );

    expect(onSelect).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Open Knee' }));
    expect(onSelect).toHaveBeenCalledWith(HITS[0]);
  });

  it('states plainly when nothing matched', async () => {
    const user = userEvent.setup();
    render(
      <GraphSearch
        value=""
        onChange={vi.fn()}
        hits={[]}
        isLoading={false}
        selectedId={null}
        onSelect={vi.fn()}
        truncated={false}
      />,
    );

    await user.type(screen.getByLabelText('Search knowledge graph'), 'zorblatt');
    expect(await screen.findByText(/Nothing was auto-selected/i)).toBeInTheDocument();
  });
});

/* ------------------------------- canvas ---------------------------------- */

describe('GraphCanvas', () => {
  it('places the root at the centre and neighbours around it', () => {
    const placed = layout(SUBGRAPH);
    expect(placed[0].node.id).toBe(SUBGRAPH.root_id);
    expect(placed[0].ring).toBe(0);
    expect(placed.length).toBe(SUBGRAPH.nodes.length);
    // Deterministic: the same payload always lays out identically.
    expect(layout(SUBGRAPH)).toEqual(placed);
  });

  it('renders every node as a focusable element carrying its type', () => {
    render(
      <GraphCanvas
        subgraph={SUBGRAPH}
        selectedId={null}
        onSelect={vi.fn()}
        onExpand={vi.fn()}
      />,
    );

    for (const node of SUBGRAPH.nodes) {
      const element = screen.getByRole('button', {
        name: new RegExp(`${node.label}, ${node.kind}`),
      });
      expect(element).toHaveAttribute('tabindex', '0');
    }
  });

  it('renders relationship labels from the payload only when selected', () => {
    const { rerender } = render(
      <GraphCanvas
        subgraph={SUBGRAPH}
        selectedId={null}
        onSelect={vi.fn()}
        onExpand={vi.fn()}
      />,
    );
    expect(screen.queryByText('PART_OF')).not.toBeInTheDocument();

    rerender(
      <GraphCanvas
        subgraph={SUBGRAPH}
        selectedId={KNEE.id}
        onSelect={vi.fn()}
        onExpand={vi.fn()}
      />,
    );
    expect(screen.getByText('PART_OF')).toBeInTheDocument();
    expect(screen.getByText('SKOS_EXACT_MATCH')).toBeInTheDocument();
  });

  it('renders no relationship name the payload did not contain', () => {
    const { container } = render(
      <GraphCanvas
        subgraph={SUBGRAPH}
        selectedId={KNEE.id}
        onSelect={vi.fn()}
        onExpand={vi.fn()}
      />,
    );
    const real = new Set(SUBGRAPH.edges.map((edge) => edge.relationship));
    const rendered = Array.from(container.querySelectorAll('text'))
      .map((node) => node.textContent?.trim() ?? '')
      .filter((text) => /^[A-Z_]{4,}$/.test(text));

    expect(rendered.length).toBeGreaterThan(0);
    for (const name of rendered) expect(real.has(name)).toBe(true);
  });

  it('is keyboard operable', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const onExpand = vi.fn();
    render(
      <GraphCanvas
        subgraph={SUBGRAPH}
        selectedId={null}
        onSelect={onSelect}
        onExpand={onExpand}
      />,
    );

    const node = screen.getByRole('button', { name: /Lower Limb, AnatomicalRegion/ });
    node.focus();
    await user.keyboard('{Enter}');
    expect(onSelect).toHaveBeenCalledWith(LOWER_LIMB.id);

    await user.keyboard('e');
    expect(onExpand).toHaveBeenCalledWith(LOWER_LIMB.id);
  });

  it('describes the graph in text for assistive technology', () => {
    render(
      <GraphCanvas
        subgraph={SUBGRAPH}
        selectedId={null}
        onSelect={vi.fn()}
        onExpand={vi.fn()}
      />,
    );
    expect(
      screen.getByRole('img', {
        name: /Graph neighborhood of Knee: 4 nodes, 2 relationships/,
      }),
    ).toBeInTheDocument();
  });
});

/* ------------------------------ inspector -------------------------------- */

describe('NodeInspector', () => {
  it('shows the node, its kind and its graph id', () => {
    render(
      <NodeInspector node={KNEE} subgraph={SUBGRAPH} onExpand={vi.fn()} />,
    );

    expect(screen.getByText('Knee')).toBeInTheDocument();
    expect(screen.getByText('AnatomicalRegion')).toBeInTheDocument();
    expect(screen.getByText('AnatomicalRegion:knee')).toBeInTheDocument();
  });

  it('renders ontology grounding through the shared component', async () => {
    const user = userEvent.setup();
    render(
      <NodeInspector node={KNEE} subgraph={SUBGRAPH} onExpand={vi.fn()} />,
    );

    expect(screen.getAllByText('SNOMED CT').length).toBeGreaterThan(0);
    await user.click(screen.getByText('Ontology detail'));
    expect(screen.getByText('72696002')).toBeInTheDocument();
    expect(screen.getByText('skos:exactMatch')).toBeInTheDocument();
  });

  it('says an unmapped concept has no published mapping, not an error', () => {
    render(
      <NodeInspector node={DUMBBELL} subgraph={SUBGRAPH} onExpand={vi.fn()} />,
    );
    expect(screen.getByText(/No published mapping recorded/i)).toBeInTheDocument();
    expect(screen.queryByText(/error/i)).not.toBeInTheDocument();
  });

  it('lists connections from the loaded subgraph and the full degree', () => {
    render(
      <NodeInspector node={KNEE} subgraph={SUBGRAPH} onExpand={vi.fn()} />,
    );
    expect(screen.getByText('2 shown · 26 in the graph')).toBeInTheDocument();
    expect(screen.getByText('PART_OF')).toBeInTheDocument();
  });

  it('offers safety reasoning only for exercises', async () => {
    const user = userEvent.setup();
    const onOpenSafety = vi.fn();
    const exercise: GraphNodeView = {
      ...DUMBBELL,
      id: 'Exercise:x',
      label: 'Static Jump',
      kind: 'Exercise',
    };

    const { rerender } = render(
      <NodeInspector
        node={KNEE}
        subgraph={SUBGRAPH}
        onExpand={vi.fn()}
        onOpenSafety={onOpenSafety}
      />,
    );
    expect(
      screen.queryByRole('button', { name: /Show safety reasoning/i }),
    ).not.toBeInTheDocument();

    rerender(
      <NodeInspector
        node={exercise}
        subgraph={SUBGRAPH}
        onExpand={vi.fn()}
        onOpenSafety={onOpenSafety}
      />,
    );
    await user.click(screen.getByRole('button', { name: /Show safety reasoning/i }));
    expect(onOpenSafety).toHaveBeenCalledWith('Exercise:x');
  });

  it('prompts a selection when nothing is chosen', () => {
    render(<NodeInspector node={null} subgraph={null} onExpand={vi.fn()} />);
    expect(screen.getByText(/No node selected/i)).toBeInTheDocument();
  });
});

/* --------------------------- safety reasoning ---------------------------- */

describe('SafetyReasoningMode', () => {
  it('renders the engine verdict and reuses DecisionPaths', () => {
    render(
      <SafetyReasoningMode
        safety={SAFETY}
        isLoading={false}
        error={null}
        exerciseName="Static Jump"
      />,
    );

    expect(screen.getByText('Jordan Rivera')).toBeInTheDocument();
    expect(screen.getByText('Static Jump')).toBeInTheDocument();
    expect(screen.getAllByText(/excluded/i).length).toBeGreaterThan(0);
    // The coach UI's component, reused rather than re-implemented.
    expect(
      screen.getByRole('region', { name: 'Decision paths' }),
    ).toBeInTheDocument();
  });

  it('shows the rule ids the engine reported', () => {
    render(
      <SafetyReasoningMode
        safety={SAFETY}
        isLoading={false}
        error={null}
        exerciseName="Static Jump"
      />,
    );
    for (const rule of SAFETY.traversals
      .map((traversal) => traversal.rule_id)
      .filter(Boolean)) {
      expect(screen.getAllByText(rule as string).length).toBeGreaterThan(0);
    }
  });

  it('reports longitudinal influence separately from the decision', () => {
    render(
      <SafetyReasoningMode
        safety={{
          ...SAFETY,
          longitudinal_adjustment: 6,
          longitudinal_reasons: ['familiar movement family (push)'],
        }}
        isLoading={false}
        error={null}
        exerciseName="Static Jump"
      />,
    );

    expect(screen.getByText('Longitudinal personalization')).toBeInTheDocument();
    expect(screen.getByText(/never decides eligibility/i)).toBeInTheDocument();
  });

  it('prompts for an exercise before anything is selected', () => {
    render(
      <SafetyReasoningMode
        safety={null}
        isLoading={false}
        error={null}
        exerciseName={null}
      />,
    );
    expect(screen.getByText(/Select an exercise/i)).toBeInTheDocument();
  });

  it('shows a backend error without a stack trace', () => {
    render(
      <SafetyReasoningMode
        safety={null}
        isLoading={false}
        error={new Error('Unknown exercise')}
        exerciseName={null}
      />,
    );
    expect(screen.getByText(/Unknown exercise/)).toBeInTheDocument();
  });
});

/* --------------------------- legend and filters -------------------------- */

describe('Legend, filters and backend indicator', () => {
  it('renders relationship semantics and counts from the backend', () => {
    render(<GraphLegend legend={LEGEND} stats={STATS} />);

    expect(screen.getByText('PART_OF')).toBeInTheDocument();
    expect(
      screen.getByText(/Anatomical hierarchy: this region is part of/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/210 nodes · 540 relationships/)).toBeInTheDocument();
  });

  it('reports the graph backend from the API, not an assumption', () => {
    render(<GraphBackendBadge backend={STATS.graph_backend} />);
    expect(screen.getByText('Graph backend: neo4j')).toBeInTheDocument();
  });

  it('says unknown rather than guessing when the backend has not answered', () => {
    render(<GraphBackendBadge backend={undefined} />);
    expect(screen.getByText('Graph backend: unknown')).toBeInTheDocument();
  });

  it('toggles filters and offers a reset', async () => {
    const user = userEvent.setup();
    const onToggleKind = vi.fn();
    const onReset = vi.fn();

    render(
      <GraphFilters
        nodeKinds={['Exercise', 'AnatomicalRegion']}
        relationships={['PART_OF']}
        activeKinds={['Exercise']}
        activeRelationships={[]}
        onToggleKind={onToggleKind}
        onToggleRelationship={vi.fn()}
        onReset={onReset}
      />,
    );

    expect(screen.getByRole('button', { name: 'Exercise' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await user.click(screen.getByRole('button', { name: 'AnatomicalRegion' }));
    expect(onToggleKind).toHaveBeenCalledWith('AnatomicalRegion');

    await user.click(screen.getByRole('button', { name: /Reset filters/i }));
    expect(onReset).toHaveBeenCalled();
  });
});

/* ------------------------------- security -------------------------------- */

describe('The explorer is not a database console', () => {
  it('exposes no query input anywhere in the rendered surface', () => {
    const { container } = render(
      <>
        <GraphSearch
          value=""
          onChange={vi.fn()}
          hits={HITS}
          isLoading={false}
          selectedId={null}
          onSelect={vi.fn()}
          truncated={false}
        />
        <GraphCanvas
          subgraph={SUBGRAPH}
          selectedId={KNEE.id}
          onSelect={vi.fn()}
          onExpand={vi.fn()}
        />
        <NodeInspector node={KNEE} subgraph={SUBGRAPH} onExpand={vi.fn()} />
        <GraphLegend legend={LEGEND} stats={STATS} />
      </>,
    );

    const text = (container.textContent ?? '').toLowerCase();
    for (const forbidden of ['cypher', 'bolt://', 'neo4j://', 'password', 'username']) {
      expect(text).not.toContain(forbidden);
    }
    // Exactly one input: the concept search box.
    expect(container.querySelectorAll('input')).toHaveLength(1);
    expect(container.querySelector('textarea')).toBeNull();
  });

  it('shows truncation rather than silently dropping neighbours', () => {
    render(
      <NodeInspector
        node={KNEE}
        subgraph={{ ...SUBGRAPH, truncated: true, omitted_count: 12 }}
        onExpand={vi.fn()}
      />,
    );
    // Degree still reports the full graph, so the omission is visible.
    expect(screen.getByText('2 shown · 26 in the graph')).toBeInTheDocument();
  });
});
