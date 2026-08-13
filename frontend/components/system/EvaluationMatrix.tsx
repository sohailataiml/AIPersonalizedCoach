'use client';

import { useMemo, useState } from 'react';

import { DecisionPaths } from '@/components/graph/DecisionPaths';
import {
  Badge,
  Card,
  CardHead,
  EmptyState,
  cx,
} from '@/components/ui/primitives';
import type { EvaluationCaseResult, EvaluationCategory } from '@/lib/types';

/**
 * The evaluation matrix and its case-detail panel.
 *
 * Safety evidence is rendered with `DecisionPaths` — the same component the
 * coach-facing graph panel uses. There is deliberately no second provenance
 * renderer here: two renderers of the same evidence eventually disagree, and
 * the one in the engineering dashboard is the one nobody would notice drifting.
 */

const CATEGORY_LABEL: Record<EvaluationCategory, string> = {
  concept_resolution: 'Concept resolution',
  safety: 'Safety',
  equipment: 'Equipment',
  exclusion: 'Exclusions',
  longitudinal: 'Longitudinal',
  adjustment: 'Adjustment',
  validation: 'Validation',
  copilot_mcp: 'Copilot / MCP',
};

type ResultFilter = 'all' | 'pass' | 'fail';

export function EvaluationMatrix({ results }: { results: EvaluationCaseResult[] }) {
  const [category, setCategory] = useState<EvaluationCategory | 'all'>('all');
  const [outcome, setOutcome] = useState<ResultFilter>('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const categories = useMemo(() => {
    const present = new Set(results.map((result) => result.category));
    return (Object.keys(CATEGORY_LABEL) as EvaluationCategory[]).filter((key) =>
      present.has(key),
    );
  }, [results]);

  const visible = useMemo(
    () =>
      results.filter(
        (result) =>
          (category === 'all' || result.category === category) &&
          (outcome === 'all' ||
            (outcome === 'pass' ? result.passed : !result.passed)),
      ),
    [results, category, outcome],
  );

  const selected =
    visible.find((result) => result.case_id === selectedId) ?? visible[0] ?? null;

  return (
    <Card>
      <CardHead
        title="Evaluation cases"
        right={
          <Badge tone="neutral">
            {visible.length} of {results.length}
          </Badge>
        }
      />

      <div className="flex flex-wrap gap-1.5 border-b border-ink-200 px-5 pb-3 pt-1">
        <FilterChip
          label="All"
          active={category === 'all'}
          onClick={() => setCategory('all')}
        />
        {categories.map((key) => (
          <FilterChip
            key={key}
            label={CATEGORY_LABEL[key]}
            active={category === key}
            onClick={() => setCategory(key)}
          />
        ))}
        <span aria-hidden className="mx-1 w-px bg-ink-200" />
        {(['all', 'pass', 'fail'] as ResultFilter[]).map((key) => (
          <FilterChip
            key={key}
            label={key === 'all' ? 'Any result' : key.toUpperCase()}
            active={outcome === key}
            onClick={() => setOutcome(key)}
          />
        ))}
      </div>

      <div className="grid gap-0 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <div
          role="region"
          aria-label="Evaluation case list"
          className="scrollbar-slim max-h-[520px] overflow-y-auto border-b border-ink-200 lg:border-b-0 lg:border-r"
        >
          {visible.length ? (
            <table className="w-full border-collapse">
              <thead className="sticky top-0 z-10 bg-ink-50">
                <tr className="text-left text-[9.5px] uppercase tracking-wide text-ink-400">
                  <th className="px-4 py-1.5 font-medium">Category</th>
                  <th className="px-2 py-1.5 font-medium">Case</th>
                  <th className="px-2 py-1.5 font-medium">Result</th>
                  <th className="px-4 py-1.5 text-right font-medium">Latency</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((result) => (
                  <tr key={result.case_id}>
                    <td colSpan={4} className="p-0">
                      <button
                        type="button"
                        onClick={() => setSelectedId(result.case_id)}
                        aria-label={`Inspect ${result.name}`}
                        className={cx(
                          'flex w-full items-center gap-2 border-b border-ink-100 px-4 py-1.5 text-left',
                          selected?.case_id === result.case_id
                            ? 'bg-brand-50'
                            : 'hover:bg-ink-50',
                        )}
                      >
                        <span className="w-28 shrink-0 text-[10px] text-ink-500">
                          {CATEGORY_LABEL[result.category]}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-2xs text-navy-900">
                          {result.name}
                        </span>
                        <span
                          className={cx(
                            'shrink-0 rounded px-1.5 text-[9.5px] font-semibold',
                            result.passed
                              ? 'bg-safe-50 text-safe-700'
                              : 'bg-danger-100 text-danger-800',
                          )}
                        >
                          {result.passed ? 'PASS' : 'FAIL'}
                        </span>
                        <span className="w-14 shrink-0 text-right font-mono text-[9.5px] tabular-nums text-ink-400">
                          {result.latency_ms.toFixed(1)} ms
                        </span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState
              title="No cases match"
              body="Adjust the category or result filter."
            />
          )}
        </div>

        <div className="scrollbar-slim max-h-[520px] overflow-y-auto bg-ink-50/50 p-4">
          {selected ? (
            <CaseDetail result={selected} />
          ) : (
            <EmptyState
              title="Select a case"
              body="Choose an evaluation case to see what was expected, what happened, and the graph evidence behind it."
            />
          )}
        </div>
      </div>
    </Card>
  );
}

function CaseDetail({ result }: { result: EvaluationCaseResult }) {
  return (
    <section aria-label="Evaluation case detail" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold tracking-tight text-navy-900">
          {result.name}
        </h3>
        <Badge tone={result.passed ? 'safe' : 'danger'}>
          {result.passed ? 'PASS' : 'FAIL'}
        </Badge>
      </div>
      <div className="font-mono text-[9.5px] text-ink-400">{result.case_id}</div>

      {result.unsafe_escape ? (
        <div className="rounded-lg border border-danger-300 bg-danger-50 p-2.5">
          <div className="text-2xs font-semibold text-danger-800">
            Unsafe exercise survived final validation
          </div>
          <p className="text-[10.5px] text-danger-700">
            This is the metric that must be zero. Investigate before shipping.
          </p>
        </div>
      ) : null}

      <Field label="Input" value={result.input_summary} mono />
      <Field label="Expected" value={result.expected} />
      <Field label="Actual" value={result.actual} />
      <Field label="Latency" value={`${result.latency_ms.toFixed(2)} ms`} mono />

      {result.notes.length ? (
        <div>
          <div className="label-caps mb-1">Notes</div>
          <ul className="space-y-0.5">
            {result.notes.map((note) => (
              <li key={note} className="text-[10.5px] text-ink-600">
                {note}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {result.evidence.map((evidence, index) => (
        <div key={`${evidence.exercise}-${index}`}>
          <div className="mb-1 flex flex-wrap items-baseline gap-2">
            <span className="label-caps">Graph evidence</span>
            <span className="text-[10px] text-ink-500">{evidence.exercise}</span>
          </div>
          {evidence.traversals.length ? (
            <DecisionPaths traversals={evidence.traversals} />
          ) : (
            <ul className="space-y-0.5">
              {evidence.rendered_paths.map((path) => (
                <li key={path} className="font-mono text-[9.5px] text-ink-600">
                  {path}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </section>
  );
}

function Field({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <div className="label-caps mb-0.5">{label}</div>
      <p
        className={cx(
          'text-2xs leading-relaxed text-ink-700',
          mono && 'font-mono text-[10px]',
        )}
      >
        {value}
      </p>
    </div>
  );
}

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cx(
        'rounded-full border px-2 py-0.5 text-[10px] transition-colors',
        active
          ? 'border-brand-300 bg-brand-50 text-brand-800'
          : 'border-ink-200 text-ink-600 hover:bg-ink-50',
      )}
    >
      {label}
    </button>
  );
}
