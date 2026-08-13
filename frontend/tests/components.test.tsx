/**
 * Frontend component tests.
 *
 * These cover the interactions a coach actually performs and the ones that
 * carry meaning for the architecture: that resolution is visible, that the plan
 * renders, and above all that clicking a safety row surfaces the graph paths
 * behind that decision. Fixtures are captured verbatim from the running backend
 * so the tests fail if the API contract drifts.
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { CopilotCard } from '@/components/copilot/CopilotCard';
import { MemberMetricStrip } from '@/components/member/MemberMetricStrip';
import { SafetyInspector } from '@/components/provenance/SafetyInspector';
import { ConceptResolution } from '@/components/workout/ConceptResolution';
import { DurationSelector } from '@/components/workout/DurationSelector';
import { WorkoutGeneratorCard } from '@/components/workout/WorkoutGeneratorCard';
import { statusOf } from '@/lib/presentation';
import {
  copilotFixture,
  historyFixture,
  mcpCopilotFixture,
  memberFixture,
  workoutFixture,
} from './fixtures';

describe('DurationSelector', () => {
  it('marks the active duration and reports the chosen value', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<DurationSelector value={45} onChange={onChange} />);

    const selected = screen.getByRole('radio', { name: '45 min' });
    expect(selected).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: '30 min' })).toHaveAttribute(
      'aria-checked',
      'false',
    );

    await user.click(screen.getByRole('radio', { name: '60 min' }));
    expect(onChange).toHaveBeenCalledWith(60);
  });

  it('exposes all four durations as a labelled radio group', () => {
    render(<DurationSelector value={20} onChange={vi.fn()} />);
    const group = screen.getByRole('radiogroup', { name: /duration/i });
    expect(within(group).getAllByRole('radio')).toHaveLength(4);
  });

  it('cannot be changed while a request is running', async () => {
    const onChange = vi.fn();
    render(<DurationSelector value={45} onChange={onChange} disabled />);
    await userEvent.click(screen.getByRole('radio', { name: '20 min' }));
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe('ConceptResolution', () => {
  it('shows each phrase, its canonical concept and the matching pass', () => {
    render(
      <ConceptResolution
        resolved={workoutFixture.resolved_concepts}
        unresolved={workoutFixture.unresolved_concepts}
      />,
    );

    expect(screen.getByText('“left knee”')).toBeInTheDocument();
    expect(screen.getByText('anatomy.knee')).toBeInTheDocument();
    expect(screen.getByText('equipment.kettlebell')).toBeInTheDocument();

    // Method badges distinguish how each match was made.
    expect(screen.getByText('exact')).toBeInTheDocument();
    expect(screen.getAllByText('alias').length).toBeGreaterThan(0);
    expect(screen.getByText('fuzzy')).toBeInTheDocument();
  });

  it('surfaces unresolved phrases instead of hiding them', () => {
    render(
      <ConceptResolution
        resolved={[]}
        unresolved={[
          {
            source_text: 'weird knee-ish thing',
            canonical_id: null,
            label: null,
            concept_type: null,
            method: 'unresolved',
            confidence: 0.45,
            alternatives: [],
          },
        ]}
      />,
    );

    expect(screen.getByText('“weird knee-ish thing”')).toBeInTheDocument();
    expect(screen.getByText('unresolved')).toBeInTheDocument();
    expect(screen.getByText(/reported rather than guessed/i)).toBeInTheDocument();
  });

  it('renders nothing when there is no resolution to show', () => {
    const { container } = render(<ConceptResolution resolved={[]} unresolved={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('WorkoutGeneratorCard', () => {
  const baseProps = {
    prompt: 'Create a 45-minute lower-body workout.',
    duration: 45,
    onPromptChange: vi.fn(),
    onDurationChange: vi.fn(),
    onGenerate: vi.fn(),
    isGenerating: false,
  };

  it('renders warm-up, main and cool-down with prescriptions', () => {
    render(<WorkoutGeneratorCard {...baseProps} result={workoutFixture} />);

    expect(screen.getByRole('region', { name: 'Warm-up' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Main' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Cool-down' })).toBeInTheDocument();

    const firstExercise = workoutFixture.workout.sections[0].exercises[0];
    expect(
      screen.getByRole('button', { name: firstExercise.name }),
    ).toBeInTheDocument();

    const planned = workoutFixture.workout.sections.flatMap((s) => s.exercises);
    expect(screen.getByText(`${planned.length} exercises`, { exact: false })).toBeInTheDocument();
  });

  it('fills the prompt from a scenario chip', async () => {
    const user = userEvent.setup();
    const onPromptChange = vi.fn();
    render(
      <WorkoutGeneratorCard
        {...baseProps}
        onPromptChange={onPromptChange}
        onDurationChange={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Exclusion' }));
    expect(onPromptChange).toHaveBeenCalledWith(
      expect.stringContaining('exclude deadlifts'),
    );
  });

  it('blocks duplicate submissions while generating', async () => {
    const onGenerate = vi.fn();
    render(
      <WorkoutGeneratorCard {...baseProps} onGenerate={onGenerate} isGenerating />,
    );

    const button = screen.getByRole('button', { name: /reasoning over graph/i });
    expect(button).toBeDisabled();
    await userEvent.click(button);
    expect(onGenerate).not.toHaveBeenCalled();
  });

  it('reports a backend failure without pretending to have a plan', () => {
    render(
      <WorkoutGeneratorCard {...baseProps} error={new Error('Cannot reach the API.')} />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Cannot reach the API.');
  });

  it('explains the fail-closed state when nothing is eligible', () => {
    const empty = {
      ...workoutFixture,
      safety: { ...workoutFixture.safety, eligible: 0 },
    };
    render(<WorkoutGeneratorCard {...baseProps} result={empty} />);
    expect(screen.getByRole('alert')).toHaveTextContent(/fails closed/i);
  });
});

describe('CopilotCard', () => {
  const baseProps = {
    member: memberFixture,
    history: historyFixture,
    turns: [],
    isPending: false,
  };

  it('sends the exact quick-prompt text when a chip is clicked', async () => {
    const user = userEvent.setup();
    const onAsk = vi.fn();
    render(<CopilotCard {...baseProps} onAsk={onAsk} />);

    await user.click(screen.getByRole('button', { name: "How's adherence trending?" }));
    expect(onAsk).toHaveBeenCalledWith("How's adherence trending?");
  });

  it('offers every documented quick prompt', () => {
    render(<CopilotCard {...baseProps} onAsk={vi.fn()} />);
    const quick = screen.getByRole('region', { name: 'Quick prompts' });
    for (const prompt of [
      'Show me the brief',
      'Sleep this week',
      'What changed since last week?',
      'Is there any churn risk?',
      'Show message pattern',
    ]) {
      expect(within(quick).getByRole('button', { name: prompt })).toBeInTheDocument();
    }
  });

  it('renders the morning brief from member context', () => {
    render(<CopilotCard {...baseProps} onAsk={vi.fn()} />);
    const brief = screen.getByRole('region', { name: 'Morning brief' });
    expect(
      within(brief).getByText(memberFixture.morning_tasks[0].text),
    ).toBeInTheDocument();
  });

  it('plots adherence from real observations with a text alternative', () => {
    render(<CopilotCard {...baseProps} onAsk={vi.fn()} />);
    const chart = screen.getByRole('region', { name: 'Adherence trend' });

    const weeks = historyFixture.adherence.length;
    expect(within(chart).getByText(`Adherence (last ${weeks} weeks)`)).toBeInTheDocument();

    const first = historyFixture.adherence[0].pct;
    const last = historyFixture.adherence[weeks - 1].pct;
    expect(within(chart).getByText(`${first}% → ${last}%`, { exact: false })).toBeInTheDocument();
    expect(within(chart).getByText(/weekly completion is declining/i)).toBeInTheDocument();
  });

  it('shows a grounded answer with its citations', () => {
    render(
      <CopilotCard
        {...baseProps}
        onAsk={vi.fn()}
        turns={[
          { role: 'coach', text: "How's adherence trending?" },
          { role: 'assistant', text: copilotFixture.answer, response: copilotFixture },
        ]}
      />,
    );

    expect(screen.getByText(copilotFixture.answer)).toBeInTheDocument();
    expect(
      screen.getByText(copilotFixture.citations[0].source, { exact: false }),
    ).toBeInTheDocument();
  });

  it('disables input while a question is in flight', () => {
    render(<CopilotCard {...baseProps} onAsk={vi.fn()} isPending />);
    expect(screen.getByLabelText(/ask about this member/i)).toBeDisabled();
    expect(screen.getByRole('button', { name: /send message/i })).toBeDisabled();
  });

  /**
   * The regression: an MCP-grounded safety answer once rendered the raw tool
   * payload as the chat message. The visible bubble must be the prose the
   * backend wrote, and the structured detail must stay behind a disclosure.
   */
  describe('MCP-grounded safety answers', () => {
    function renderSafetyTurn() {
      render(
        <CopilotCard
          {...baseProps}
          onAsk={vi.fn()}
          turns={[
            { role: 'coach', text: 'Can Jordan do Static Jump today?' },
            {
              role: 'assistant',
              text: mcpCopilotFixture.answer,
              response: mcpCopilotFixture,
            },
          ]}
        />,
      );
    }

    it('renders response.answer as the assistant message', () => {
      renderSafetyTurn();
      expect(screen.getByText(mcpCopilotFixture.answer)).toBeInTheDocument();
    });

    it('never shows a serialized payload in the default view', () => {
      renderSafetyTurn();
      const body = document.body.textContent ?? '';

      for (const marker of ["{'", '{"', 'member_id', 'exercise_id', 'is_excluded']) {
        expect(body).not.toContain(marker);
      }
    });

    it('shows the MCP grounded and safety authoritative badges', () => {
      renderSafetyTurn();
      expect(screen.getByText(/MCP grounded/i)).toBeInTheDocument();
      expect(screen.getByText(/Safety authoritative/i)).toBeInTheDocument();
    });

    it('lists the tools that actually ran', () => {
      renderSafetyTurn();
      for (const tool of mcpCopilotFixture.grounding!.tools_used) {
        expect(screen.getByText(tool)).toBeInTheDocument();
      }
    });

    it('keeps graph evidence collapsed until asked for', async () => {
      const user = userEvent.setup();
      renderSafetyTurn();

      const evidence = mcpCopilotFixture.safety_evidence!;
      const disclosure = screen.getByText(/view evidence/i);
      expect(disclosure.closest('details')).not.toHaveAttribute('open');

      await user.click(disclosure);

      expect(disclosure.closest('details')).toHaveAttribute('open');
      expect(screen.getByText(evidence.rule_ids[0])).toBeInTheDocument();
      expect(screen.getByText(evidence.reasons[0].message)).toBeInTheDocument();
      // The real traversal, exactly as the graph engine rendered it.
      expect(screen.getByText(evidence.graph_paths[0])).toBeInTheDocument();
    });

    it('states the decision in the evidence panel', async () => {
      const user = userEvent.setup();
      renderSafetyTurn();

      await user.click(screen.getByText(/view evidence/i));
      expect(screen.getByText('excluded')).toBeInTheDocument();
      expect(screen.getByText('Static Jump')).toBeInTheDocument();
    });

    it('falls back to readable text when the answer is missing', () => {
      render(
        <CopilotCard
          {...baseProps}
          onAsk={vi.fn()}
          turns={[
            { role: 'assistant', text: '   ', response: mcpCopilotFixture },
          ]}
        />,
      );

      expect(
        screen.getByText(/explanation could not be formatted/i),
      ).toBeInTheDocument();
      // Still no payload, even in the degraded case.
      expect(document.body.textContent ?? '').not.toContain('{');
    });

    it('flags a corrected verdict', () => {
      const corrected = {
        ...mcpCopilotFixture,
        grounding: { ...mcpCopilotFixture.grounding!, safety_corrected: true },
      };
      render(
        <CopilotCard
          {...baseProps}
          onAsk={vi.fn()}
          turns={[{ role: 'assistant', text: corrected.answer, response: corrected }]}
        />,
      );

      expect(screen.getByText(/verdict corrected/i)).toBeInTheDocument();
    });
  });
});

describe('SafetyInspector', () => {
  /** Mirrors the page's selection state so the click-through is exercised. */
  function Harness() {
    const [selected, setSelected] = useState<string | null>(null);
    return (
      <SafetyInspector
        result={workoutFixture}
        selectedExerciseId={selected}
        onSelect={setSelected}
      />
    );
  }

  it('shows real removed / down-ranked / in-plan counts', () => {
    render(<Harness />);
    const filtered = workoutFixture.filtered_exercises.filter(
      (i) => i.decision === 'filtered',
    ).length;
    // Down-ranked spans both buckets: unused ones in `filtered_exercises` and
    // cautioned ones that still made the plan, under `provenance`.
    const downranked =
      workoutFixture.filtered_exercises.filter((i) => i.decision === 'downranked')
        .length +
      workoutFixture.provenance.filter((i) => statusOf(i) === 'cautioned').length;

    expect(screen.getByText(`${filtered} removed`)).toBeInTheDocument();
    expect(screen.getByText(`${downranked} down-ranked`)).toBeInTheDocument();
    expect(
      screen.getByText(`${workoutFixture.safety.in_plan} in plan`),
    ).toBeInTheDocument();
  });

  it('switches the decision table between tabs', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const filteredNames = workoutFixture.filtered_exercises
      .filter((i) => i.decision === 'filtered')
      .map((i) => i.exercise);
    expect(
      screen.getByRole('button', { name: filteredNames[0] }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: /in the plan/i }));

    const planned = workoutFixture.provenance[0].exercise;
    expect(screen.getByRole('button', { name: planned })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /in the plan/i })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('shows member evidence on its own tab', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole('tab', { name: /member evidence/i }));
    expect(screen.getByText('Member facts used')).toBeInTheDocument();
    expect(screen.getByText(workoutFixture.member_facts[0])).toBeInTheDocument();
  });

  /** The highest-priority interaction in the redesign. */
  it('updates the provenance panel when a safety row is clicked', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const filtered = workoutFixture.filtered_exercises.filter(
      (i) => i.decision === 'filtered',
    );
    const target = filtered.find((i) => i.evidence.length > 0) ?? filtered[1];

    await user.click(screen.getByRole('button', { name: target.exercise }));

    const panel = screen.getByRole('region', { name: 'Provenance detail' });

    // The panel now describes the clicked exercise...
    expect(
      within(panel).getByRole('heading', { level: 3, name: target.exercise }),
    ).toBeInTheDocument();
    // ...with its real reason text...
    expect(within(panel).getByText(target.reasons[0])).toBeInTheDocument();
    // ...and the graph nodes that justified it.
    expect(target.evidence.length).toBeGreaterThan(0);
    const firstNode = target.evidence[0].path[0];
    expect(within(panel).getAllByText(firstNode).length).toBeGreaterThan(0);
    expect(within(panel).getByText('Graph path')).toBeInTheDocument();
    expect(
      within(panel).getByText(
        `${target.evidence.length} graph path${target.evidence.length === 1 ? '' : 's'}`,
        { exact: false },
      ),
    ).toBeInTheDocument();
  });

  it('always attributes the decision to the graph, not the model', async () => {
    render(<Harness />);
    expect(screen.getByText('✕ LLM did not decide safety')).toBeInTheDocument();
    expect(screen.getByText(/Knowledge graph/)).toBeInTheDocument();
  });

  it('invites a generation before a plan exists', () => {
    render(
      <SafetyInspector result={null} selectedExerciseId={null} onSelect={vi.fn()} />,
    );
    expect(screen.getByText('Nothing to inspect yet')).toBeInTheDocument();
  });
});

describe('MemberMetricStrip', () => {
  it('renders KPIs from member data with sized trend windows', () => {
    render(<MemberMetricStrip member={memberFixture} history={historyFixture} />);

    expect(screen.getByText('Left Knee')).toBeInTheDocument();
    expect(
      screen.getByText(`${memberFixture.latest_adherence_pct}%`),
    ).toBeInTheDocument();
    expect(screen.getByText('Elevated')).toBeInTheDocument();
    expect(screen.getByText(`${memberFixture.avg_sleep_hours}h`)).toBeInTheDocument();

    // Window sizes reflect the data actually present, not a hard-coded period.
    expect(
      screen.getByText(`Adherence (${historyFixture.adherence.length}w)`),
    ).toBeInTheDocument();
    expect(
      screen.getByText(`Avg sleep (${historyFixture.sleep.length}d)`),
    ).toBeInTheDocument();
  });

  it('lists the member equipment', () => {
    render(<MemberMetricStrip member={memberFixture} history={historyFixture} />);
    expect(screen.getByText('Dumbbell')).toBeInTheDocument();
    expect(screen.getByText('Kettlebell')).toBeInTheDocument();
  });
});
