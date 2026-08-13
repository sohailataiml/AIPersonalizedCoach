/**
 * System Quality dashboard tests.
 *
 * The property under protection: **nothing on this page is hard-coded.** Every
 * KPI, bar, tick and count must come from the evaluation artifact or the trace
 * payload. A dashboard that displays a green "100%" of its own accord is worse
 * than no dashboard, because it manufactures confidence.
 *
 * So several tests deliberately feed *failing* data and assert the page says so.
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { EvaluationHistoryPanel } from '@/components/system/EvaluationHistoryPanel';
import { EvaluationMatrix } from '@/components/system/EvaluationMatrix';
import {
  KpiCards,
  QualityByCategory,
  SafetyInvariants,
} from '@/components/system/EvaluationOverview';
import {
  ExecutionTraces,
  McpObservability,
  TraceDetail,
} from '@/components/system/ExecutionTraces';
import type { EvaluationRun } from '@/lib/types';
import {
  copilotTrace,
  evaluationHistory,
  evaluationRun,
  generateTrace,
  traces,
} from './system-fixtures';

const safetyMetric = evaluationRun.metrics.find(
  (metric) => metric.key === 'hard_safety_satisfaction',
)!;

describe('KPI cards', () => {
  it('renders ratios taken from the evaluation artifact', () => {
    render(<KpiCards run={evaluationRun} />);

    const cases = screen.getByTestId('kpi-cases');
    expect(
      within(cases).getByText(
        `${evaluationRun.passed_cases} / ${evaluationRun.total_cases}`,
      ),
    ).toBeInTheDocument();

    const safety = screen.getByTestId('kpi-safety');
    expect(
      within(safety).getByText(
        `${safetyMetric.numerator} / ${safetyMetric.denominator}`,
      ),
    ).toBeInTheDocument();
  });

  it('shows the unsafe escape count as a first-class number', () => {
    render(<KpiCards run={evaluationRun} />);
    const card = screen.getByTestId('kpi-unsafe');

    expect(within(card).getByText(String(evaluationRun.unsafe_escapes))).toBeInTheDocument();
    expect(within(card).getByText(/survived final validation/i)).toBeInTheDocument();
  });

  it('flags a run with unsafe escapes rather than showing it as healthy', () => {
    const broken: EvaluationRun = {
      ...evaluationRun,
      unsafe_escapes: 3,
      failed_cases: 3,
      passed_cases: evaluationRun.total_cases - 3,
      status: 'fail',
    };
    render(<KpiCards run={broken} />);

    const card = screen.getByTestId('kpi-unsafe');
    expect(within(card).getByText('3')).toBeInTheDocument();
    expect(card.className).toMatch(/danger/);
  });

  it('renders latency from the measured summary', () => {
    render(<KpiCards run={evaluationRun} />);
    const card = screen.getByTestId('kpi-latency');
    expect(
      within(card).getByText(`${evaluationRun.latency.p95_ms!.toFixed(0)} ms`),
    ).toBeInTheDocument();
  });
});

describe('Safety invariants', () => {
  it('renders one row per invariant, each backed by cases', () => {
    render(<SafetyInvariants invariants={evaluationRun.invariants} />);

    for (const invariant of evaluationRun.invariants) {
      const row = screen.getByTestId(`invariant-${invariant.key}`);
      expect(within(row).getByText(invariant.statement)).toBeInTheDocument();
      expect(within(row).getByText(/proven by \d+ case/)).toBeInTheDocument();
    }
  });

  it('shows a failing invariant prominently and first', () => {
    const invariants = evaluationRun.invariants.map((invariant, index) =>
      index === evaluationRun.invariants.length - 1
        ? { ...invariant, holds: false, proven_by: [], failed_by: ['case-x'] }
        : invariant,
    );
    render(<SafetyInvariants invariants={invariants} />);

    const broken = invariants[invariants.length - 1];
    const row = screen.getByTestId(`invariant-${broken.key}`);
    expect(row.className).toMatch(/danger/);
    expect(within(row).getByText(/case-x/)).toBeInTheDocument();

    // Failing rows sort to the top so they cannot be missed.
    const rows = screen.getAllByTestId(/^invariant-/);
    expect(rows[0]).toBe(row);
  });

  it('counts proven invariants from the data, not a constant', () => {
    render(<SafetyInvariants invariants={evaluationRun.invariants} />);
    const proven = evaluationRun.invariants.filter((i) => i.holds).length;
    expect(
      screen.getByText(`${proven} / ${evaluationRun.invariants.length} proven`),
    ).toBeInTheDocument();
  });
});

describe('Quality by category', () => {
  it('shows a numerator and denominator for every measured metric', () => {
    render(<QualityByCategory metrics={evaluationRun.metrics} />);

    for (const metric of evaluationRun.metrics.filter((m) => m.denominator > 0)) {
      const row = screen.getByTestId(`metric-${metric.key}`);
      expect(
        within(row).getByText(`${metric.numerator}/${metric.denominator}`),
      ).toBeInTheDocument();
    }
  });

  it('omits metrics with nothing measured rather than rendering 0%', () => {
    const metrics = [
      ...evaluationRun.metrics,
      {
        key: 'never_measured',
        label: 'Never measured',
        numerator: 0,
        denominator: 0,
        higher_is_better: true,
        detail: null,
        value: null,
      },
    ];
    render(<QualityByCategory metrics={metrics} />);
    expect(screen.queryByTestId('metric-never_measured')).not.toBeInTheDocument();
  });

  it('states that categories are not averaged', () => {
    render(<QualityByCategory metrics={evaluationRun.metrics} />);
    expect(screen.getByText(/never averaged into one number/i)).toBeInTheDocument();
  });
});

describe('Evaluation matrix', () => {
  it('lists every case with its result and latency', () => {
    render(<EvaluationMatrix results={evaluationRun.results} />);
    const list = screen.getByRole('region', { name: 'Evaluation case list' });

    for (const result of evaluationRun.results) {
      expect(within(list).getByText(result.name)).toBeInTheDocument();
      expect(
        within(list).getByText(`${result.latency_ms.toFixed(1)} ms`),
      ).toBeInTheDocument();
    }
    expect(within(list).getAllByText('PASS').length).toBe(
      evaluationRun.results.filter((r) => r.passed).length,
    );
  });

  it('filters by category', async () => {
    const user = userEvent.setup();
    render(<EvaluationMatrix results={evaluationRun.results} />);

    await user.click(screen.getByRole('button', { name: 'Safety' }));
    const list = screen.getByRole('region', { name: 'Evaluation case list' });
    const safetyCases = evaluationRun.results.filter((r) => r.category === 'safety');
    const otherCase = evaluationRun.results.find((r) => r.category === 'equipment')!;

    expect(within(list).getByText(safetyCases[0].name)).toBeInTheDocument();
    expect(within(list).queryByText(otherCase.name)).not.toBeInTheDocument();
  });

  it('filters by pass/fail', async () => {
    const user = userEvent.setup();
    const withFailure = evaluationRun.results.map((result, index) =>
      index === 0 ? { ...result, passed: false, actual: 'deliberate failure' } : result,
    );
    render(<EvaluationMatrix results={withFailure} />);

    await user.click(screen.getByRole('button', { name: 'FAIL' }));
    const list = screen.getByRole('region', { name: 'Evaluation case list' });
    expect(within(list).getByText(withFailure[0].name)).toBeInTheDocument();
    expect(within(list).queryByText(withFailure[1].name)).not.toBeInTheDocument();
  });

  it('opens a case detail with expected and actual behaviour', async () => {
    const user = userEvent.setup();
    render(<EvaluationMatrix results={evaluationRun.results} />);

    const target = evaluationRun.results.find(
      (result) => result.case_id === 'safe-knee-plyometric',
    )!;
    await user.click(screen.getByRole('button', { name: `Inspect ${target.name}` }));

    const detail = screen.getByRole('region', { name: 'Evaluation case detail' });
    expect(within(detail).getByText(target.expected)).toBeInTheDocument();
    expect(within(detail).getByText(target.actual)).toBeInTheDocument();
    expect(within(detail).getByText(target.case_id)).toBeInTheDocument();
  });

  it('renders graph evidence through the shared path viewer', async () => {
    const user = userEvent.setup();
    render(<EvaluationMatrix results={evaluationRun.results} />);

    const target = evaluationRun.results.find(
      (result) => result.case_id === 'safe-knee-plyometric',
    )!;
    await user.click(screen.getByRole('button', { name: `Inspect ${target.name}` }));

    const detail = screen.getByRole('region', { name: 'Evaluation case detail' });
    // DecisionPaths is the coach UI's component: reused, not re-implemented.
    expect(
      within(detail).getAllByRole('region', { name: 'Decision paths' }).length,
    ).toBeGreaterThan(0);
    expect(within(detail).getAllByText('Decision').length).toBeGreaterThan(0);
  });

  it('highlights an unsafe escape in the case detail', async () => {
    const user = userEvent.setup();
    const escaped = evaluationRun.results.map((result, index) =>
      index === 0
        ? { ...result, passed: false, unsafe_escape: true, actual: 'escaped' }
        : result,
    );
    render(<EvaluationMatrix results={escaped} />);

    await user.click(screen.getByRole('button', { name: `Inspect ${escaped[0].name}` }));
    expect(
      screen.getByText(/Unsafe exercise survived final validation/i),
    ).toBeInTheDocument();
  });
});

describe('Execution traces', () => {
  it('lists recent requests with their durations', () => {
    render(<ExecutionTraces traces={traces} />);
    const list = screen.getByRole('region', { name: 'Trace list' });

    expect(within(list).getByText(generateTrace.request_id)).toBeInTheDocument();
    expect(within(list).getByText(copilotTrace.request_id)).toBeInTheDocument();
    expect(
      within(list).getByText(`${generateTrace.total_duration_ms.toFixed(1)} ms`),
    ).toBeInTheDocument();
  });

  it('shows an honest empty state before anything is traced', () => {
    render(<ExecutionTraces traces={[]} />);
    expect(screen.getByText(/No requests traced yet/i)).toBeInTheDocument();
  });

  it('renders a waterfall with the safe candidate boundary', () => {
    render(<TraceDetail trace={generateTrace} />);

    expect(screen.getByText('evaluate_safety')).toBeInTheDocument();
    expect(screen.getByText('compose_workout (LLM)')).toBeInTheDocument();
    expect(screen.getByText(/Safe candidate boundary/i)).toBeInTheDocument();
  });

  it('breaks time down by architectural zone', () => {
    render(<TraceDetail trace={generateTrace} />);

    expect(screen.getByText('Deterministic')).toBeInTheDocument();
    expect(screen.getByText('Generative')).toBeInTheDocument();
    // 0.05 + 5.39 + 0.84 + 20.7 + 1.67 + 3.1 + 4.2 = 35.95
    expect(screen.getByText('35.95 ms')).toBeInTheDocument();
    // 9.60 ms appears twice by design: once as the LLM span in the waterfall,
    // once as the generative-zone total.
    expect(screen.getAllByText('9.60 ms').length).toBe(2);
  });

  it('shows the safety summary counts from the trace', () => {
    render(<TraceDetail trace={generateTrace} />);

    expect(screen.getByText('50')).toBeInTheDocument();
    expect(screen.getByText('34')).toBeInTheDocument();
    expect(screen.getByText('212')).toBeInTheDocument();
    for (const rule of generateTrace.safety!.rules_fired) {
      expect(screen.getByText(rule)).toBeInTheDocument();
    }
  });

  it('states that no member payload or reasoning is recorded', () => {
    render(<TraceDetail trace={generateTrace} />);
    expect(
      screen.getByText(/No member payload, prompt body or model reasoning/i),
    ).toBeInTheDocument();
  });
});

describe('MCP observability', () => {
  it('shows the intent, tools and mode without the coach question', () => {
    render(<McpObservability traces={traces} />);

    const row = screen.getByTestId(`mcp-row-${copilotTrace.request_id}`);
    expect(within(row).getByText('ADHERENCE_TREND')).toBeInTheDocument();
    expect(within(row).getByText('get_member_metric_trend')).toBeInTheDocument();
    expect(within(row).getByText('mcp')).toBeInTheDocument();
  });

  it('excludes non-copilot traces', () => {
    render(<McpObservability traces={traces} />);
    expect(
      screen.queryByTestId(`mcp-row-${generateTrace.request_id}`),
    ).not.toBeInTheDocument();
  });

  it('says the question is never recorded', () => {
    render(<McpObservability traces={traces} />);
    expect(screen.getByText(/question is never recorded/i)).toBeInTheDocument();
  });
});

describe('Evaluation history', () => {
  it('lists recent runs with their measured counts', () => {
    render(<EvaluationHistoryPanel history={evaluationHistory} />);

    const row = screen.getByTestId(`eval-run-${evaluationRun.run_id}`);
    expect(
      within(row).getAllByText(String(evaluationRun.total_cases)).length,
    ).toBeGreaterThan(0);
    expect(within(row).getByText('PASS')).toBeInTheDocument();
  });

  it('does not manufacture a trend from a single run', () => {
    render(<EvaluationHistoryPanel history={evaluationHistory} />);

    expect(screen.queryByLabelText('P95 latency trend')).not.toBeInTheDocument();
    expect(screen.getByText(/no history is manufactured/i)).toBeInTheDocument();
  });

  it('shows a trend once more than one run exists', () => {
    const two = {
      count: 2,
      runs: [
        evaluationHistory.runs[0],
        { ...evaluationHistory.runs[0], run_id: 'eval-older', p95_ms: 120 },
      ],
    };
    render(<EvaluationHistoryPanel history={two} />);
    expect(screen.getByLabelText('P95 latency trend')).toBeInTheDocument();
  });

  it('shows an empty state when no runs exist', () => {
    render(<EvaluationHistoryPanel history={{ runs: [], count: 0 }} />);
    expect(screen.getByText(/No evaluation runs yet/i)).toBeInTheDocument();
  });
});
