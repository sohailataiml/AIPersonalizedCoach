/**
 * Longitudinal context UI tests.
 *
 * The panel exists to make a personalization signal auditable, so the tests
 * check exactly that: every number shown comes from the payload, the
 * ranking-only boundary is stated, and the injury reading is labelled as
 * recorded rather than assessed.
 *
 * The absence tests matter as much as the presence ones — a response without a
 * trajectory must render no longitudinal claims at all, not a default one.
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { GraphReasoningPanel } from '@/components/graph/GraphReasoningPanel';
import { LongitudinalContext } from '@/components/graph/LongitudinalContext';
import type { GenerateWorkoutResponse, MemberTrajectory } from '@/lib/types';
import { workoutFixture } from './fixtures';

const trajectory = workoutFixture.trajectory as MemberTrajectory;

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

async function openSummary(result?: GenerateWorkoutResponse) {
  const user = userEvent.setup();
  render(<Panel result={result} />);
  await user.click(screen.getByRole('tab', { name: /decision summary/i }));
  return user;
}

describe('LongitudinalContext', () => {
  it('states the progression decision and the volume bias', () => {
    render(<LongitudinalContext trajectory={trajectory} />);

    expect(screen.getByText(/Progression: Hold/i)).toBeInTheDocument();
    expect(screen.getByText(/conservative volume/i)).toBeInTheDocument();
  });

  it('renders each signal from the payload rather than deriving one', () => {
    render(<LongitudinalContext trajectory={trajectory} />);

    expect(screen.getByText(/declining · 100% → 50% over 4 weeks/)).toBeInTheDocument();
    expect(screen.getByText(/flat · avg 6.27h over 7 nights/)).toBeInTheDocument();
    expect(screen.getByText(/low · 2.62\/week against a target of 4/)).toBeInTheDocument();
  });

  it('reports sleep as flat, matching the data rather than the narrative', () => {
    // The member is struggling on adherence, but the sleep numbers do not
    // trend down. The UI must not round that into "declining".
    render(<LongitudinalContext trajectory={trajectory} />);

    expect(screen.getByText(/flat · avg 6.27h/)).toBeInTheDocument();
    expect(screen.queryByText(/declining · avg/)).not.toBeInTheDocument();
  });

  it('lists the rationale behind the progression state', () => {
    render(<LongitudinalContext trajectory={trajectory} />);

    for (const reason of trajectory.progression.rationale) {
      expect(screen.getByText(new RegExp(reason.replace(/[.()]/g, '\\$&')))).toBeInTheDocument();
    }
  });

  it('states that longitudinal reasoning never decides eligibility', () => {
    render(<LongitudinalContext trajectory={trajectory} />);

    expect(screen.getByText(/ranking and volume only/i)).toBeInTheDocument();
    expect(
      screen.getByText(/hard safety exclusions are applied before/i),
    ).toBeInTheDocument();
  });

  it('labels the injury reading as recorded, not inferred', () => {
    render(<LongitudinalContext trajectory={trajectory} />);

    expect(
      screen.getByText(/read from the recorded status — not inferred/i),
    ).toBeInTheDocument();
  });

  it('shows insufficient data instead of a fabricated direction', () => {
    const sparse: MemberTrajectory = {
      ...trajectory,
      adherence: { ...trajectory.adherence, direction: 'insufficient_data' },
      training_load: { ...trajectory.training_load, state: 'insufficient_data' },
      progression: { state: 'insufficient_data', rationale: [] },
    };
    render(<LongitudinalContext trajectory={sparse} />);

    expect(screen.getByText(/Progression: Insufficient data/i)).toBeInTheDocument();
    expect(screen.getAllByText('insufficient data').length).toBe(2);
    expect(screen.queryByText(/volume$/)).not.toBeInTheDocument();
  });

  it('omits the recorded-status note when no injury is recorded', () => {
    const healthy: MemberTrajectory = {
      ...trajectory,
      injury_trajectory: {
        state: 'unknown',
        source: 'absent',
        injury_name: null,
        recorded_status: null,
        severity: null,
      },
    };
    render(<LongitudinalContext trajectory={healthy} />);

    expect(screen.queryByText(/not inferred/i)).not.toBeInTheDocument();
  });
});

describe('Decision summary tab', () => {
  it('surfaces the longitudinal context alongside the LLM boundary', async () => {
    await openSummary();

    expect(screen.getByText('Longitudinal context')).toBeInTheDocument();
    // Scoped to the panel: the pipeline flow above it also reports the
    // progression state, as the outcome of its own stage.
    const panel = screen.getByRole('region', { name: 'Longitudinal context' });
    expect(within(panel).getByText(/Progression: Hold/i)).toBeInTheDocument();
  });

  it('renders nothing longitudinal when the backend omitted it', async () => {
    const { trajectory: _trajectory, ...withoutTrajectory } = workoutFixture;
    await openSummary(withoutTrajectory as GenerateWorkoutResponse);

    expect(screen.queryByText('Longitudinal context')).not.toBeInTheDocument();
    expect(screen.queryByText(/Progression:/i)).not.toBeInTheDocument();
  });
});

describe('Provenance exposure', () => {
  it('carries the longitudinal reason on the items it influenced', () => {
    const influenced = workoutFixture.provenance.filter(
      (item) => (item.longitudinal_adjustment ?? 0) !== 0,
    );

    for (const item of influenced) {
      expect(item.longitudinal_reasons?.length).toBeGreaterThan(0);
      expect(
        item.reasons.some((reason) =>
          reason.startsWith('Longitudinal personalization:'),
        ),
      ).toBe(true);
    }
  });

  it('keeps the safety adjustment separate from the longitudinal one', () => {
    for (const item of workoutFixture.provenance) {
      // Two independent fields: a reader can always tell which system moved
      // this exercise and by how much.
      expect(typeof item.score_adjustment).toBe('number');
      expect(typeof (item.longitudinal_adjustment ?? 0)).toBe('number');
    }
  });
});
