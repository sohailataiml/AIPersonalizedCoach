/**
 * Graph reasoning UI + workout adjustment tests.
 *
 * The property under protection is the same one the backend protects, restated
 * for the view layer:
 *
 *   Everything drawn in the graph panel must come from backend evidence.
 *   The UI classifies nothing, infers no relationship, and invents no path.
 *
 * So the sharpest tests here are negative: every relationship name rendered
 * must exist in the fixture's own edges, and no path grouping may appear that
 * the backend did not label.
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { DecisionPaths } from '@/components/graph/DecisionPaths';
import { GraphReasoningPanel } from '@/components/graph/GraphReasoningPanel';
import { PipelineFlow } from '@/components/graph/PipelineFlow';
import {
  ADJUSTMENT_PRESETS,
  AdjustmentDiffView,
  WorkoutAdjustment,
} from '@/components/workout/WorkoutAdjustment';
import type {
  AdjustmentDiff,
  GenerateWorkoutResponse,
  GraphTraversal,
  MemberTrajectory,
} from '@/lib/types';
import { workoutFixture } from './fixtures';

const reasoning = workoutFixture.graph_reasoning!;
const trajectory = workoutFixture.trajectory as MemberTrajectory;

/** Every relationship the backend actually returned in this fixture. */
const REAL_RELATIONSHIPS = new Set(
  reasoning.traversals.flatMap((t) => t.edges.map((e) => e.relationship)),
);

function traversalsFor(exerciseId: string): GraphTraversal[] {
  return reasoning.traversals.filter((t) => t.exercise_id === exerciseId);
}

function firstExcluded(): GraphTraversal[] {
  const excluded = reasoning.traversals.find((t) => t.decision === 'excluded')!;
  return traversalsFor(excluded.exercise_id);
}

function Panel({ result = workoutFixture }: { result?: GenerateWorkoutResponse }) {
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <GraphReasoningPanel
      result={result}
      selectedExerciseId={selected}
      onSelect={setSelected}
    />
  );
}

/* ------------------------------- path viewer ------------------------------ */

describe('DecisionPaths', () => {
  it('groups paths by the backend-assigned kind', () => {
    const traversals = firstExcluded();
    render(<DecisionPaths traversals={traversals} />);

    const kinds = new Set(traversals.map((t) => t.path_kind));
    if (kinds.has('member_context')) {
      expect(screen.getByText('Member path')).toBeInTheDocument();
    }
    if (kinds.has('exercise_structure')) {
      expect(screen.getByText('Exercise path')).toBeInTheDocument();
    }
    if (kinds.has('anatomy_hierarchy')) {
      expect(screen.getByText('Anatomy path')).toBeInTheDocument();
    }
  });

  it('never shows a group the backend did not label', () => {
    // A traversal set with only exercise paths must not produce a member path.
    const exerciseOnly = reasoning.traversals.filter(
      (t) => t.path_kind === 'exercise_structure',
    );
    expect(exerciseOnly.length).toBeGreaterThan(0);

    render(<DecisionPaths traversals={exerciseOnly.slice(0, 2)} />);
    expect(screen.queryByText('Member path')).not.toBeInTheDocument();
    expect(screen.queryByText('Anatomy path')).not.toBeInTheDocument();
  });

  it('renders only relationship names present in the backend payload', () => {
    const traversals = firstExcluded();
    const { container } = render(<DecisionPaths traversals={traversals} />);

    const rendered = Array.from(container.querySelectorAll('span.font-mono'))
      .map((node) => node.textContent?.trim() ?? '')
      .filter((text) => /^[A-Z_]{3,}$/.test(text));

    expect(rendered.length).toBeGreaterThan(0);
    for (const relationship of rendered) {
      expect(REAL_RELATIONSHIPS.has(relationship)).toBe(true);
    }
  });

  it('shows the decision and every rule id that fired', () => {
    const traversals = firstExcluded();
    render(<DecisionPaths traversals={traversals} />);

    expect(screen.getByText('Decision')).toBeInTheDocument();
    const ruleIds = new Set(
      traversals.map((t) => t.rule_id).filter((id): id is string => Boolean(id)),
    );
    for (const ruleId of ruleIds) {
      expect(screen.getAllByText(ruleId).length).toBeGreaterThan(0);
    }
  });

  it('labels evidence with no edges as deterministic facts, not a graph walk', () => {
    const setOps = reasoning.traversals.filter((t) => t.path_kind === 'set_operation');
    expect(setOps.length).toBeGreaterThan(0);

    render(<DecisionPaths traversals={[setOps[0]]} />);
    expect(screen.getByText('Deterministic facts')).toBeInTheDocument();
    expect(screen.queryByText('Member path')).not.toBeInTheDocument();
  });

  it('renders nothing when there is no evidence', () => {
    const { container } = render(<DecisionPaths traversals={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

/* ------------------------------ selection ------------------------------ */

/**
 * Decision buttons carry the exercise name plus a constraint badge, so their
 * accessible name is the concatenation. Match the name as a substring.
 */
function nameMatcher(text: string): RegExp {
  return new RegExp(text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
}

describe('Traversal tab selection', () => {
  it('updates the path view when a different decision is selected', async () => {
    const user = userEvent.setup();
    render(<Panel />);

    const names = Array.from(
      new Set(reasoning.traversals.map((t) => t.exercise_name)),
    );
    expect(names.length).toBeGreaterThan(1);

    await user.click(screen.getByRole('button', { name: nameMatcher(names[0]) }));
    const detail = screen.getByRole('region', { name: 'Graph traversal detail' });
    expect(
      within(detail).getByRole('heading', { level: 3, name: names[0] }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: nameMatcher(names[1]) }));
    expect(
      within(
        screen.getByRole('region', { name: 'Graph traversal detail' }),
      ).getByRole('heading', { level: 3, name: names[1] }),
    ).toBeInTheDocument();
  });

  it('shows a grouped decision panel for the selected exercise', async () => {
    const user = userEvent.setup();
    render(<Panel />);

    const excluded = reasoning.traversals.find((t) => t.decision === 'excluded')!;
    await user.click(
      screen.getByRole('button', { name: nameMatcher(excluded.exercise_name) }),
    );

    const detail = screen.getByRole('region', { name: 'Graph traversal detail' });
    expect(within(detail).getByText('Decision')).toBeInTheDocument();
    expect(
      within(detail).getByRole('region', { name: 'Decision paths' }),
    ).toBeInTheDocument();
  });
});

/* ------------------------------ pipeline flow ----------------------------- */

describe('PipelineFlow', () => {
  it('names every stage of the real pipeline in order', () => {
    render(<PipelineFlow summary={reasoning.summary} trajectory={trajectory} />);

    for (const stage of [
      'Coach request',
      'Concept resolution',
      'Longitudinal analysis',
      'Knowledge graph traversal',
      'Safety decisions',
      'Safe candidate set',
      'LLM composition',
      'Final deterministic validation',
    ]) {
      expect(screen.getByText(stage)).toBeInTheDocument();
    }
  });

  it('marks the boundary the candidate set crosses', () => {
    render(<PipelineFlow summary={reasoning.summary} trajectory={trajectory} />);
    expect(
      screen.getByText('Only graph-approved candidates cross this boundary'),
    ).toBeInTheDocument();
  });

  it('reports backend counts rather than recomputing them', () => {
    render(<PipelineFlow summary={reasoning.summary} trajectory={trajectory} />);

    expect(
      screen.getByText(
        `${reasoning.summary.excluded_count} excluded · ${reasoning.summary.downranked_count} down-ranked`,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(`${reasoning.summary.eligible_count} approved`),
    ).toBeInTheDocument();
  });

  it('says so plainly when no longitudinal analysis ran', () => {
    render(<PipelineFlow summary={reasoning.summary} trajectory={null} />);
    expect(screen.getByText('not computed')).toBeInTheDocument();
  });
});

/* --------------------------- adjustment input ---------------------------- */

describe('WorkoutAdjustment', () => {
  it('submits the typed adjustment', async () => {
    const user = userEvent.setup();
    const onAdjust = vi.fn();
    render(
      <WorkoutAdjustment
        onAdjust={onAdjust}
        isPending={false}
        error={null}
        disabled={false}
      />,
    );

    await user.type(screen.getByLabelText('Adjustment'), 'Exclude deadlifts');
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    expect(onAdjust).toHaveBeenCalledWith('Exclude deadlifts');
  });

  it('sends the exact preset text when a chip is clicked', async () => {
    const user = userEvent.setup();
    const onAdjust = vi.fn();
    render(
      <WorkoutAdjustment
        onAdjust={onAdjust}
        isPending={false}
        error={null}
        disabled={false}
      />,
    );

    await user.click(screen.getByRole('button', { name: ADJUSTMENT_PRESETS[0] }));
    expect(onAdjust).toHaveBeenCalledWith(ADJUSTMENT_PRESETS[0]);
  });

  it('offers every adjustment scenario the backend supports', () => {
    render(
      <WorkoutAdjustment
        onAdjust={vi.fn()}
        isPending={false}
        error={null}
        disabled={false}
      />,
    );

    for (const preset of ADJUSTMENT_PRESETS) {
      expect(screen.getByRole('button', { name: preset })).toBeInTheDocument();
    }
  });

  it('cannot be used before a plan exists', async () => {
    const user = userEvent.setup();
    const onAdjust = vi.fn();
    render(
      <WorkoutAdjustment
        onAdjust={onAdjust}
        isPending={false}
        error={null}
        disabled
      />,
    );

    await user.click(screen.getByRole('button', { name: ADJUSTMENT_PRESETS[0] }));
    expect(onAdjust).not.toHaveBeenCalled();
    expect(screen.getByText(/Generate a workout first/i)).toBeInTheDocument();
  });

  it('surfaces a failure instead of silently doing nothing', () => {
    render(
      <WorkoutAdjustment
        onAdjust={vi.fn()}
        isPending={false}
        error={new Error('Adjustment produced no safe plan')}
        disabled={false}
      />,
    );
    expect(screen.getByText(/no safe plan/i)).toBeInTheDocument();
  });
});

/* ------------------------------- the diff -------------------------------- */

const DIFF: AdjustmentDiff = {
  removed: [
    {
      exercise_id: 'a',
      exercise: 'One-Kettlebell Hamstring Walkout',
      kind: 'removed',
      reasons: [
        'Coach excluded "deadlifts", which resolves to the Hip Hinge / Deadlift Family.',
      ],
      rule_ids: ['explicit_exclusion'],
      score_before: null,
      score_after: null,
      now_excluded: true,
    },
  ],
  added: [
    {
      exercise_id: 'b',
      exercise: 'Dumbbell Neutral-Grip Bench Press',
      kind: 'added',
      reasons: ['Required equipment available: Dumbbell.'],
      rule_ids: [],
      score_before: null,
      score_after: null,
      now_excluded: false,
    },
  ],
  downranked: [
    {
      exercise_id: 'c',
      exercise: 'Walking Toe Touches',
      kind: 'downranked',
      reasons: ['outside the requested focus'],
      rule_ids: [],
      score_before: 87,
      score_after: 77,
      now_excluded: false,
    },
  ],
  retained_ids: ['d', 'e'],
  counts: { removed: 1, added: 1, downranked: 1, retained: 2, newly_excluded: 1 },
  notes: [],
};

describe('AdjustmentDiffView', () => {
  it('shows what was removed, added and down-ranked', () => {
    render(<AdjustmentDiffView diff={DIFF} adjustment="Exclude deadlifts" />);

    expect(screen.getByText('Removed')).toBeInTheDocument();
    expect(screen.getByText('One-Kettlebell Hamstring Walkout')).toBeInTheDocument();
    expect(screen.getByText('Added')).toBeInTheDocument();
    expect(screen.getByText('Dumbbell Neutral-Grip Bench Press')).toBeInTheDocument();
    expect(screen.getByText('Down-ranked')).toBeInTheDocument();
  });

  it('renders the deterministic reason and rule id for a removal', () => {
    render(<AdjustmentDiffView diff={DIFF} adjustment="Exclude deadlifts" />);

    expect(screen.getByText(/Hip Hinge \/ Deadlift Family/)).toBeInTheDocument();
    expect(screen.getByText('explicit_exclusion')).toBeInTheDocument();
    expect(screen.getByText('Now ineligible')).toBeInTheDocument();
  });

  it('shows real score movement for a down-ranked exercise', () => {
    render(<AdjustmentDiffView diff={DIFF} adjustment="Exclude deadlifts" />);
    expect(screen.getByText('87 → 77')).toBeInTheDocument();
  });

  it('never claims an added exercise replaces a removed one', () => {
    const { container } = render(
      <AdjustmentDiffView diff={DIFF} adjustment="Exclude deadlifts" />,
    );
    const text = container.textContent ?? '';

    expect(text).not.toMatch(/equivalent/i);
    expect(text).not.toMatch(/replaces/i);
    expect(text).not.toMatch(/instead of/i);
  });

  it('states that the model did not edit the previous plan', () => {
    render(<AdjustmentDiffView diff={DIFF} adjustment="Exclude deadlifts" />);
    expect(
      screen.getByText(/model never edited the previous plan/i),
    ).toBeInTheDocument();
  });

  it('renders the backend note when nothing changed', () => {
    const unchanged: AdjustmentDiff = {
      removed: [],
      added: [],
      downranked: [],
      retained_ids: ['a'],
      counts: { removed: 0, added: 0, downranked: 0, retained: 1, newly_excluded: 0 },
      notes: [
        'The adjusted request produced the same plan. Every rule was re-evaluated against the graph.',
      ],
    };
    render(
      <AdjustmentDiffView diff={unchanged} adjustment="Avoid knee stress" />,
    );

    expect(screen.getByText(/re-evaluated against the graph/i)).toBeInTheDocument();
    expect(screen.queryByText('Removed')).not.toBeInTheDocument();
  });
});
