/**
 * Graph reasoning UI tests.
 *
 * The point of this panel is that a reviewer can trust what it draws, so these
 * tests focus on fidelity rather than layout: every node and edge shown must
 * come from `graph_reasoning`, counts must be the backend's, and a response
 * without the field must degrade to the existing provenance UI rather than
 * rendering an empty or invented graph.
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { GraphReasoningPanel } from '@/components/graph/GraphReasoningPanel';
import { LlmBoundary } from '@/components/graph/LlmBoundary';
import { TraversalPath } from '@/components/graph/TraversalPath';
import { SafetyInspector } from '@/components/provenance/SafetyInspector';
import { WorkoutGeneratorCard } from '@/components/workout/WorkoutGeneratorCard';
import type { GenerateWorkoutResponse, GraphTraversal } from '@/lib/types';
import { workoutFixture } from './fixtures';

const reasoning = workoutFixture.graph_reasoning!;

/** Mirrors the page: one selection shared by both panels. */
function Harness({
  result = workoutFixture,
  initial = null,
}: {
  result?: GenerateWorkoutResponse;
  initial?: string | null;
}) {
  const [selected, setSelected] = useState<string | null>(initial);
  return (
    <GraphReasoningPanel
      result={result}
      selectedExerciseId={selected}
      onSelect={setSelected}
    />
  );
}

function traversalsFor(exerciseId: string): GraphTraversal[] {
  return reasoning.traversals.filter((t) => t.exercise_id === exerciseId);
}

/**
 * Decision buttons carry the exercise name plus a constraint badge, so their
 * accessible name is the concatenation. Match on the name as a substring.
 */
function nameMatcher(text: string): RegExp {
  return new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
}

describe('GraphReasoningPanel', () => {
  it('renders when the response carries graph_reasoning', () => {
    render(<Harness />);
    expect(screen.getByText('Graph reasoning')).toBeInTheDocument();
    expect(
      screen.getByText(`graph.${reasoning.graph_backend}`),
    ).toBeInTheDocument();
  });

  it('falls back to provenance messaging when the field is absent', () => {
    const legacy = { ...workoutFixture, graph_reasoning: undefined };
    render(<Harness result={legacy} />);

    expect(screen.getByText('Graph reasoning not available')).toBeInTheDocument();
    expect(screen.getByText(/Safety & Provenance inspector/i)).toBeInTheDocument();
  });

  it('renders nothing before a workout exists', () => {
    const { container } = render(
      <GraphReasoningPanel result={null} selectedExerciseId={null} onSelect={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('reports the backend traversal count', () => {
    render(<Harness />);
    expect(
      screen.getByText(
        `${reasoning.summary.traversal_count} traversals · ${reasoning.summary.exercises_with_evidence} exercises`,
      ),
    ).toBeInTheDocument();
  });
});

describe('Prompt concepts tab', () => {
  it('shows each phrase with its resolver method and confidence', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole('tab', { name: /prompt concepts/i }));

    const knee = reasoning.prompt_concepts.find((c) => c.source_text === 'left knee');
    expect(knee).toBeDefined();

    expect(screen.getByText('“left knee”')).toBeInTheDocument();
    expect(screen.getByText(knee!.label!)).toBeInTheDocument();
    expect(screen.getAllByText(knee!.method).length).toBeGreaterThan(0);
    expect(screen.getAllByText(knee!.confidence.toFixed(2)).length).toBeGreaterThan(0);
  });

  it('resolves equipment phrases to canonical concepts', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole('tab', { name: /prompt concepts/i }));

    expect(screen.getByText('equipment.dumbbell')).toBeInTheDocument();
    expect(screen.getByText('equipment.kettlebell')).toBeInTheDocument();
  });

  it('marks unresolved phrases as not applied', async () => {
    const user = userEvent.setup();
    const withUnresolved: GenerateWorkoutResponse = {
      ...workoutFixture,
      graph_reasoning: {
        ...reasoning,
        prompt_concepts: [
          ...reasoning.prompt_concepts,
          {
            source_text: 'weird knee-ish thing',
            canonical_id: null,
            label: null,
            concept_type: null,
            method: 'unresolved',
            confidence: 0.45,
            resolved: false,
          },
        ],
      },
    };

    render(<Harness result={withUnresolved} />);
    await user.click(screen.getByRole('tab', { name: /prompt concepts/i }));

    expect(screen.getByText('“weird knee-ish thing”')).toBeInTheDocument();
    expect(screen.getByText(/no safety rule applied/i)).toBeInTheDocument();
  });
});

describe('Traversal tab', () => {
  it('renders nodes and edges taken from the backend', () => {
    const traversal = reasoning.traversals.find((t) => t.edges.length > 0)!;
    render(<TraversalPath traversal={traversal} />);

    for (const node of traversal.nodes) {
      expect(screen.getAllByText(node.label).length).toBeGreaterThan(0);
      expect(screen.getAllByText(node.type).length).toBeGreaterThan(0);
    }
    for (const edge of traversal.edges) {
      expect(screen.getAllByText(edge.relationship).length).toBeGreaterThan(0);
    }
  });

  it('never renders a relationship the backend did not supply', () => {
    const supplied = new Set(
      reasoning.traversals.flatMap((t) => t.edges.map((e) => e.relationship)),
    );
    // Regression guard: these were previously invented for display only.
    expect(supplied.has('DOES_NOT_HAVE')).toBe(false);
    expect(supplied.has('LOADS_SIDE')).toBe(false);
  });

  it('marks a hop that is read against the stored arrow', () => {
    const reversed = reasoning.traversals.find((t) =>
      t.edges.some((e) => e.direction === 'incoming'),
    );
    expect(reversed).toBeDefined();

    render(<TraversalPath traversal={reversed!} />);
    expect(screen.getByText('reverse')).toBeInTheDocument();
  });

  it('states equipment absence as a fact rather than an edge', () => {
    const equipment = reasoning.traversals.find(
      (t) => t.constraint_type === 'equipment',
    )!;
    render(<TraversalPath traversal={equipment} />);

    expect(
      screen.getByText(/Available to member/i, { exact: false }),
    ).toBeInTheDocument();
    expect(equipment.edges.map((e) => e.relationship)).toEqual(['REQUIRES']);
  });

  it('groups decisions by excluded / down-ranked / allowed', () => {
    render(<Harness />);
    const decisions = new Set(reasoning.traversals.map((t) => t.decision));
    if (decisions.has('excluded')) {
      expect(screen.getAllByText('Excluded').length).toBeGreaterThan(0);
    }
    if (decisions.has('downranked')) {
      expect(screen.getAllByText('Down-ranked').length).toBeGreaterThan(0);
    }
  });

  /** The central interaction. */
  it('changes the displayed traversal when a different decision is clicked', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const withEdges = reasoning.traversals.filter((t) => t.edges.length > 0);
    const first = withEdges[0];
    const other = withEdges.find((t) => t.exercise_id !== first.exercise_id)!;
    expect(other).toBeDefined();

    await user.click(
      screen.getByRole('button', { name: nameMatcher(other.exercise_name) }),
    );

    const detail = screen.getByRole('region', { name: 'Graph traversal detail' });
    expect(
      within(detail).getByRole('heading', { level: 3, name: other.exercise_name }),
    ).toBeInTheDocument();

    // And the evidence shown belongs to that exercise.
    const expected = traversalsFor(other.exercise_id);
    expect(within(detail).getByText(expected[0].reason)).toBeInTheDocument();
  });

  it('attributes evidence to the graph, not the model', async () => {
    render(<Harness />);
    expect(
      screen.getByText(/the LLM did not generate them/i),
    ).toBeInTheDocument();
  });
});

describe('Decision summary tab', () => {
  it('uses the backend counts verbatim', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole('tab', { name: /decision summary/i }));

    const { summary } = reasoning;
    expect(screen.getAllByText(String(summary.catalog_count)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(String(summary.excluded_count)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(String(summary.eligible_count)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(String(summary.in_plan_count)).length).toBeGreaterThan(0);
  });

  it('states that the buckets overlap rather than implying a partition', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole('tab', { name: /decision summary/i }));

    expect(screen.getByText(reasoning.summary.note)).toBeInTheDocument();
  });

  it('lists the rule categories that fired with real counts', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole('tab', { name: /decision summary/i }));

    for (const row of reasoning.summary.counts_by_constraint) {
      expect(screen.getByText(row.label)).toBeInTheDocument();
      expect(
        screen.getAllByText(`${row.exercises_affected} exercises`).length,
      ).toBeGreaterThan(0);
    }
  });
});

describe('LLM boundary', () => {
  it('identifies the deterministic and generative zones', () => {
    render(<LlmBoundary summary={reasoning.summary} />);

    expect(screen.getAllByText('Deterministic zone').length).toBeGreaterThan(0);
    expect(screen.getByText('Generative zone')).toBeInTheDocument();
    expect(screen.getByText('Final safety gate')).toBeInTheDocument();
  });

  it('states that only approved candidates cross the boundary', () => {
    render(<LlmBoundary summary={reasoning.summary} />);

    expect(
      screen.getByText(/Only graph-approved candidates cross this boundary/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(`${reasoning.summary.eligible_count} approved candidates`),
    ).toBeInTheDocument();
  });

  it('shows the final gate re-checks every id', () => {
    render(<LlmBoundary summary={reasoning.summary} />);
    expect(screen.getByText('Every id re-checked')).toBeInTheDocument();
    expect(screen.getByText(/Invented ids rejected/i)).toBeInTheDocument();
  });
});

describe('Safety inspector integration', () => {
  it('renders typed backend traversals in the provenance panel', () => {
    const target = reasoning.traversals.find((t) => t.edges.length > 0)!;
    render(
      <SafetyInspector
        result={workoutFixture}
        selectedExerciseId={target.exercise_id}
        onSelect={vi.fn()}
      />,
    );

    const panel = screen.getByRole('region', { name: 'Provenance detail' });
    expect(within(panel).getByText('Graph path')).toBeInTheDocument();
    // Node type labels only exist on backend-typed traversals.
    expect(within(panel).getAllByText(target.nodes[0].type).length).toBeGreaterThan(0);
  });

  it('still works when graph_reasoning is missing', () => {
    const legacy = { ...workoutFixture, graph_reasoning: undefined };
    const withEvidence = legacy.filtered_exercises.find((i) => i.evidence.length > 0)!;

    render(
      <SafetyInspector
        result={legacy}
        selectedExerciseId={withEvidence.exercise_id}
        onSelect={vi.fn()}
      />,
    );

    const panel = screen.getByRole('region', { name: 'Provenance detail' });
    expect(within(panel).getByText('Graph path')).toBeInTheDocument();
  });
});

describe('Workout generator entry point', () => {
  it('offers a link into the graph reasoning panel', () => {
    render(
      <WorkoutGeneratorCard
        prompt="x"
        duration={45}
        onPromptChange={vi.fn()}
        onDurationChange={vi.fn()}
        onGenerate={vi.fn()}
        isGenerating={false}
        result={workoutFixture}
      />,
    );
    expect(
      screen.getByRole('button', { name: /view graph reasoning/i }),
    ).toBeInTheDocument();
  });
});
