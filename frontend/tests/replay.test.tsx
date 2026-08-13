/**
 * Step-by-step replay tests.
 *
 * A replay is only trustworthy if it walks exactly the hops the engine
 * recorded, in the recorded order. These tests pin that: the script length and
 * sequence are derived from the fixture's own traversals, and the captions must
 * name the real relationships and node labels rather than a narrative.
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { GraphReasoningPanel } from '@/components/graph/GraphReasoningPanel';
import { TraversalReplay } from '@/components/graph/TraversalReplay';
import { buildReplaySteps } from '@/lib/replay';
import type { GenerateWorkoutResponse, GraphTraversal } from '@/lib/types';
import { workoutFixture } from './fixtures';

const reasoning = workoutFixture.graph_reasoning!;

function traversalsFor(exerciseId: string): GraphTraversal[] {
  return reasoning.traversals.filter((t) => t.exercise_id === exerciseId);
}

/** An exercise whose decision rests on real hops. */
const richExerciseId = reasoning.traversals.find((t) => t.edges.length > 0)!.exercise_id;
const richTraversals = traversalsFor(richExerciseId);

function Harness({ result = workoutFixture }: { result?: GenerateWorkoutResponse }) {
  const [selected, setSelected] = useState<string | null>(richExerciseId);
  return (
    <GraphReasoningPanel
      result={result}
      selectedExerciseId={selected}
      onSelect={setSelected}
    />
  );
}

describe('buildReplaySteps', () => {
  it('emits one start step per path plus one step per hop', () => {
    const steps = buildReplaySteps(richTraversals);

    const expectedHops = richTraversals.reduce(
      (total, traversal) => total + traversal.edges.length,
      0,
    );
    const expectedStarts = richTraversals.filter((t) => t.nodes.length > 0).length;
    const expectedFacts = richTraversals.reduce(
      (total, traversal) => total + traversal.facts.length,
      0,
    );

    // +1 for the closing decision step.
    expect(steps).toHaveLength(expectedStarts + expectedHops + expectedFacts + 1);
  });

  it('reveals one more node with each hop', () => {
    const traversal = richTraversals.find((t) => t.edges.length > 0)!;
    const steps = buildReplaySteps([traversal]).filter(
      (step) => step.kind === 'start' || step.kind === 'hop',
    );

    expect(steps.map((step) => step.visibleNodes)).toEqual(
      traversal.nodes.map((_, index) => index + 1),
    );
  });

  it('names the real relationship in each hop caption', () => {
    const traversal = richTraversals.find((t) => t.edges.length > 0)!;
    const hops = buildReplaySteps([traversal]).filter((step) => step.kind === 'hop');

    hops.forEach((hop, index) => {
      const edge = traversal.edges[index];
      expect(hop.caption).toContain(edge.relationship);
      expect(hop.caption).toContain(traversal.nodes[index + 1].label);
    });
  });

  it('says when a hop is read against the stored arrow', () => {
    const reversed = reasoning.traversals.find((t) =>
      t.edges.some((e) => e.direction === 'incoming'),
    )!;
    const steps = buildReplaySteps([reversed]);
    const backwards = steps.find((step) => step.caption.includes('backwards'));

    expect(backwards).toBeDefined();
    expect(backwards!.detail).toContain('Read against the stored arrow');
  });

  it('carries facts through verbatim', () => {
    const equipment = reasoning.traversals.find(
      (t) => t.constraint_type === 'equipment' && t.facts.length > 0,
    )!;
    const factSteps = buildReplaySteps([equipment]).filter((s) => s.kind === 'fact');

    expect(factSteps.map((s) => s.caption)).toEqual(equipment.facts);
  });

  it('always ends on the decision', () => {
    const steps = buildReplaySteps(richTraversals);
    const last = steps[steps.length - 1];

    expect(last.kind).toBe('decision');
    expect(last.caption).toMatch(/^Decision: (Excluded|Down-ranked|Allowed)$/);
    expect(last.detail).toBe(richTraversals[richTraversals.length - 1].reason);
  });

  it('returns nothing for an empty traversal list', () => {
    expect(buildReplaySteps([])).toEqual([]);
  });
});

describe('TraversalReplay player', () => {
  const props = { traversals: richTraversals, exerciseName: 'Test Exercise' };
  const total = buildReplaySteps(richTraversals).length;

  it('starts at the first step', () => {
    render(<TraversalReplay {...props} />);
    expect(screen.getByTestId('replay-position')).toHaveTextContent(
      `Step 1 of ${total}`,
    );
  });

  it('advances and rewinds one step at a time', async () => {
    const user = userEvent.setup();
    render(<TraversalReplay {...props} />);

    await user.click(screen.getByRole('button', { name: 'Next step' }));
    expect(screen.getByTestId('replay-position')).toHaveTextContent(
      `Step 2 of ${total}`,
    );

    await user.click(screen.getByRole('button', { name: 'Previous step' }));
    expect(screen.getByTestId('replay-position')).toHaveTextContent(
      `Step 1 of ${total}`,
    );
  });

  it('cannot step before the beginning or past the end', async () => {
    const user = userEvent.setup();
    render(<TraversalReplay {...props} />);

    expect(screen.getByRole('button', { name: 'Previous step' })).toBeDisabled();

    for (let i = 0; i < total - 1; i += 1) {
      await user.click(screen.getByRole('button', { name: 'Next step' }));
    }
    expect(screen.getByTestId('replay-position')).toHaveTextContent(
      `Step ${total} of ${total}`,
    );
    expect(screen.getByRole('button', { name: 'Next step' })).toBeDisabled();
  });

  it('shows the caption for the current step', async () => {
    const user = userEvent.setup();
    const steps = buildReplaySteps(richTraversals);
    render(<TraversalReplay {...props} />);

    expect(screen.getByText(steps[0].caption)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Next step' }));
    expect(screen.getByText(steps[1].caption)).toBeInTheDocument();
  });

  it('reveals the graph progressively', async () => {
    const user = userEvent.setup();
    const traversal = richTraversals.find((t) => t.edges.length > 1);
    if (!traversal) return; // fixture has no multi-hop path; nothing to assert

    render(<TraversalReplay traversals={[traversal]} exerciseName="X" />);

    // Only the first node is on screen at step 1.
    expect(screen.getByText(traversal.nodes[0].label)).toBeInTheDocument();
    expect(screen.queryByText(traversal.nodes[1].label)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Next step' }));
    expect(screen.getByText(traversal.nodes[1].label)).toBeInTheDocument();
  });

  it('restarts back to the first step', async () => {
    const user = userEvent.setup();
    render(<TraversalReplay {...props} />);

    await user.click(screen.getByRole('button', { name: 'Next step' }));
    await user.click(screen.getByRole('button', { name: 'Restart' }));

    expect(screen.getByTestId('replay-position')).toHaveTextContent(
      `Step 1 of ${total}`,
    );
  });

  it('supports keyboard stepping', async () => {
    const user = userEvent.setup();
    render(<TraversalReplay {...props} />);

    const group = screen.getByRole('group', { name: 'Traversal replay' });
    group.focus();

    await user.keyboard('{ArrowRight}');
    expect(screen.getByTestId('replay-position')).toHaveTextContent(
      `Step 2 of ${total}`,
    );

    await user.keyboard('{ArrowLeft}');
    expect(screen.getByTestId('replay-position')).toHaveTextContent(
      `Step 1 of ${total}`,
    );
  });

  it('toggles play and pause', async () => {
    const user = userEvent.setup();
    render(<TraversalReplay {...props} />);

    await user.click(screen.getByRole('button', { name: 'Play replay' }));
    expect(screen.getByRole('button', { name: 'Pause replay' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Pause replay' }));
    expect(screen.getByRole('button', { name: 'Play replay' })).toBeInTheDocument();
  });

  it('offers playback speeds', () => {
    render(<TraversalReplay {...props} />);
    for (const label of ['0.5×', '1×', '2×']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
    expect(screen.getByRole('button', { name: '1×' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('handles a decision with no recorded steps', () => {
    render(<TraversalReplay traversals={[]} exerciseName="X" />);
    expect(screen.getByText('Nothing to replay')).toBeInTheDocument();
  });
});

describe('Replay tab', () => {
  it('is reachable from the graph reasoning panel', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('tab', { name: /step-by-step replay/i }));
    expect(screen.getByRole('group', { name: 'Traversal replay' })).toBeInTheDocument();
  });

  it('replays whichever decision is selected', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('tab', { name: /step-by-step replay/i }));

    const group = screen.getByRole('group', { name: 'Traversal replay' });
    expect(
      within(group).getByRole('heading', {
        level: 4,
        name: richTraversals[0].exercise_name,
      }),
    ).toBeInTheDocument();
  });

  it('shares selection with the traversal tab', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('tab', { name: /step-by-step replay/i }));

    const other = reasoning.traversals.find(
      (t) => t.exercise_id !== richExerciseId && t.edges.length > 0,
    );
    if (!other) return;

    await user.click(
      screen.getByRole('button', {
        name: new RegExp(other.exercise_name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')),
      }),
    );

    const group = screen.getByRole('group', { name: 'Traversal replay' });
    expect(
      within(group).getByRole('heading', { level: 4, name: other.exercise_name }),
    ).toBeInTheDocument();
  });

  it('does not appear when graph_reasoning is absent', () => {
    render(<Harness result={{ ...workoutFixture, graph_reasoning: undefined }} />);
    expect(
      screen.queryByRole('tab', { name: /step-by-step replay/i }),
    ).not.toBeInTheDocument();
  });
});

describe('Replay fidelity', () => {
  it('never introduces a relationship the traversal does not contain', () => {
    for (const traversal of reasoning.traversals) {
      const steps = buildReplaySteps([traversal]);
      const supplied = new Set(traversal.edges.map((e) => e.relationship));

      for (const step of steps.filter((s) => s.kind === 'hop')) {
        expect(supplied.has(step.edge!.relationship)).toBe(true);
      }
    }
  });

  it('never shows more nodes than the traversal has', () => {
    for (const traversal of reasoning.traversals) {
      for (const step of buildReplaySteps([traversal])) {
        expect(step.visibleNodes).toBeLessThanOrEqual(traversal.nodes.length);
      }
    }
  });

  it('preserves the recorded order of paths', () => {
    const steps = buildReplaySteps(richTraversals);
    const order = steps
      .filter((step) => step.kind !== 'decision')
      .map((step) => step.traversalIndex);

    expect(order).toEqual([...order].sort((a, b) => a - b));
  });
});
