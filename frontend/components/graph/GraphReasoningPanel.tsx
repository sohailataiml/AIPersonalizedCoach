'use client';

import { useMemo, useState } from 'react';

import {
  Badge,
  Card,
  CardHead,
  EmptyState,
  StatusPill,
  cx,
} from '@/components/ui/primitives';
import { CONCEPT_METHOD_STYLE, conceptLabel } from '@/lib/presentation';
import type {
  GenerateWorkoutResponse,
  GraphTraversal,
  MemberTrajectory,
} from '@/lib/types';
import { LlmBoundary } from './LlmBoundary';
import { LongitudinalContext } from './LongitudinalContext';
import { GroundingDetail } from './OntologyGrounding';
import { DecisionPaths } from './DecisionPaths';
import { PipelineFlow } from './PipelineFlow';
import { CONSTRAINT_LABEL, CONSTRAINT_TONE } from './TraversalPath';
import { TraversalReplay } from './TraversalReplay';

type TabId = 'concepts' | 'traversal' | 'replay' | 'summary';

type DecisionGroups = {
  excluded: GraphTraversal[];
  downranked: GraphTraversal[];
  allowed: GraphTraversal[];
};

interface DecisionGroup {
  key: string;
  label: string;
  status: 'excluded' | 'cautioned' | 'safe';
  items: GraphTraversal[];
}

function decisionGroups(grouped: DecisionGroups): DecisionGroup[] {
  return [
    { key: 'excluded', label: 'Excluded', status: 'excluded', items: grouped.excluded },
    {
      key: 'downranked',
      label: 'Down-ranked',
      status: 'cautioned',
      items: grouped.downranked,
    },
    {
      key: 'allowed',
      label: 'Allowed with evidence',
      status: 'safe',
      items: grouped.allowed,
    },
  ];
}

/**
 * The graph reasoning surface.
 *
 * Everything rendered here comes from `graph_reasoning` on the workout
 * response, which the backend builds from the same `SafetyDecision` objects the
 * post-generation gate uses. Selection is shared with the Safety & Provenance
 * Inspector, so clicking a row in either place moves both.
 */
export function GraphReasoningPanel({
  result,
  selectedExerciseId,
  onSelect,
}: {
  result: GenerateWorkoutResponse | null;
  selectedExerciseId: string | null;
  onSelect: (exerciseId: string) => void;
}) {
  const [tab, setTab] = useState<TabId>('traversal');
  const reasoning = result?.graph_reasoning ?? null;

  const byExercise = useMemo(() => {
    const map = new Map<string, GraphTraversal[]>();
    for (const traversal of reasoning?.traversals ?? []) {
      const list = map.get(traversal.exercise_id) ?? [];
      list.push(traversal);
      map.set(traversal.exercise_id, list);
    }
    return map;
  }, [reasoning]);

  const grouped = useMemo(() => {
    const excluded: GraphTraversal[] = [];
    const downranked: GraphTraversal[] = [];
    const allowed: GraphTraversal[] = [];
    for (const [, list] of byExercise) {
      const first = list[0];
      if (first.decision === 'excluded') excluded.push(first);
      else if (first.decision === 'downranked') downranked.push(first);
      else allowed.push(first);
    }
    const byName = (a: GraphTraversal, b: GraphTraversal) =>
      a.exercise_name.localeCompare(b.exercise_name);
    return {
      excluded: excluded.sort(byName),
      downranked: downranked.sort(byName),
      allowed: allowed.sort(byName),
    };
  }, [byExercise]);

  // Graceful fallback: an older backend simply omits the field.
  if (!result) return null;
  if (!reasoning) {
    return (
      <Card id="graph-reasoning">
        <CardHead title="Graph reasoning" />
        <EmptyState
          title="Graph reasoning not available"
          body="This response predates the graph-trace field. The Safety & Provenance inspector below still shows the evidence behind every decision."
        />
      </Card>
    );
  }

  const selected =
    (selectedExerciseId ? byExercise.get(selectedExerciseId) : undefined) ??
    byExercise.get(grouped.excluded[0]?.exercise_id ?? '') ??
    [];

  const tabs: Array<{ id: TabId; label: string; count?: number }> = [
    { id: 'concepts', label: 'Prompt concepts', count: reasoning.prompt_concepts.length },
    { id: 'traversal', label: 'Traversal', count: reasoning.summary.traversal_count },
    { id: 'replay', label: 'Step-by-step replay' },
    { id: 'summary', label: 'Decision summary' },
  ];

  return (
    <Card id="graph-reasoning">
      <CardHead
        title="Graph reasoning"
        right={
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone="graph">
              {reasoning.summary.traversal_count} traversals ·{' '}
              {reasoning.summary.exercises_with_evidence} exercises
            </Badge>
            <Badge tone="neutral" title="Graph store that served these traversals">
              graph.{reasoning.graph_backend}
            </Badge>
          </div>
        }
      />

      <div role="tablist" aria-label="Graph reasoning" className="flex gap-1 border-b border-ink-200 px-5 pt-2.5">
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`graph-tab-${item.id}`}
            aria-selected={tab === item.id}
            aria-controls={`graph-panel-${item.id}`}
            onClick={() => setTab(item.id)}
            className={cx(
              '-mb-px border-b-2 px-3 py-2 text-2xs font-semibold transition-colors',
              tab === item.id
                ? 'border-graph-600 text-graph-800'
                : 'border-transparent text-ink-500 hover:text-ink-700',
            )}
          >
            {item.label}
            {item.count != null ? (
              <span
                className={cx(
                  'ml-1.5 rounded-full px-1.5 py-px text-[9.5px]',
                  tab === item.id ? 'bg-graph-100 text-graph-700' : 'bg-ink-100 text-ink-500',
                )}
              >
                {item.count}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`graph-panel-${tab}`} aria-labelledby={`graph-tab-${tab}`}>
        {tab === 'concepts' ? <ConceptsTab reasoning={reasoning} /> : null}
        {tab === 'traversal' ? (
          <TraversalTab
            grouped={grouped}
            selected={selected}
            selectedId={selected[0]?.exercise_id ?? null}
            onSelect={onSelect}
          />
        ) : null}
        {tab === 'replay' ? (
          <ReplayTab
            grouped={grouped}
            selected={selected}
            selectedId={selected[0]?.exercise_id ?? null}
            onSelect={onSelect}
          />
        ) : null}
        {tab === 'summary' ? (
          <SummaryTab
            reasoning={reasoning}
            trajectory={result.trajectory ?? null}
            timings={result.timings_ms}
          />
        ) : null}
      </div>
    </Card>
  );
}

/* ------------------------------- concepts ------------------------------- */

function ConceptsTab({
  reasoning,
}: {
  reasoning: NonNullable<GenerateWorkoutResponse['graph_reasoning']>;
}) {
  return (
    <div className="px-5 py-4">
      <p className="mb-3 text-2xs text-ink-500">
        The coach&apos;s wording, canonicalised onto graph concepts before any
        traversal ran. Nothing below this step is guessed — an unresolved phrase
        is reported, never forced onto a concept. Where a concept also carries a
        verified published mapping, it is shown; the local ID stays the one this
        system reasons on.
      </p>

      <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {reasoning.prompt_concepts.map((concept) => {
          const style = CONCEPT_METHOD_STYLE[concept.method];
          return (
            <li
              key={`${concept.source_text}-${concept.canonical_id}`}
              className={cx(
                'rounded-xl border p-3',
                concept.resolved
                  ? 'border-ink-200 bg-white'
                  : 'border-dashed border-danger-300 bg-danger-50',
              )}
            >
              <div className="text-xs font-semibold text-navy-900">
                “{concept.source_text}”
              </div>

              <div className="my-1.5 flex items-center gap-1.5">
                <svg
                  className="h-3 w-3 text-ink-300"
                  viewBox="0 0 12 12"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  aria-hidden
                >
                  <path d="M6 1v10M3 8l3 3 3-3" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span
                  className={cx(
                    'rounded px-1.5 py-px text-[9.5px] font-semibold ring-1 ring-inset',
                    style.className,
                  )}
                >
                  {concept.method}
                </span>
                <span className="font-mono text-[9.5px] text-ink-500">
                  {concept.confidence.toFixed(2)}
                </span>
              </div>

              {concept.resolved ? (
                <div>
                  <div className="text-2xs font-medium text-graph-800">
                    {concept.label}
                  </div>
                  <div className="font-mono text-[9.5px] text-ink-400">
                    {conceptLabel(concept.canonical_id)}
                  </div>
                  {/* Rendered only where a verified published mapping exists.
                      Equipment and movement families have none, and showing
                      nothing is the honest state for them. */}
                  {concept.grounding ? (
                    <GroundingDetail grounding={concept.grounding} />
                  ) : null}
                </div>
              ) : (
                <div className="text-2xs font-medium text-danger-700">
                  Unresolved — no safety rule applied
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/* ------------------------------- traversal ------------------------------ */

function TraversalTab({
  grouped,
  selected,
  selectedId,
  onSelect,
}: {
  grouped: DecisionGroups;
  selected: GraphTraversal[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)]">
      <DecisionList
        groups={decisionGroups(grouped)}
        selectedId={selectedId}
        onSelect={onSelect}
      />

      <div className="scrollbar-slim max-h-[460px] overflow-y-auto bg-ink-50/50 p-4">
        {selected.length ? (
          <section aria-label="Graph traversal detail">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold tracking-tight text-navy-900">
                {selected[0].exercise_name}
              </h3>
              <StatusPill
                status={
                  selected[0].decision === 'excluded'
                    ? 'excluded'
                    : selected[0].decision === 'downranked'
                      ? 'cautioned'
                      : 'safe'
                }
              />
            </div>

            <div className="mb-3 flex flex-wrap gap-1.5">
              {Array.from(
                new Set(selected.map((t) => t.constraint_type)),
              ).map((constraint) => (
                <Badge key={constraint} tone={CONSTRAINT_TONE[constraint]}>
                  {CONSTRAINT_LABEL[constraint]}
                </Badge>
              ))}
            </div>

            <ul className="mb-3 space-y-1">
              {Array.from(new Set(selected.map((t) => t.reason))).map((reason) => (
                <li key={reason} className="text-2xs leading-relaxed text-ink-600">
                  {reason}
                </li>
              ))}
            </ul>

            <DecisionPaths traversals={selected} />

            <p className="mt-3 border-t border-ink-200 pt-2.5 text-[10.5px] text-ink-500">
              Source: deterministic knowledge-graph traversal. These paths were
              produced by the safety engine before the model was called — the LLM
              did not generate them.
            </p>
          </section>
        ) : (
          <EmptyState
            title="Select a decision"
            body="Choose an exercise to see the exact nodes and relationships the safety engine walked."
          />
        )}
      </div>
    </div>
  );
}

/** Shared by the Traversal and Replay tabs so selection behaves identically. */
function DecisionList({
  groups,
  selectedId,
  onSelect,
}: {
  groups: DecisionGroup[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="scrollbar-slim max-h-[460px] overflow-y-auto border-b border-ink-200 lg:border-b-0 lg:border-r">
      {groups.map((group) =>
        group.items.length ? (
          <div key={group.key}>
            <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-ink-200 bg-ink-50 px-4 py-1.5">
              <StatusPill status={group.status} />
              <span className="text-[10px] text-ink-500">{group.items.length}</span>
            </div>
            <ul>
              {group.items.map((traversal) => {
                const isSelected = selectedId === traversal.exercise_id;
                return (
                  <li key={traversal.exercise_id}>
                    <button
                      type="button"
                      onClick={() => onSelect(traversal.exercise_id)}
                      className={cx(
                        'flex w-full items-start justify-between gap-2 border-b border-ink-100 px-4 py-2 text-left transition-colors',
                        isSelected ? 'bg-brand-50' : 'hover:bg-ink-50',
                      )}
                    >
                      <span
                        className={cx(
                          'text-2xs font-medium',
                          isSelected ? 'text-brand-800' : 'text-navy-900',
                        )}
                      >
                        {traversal.exercise_name}
                      </span>
                      <Badge tone={CONSTRAINT_TONE[traversal.constraint_type]}>
                        {CONSTRAINT_LABEL[traversal.constraint_type]}
                      </Badge>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null,
      )}
    </div>
  );
}

/* -------------------------------- replay -------------------------------- */

function ReplayTab({
  grouped,
  selected,
  selectedId,
  onSelect,
}: {
  grouped: DecisionGroups;
  selected: GraphTraversal[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)]">
      <DecisionList
        groups={decisionGroups(grouped)}
        selectedId={selectedId}
        onSelect={onSelect}
      />

      <div className="scrollbar-slim max-h-[460px] overflow-y-auto bg-ink-50/50 p-4">
        {selected.length ? (
          <TraversalReplay
            traversals={selected}
            exerciseName={selected[0].exercise_name}
          />
        ) : (
          <EmptyState
            title="Select a decision to replay"
            body="Step through the exact hops the safety engine walked to reach it."
          />
        )}
      </div>
    </div>
  );
}

/* -------------------------------- summary ------------------------------- */

function SummaryTab({
  reasoning,
  trajectory,
  timings,
}: {
  reasoning: NonNullable<GenerateWorkoutResponse['graph_reasoning']>;
  trajectory: MemberTrajectory | null;
  timings?: Record<string, number>;
}) {
  const { summary } = reasoning;

  const stages = [
    { label: 'Coach prompt', value: '1 request' },
    { label: 'Concepts resolved', value: `${summary.concepts_resolved}` },
    { label: 'Catalog exercises', value: `${summary.catalog_count}` },
    { label: 'Graph traversals', value: `${summary.traversal_count}` },
    { label: 'Hard excluded', value: `${summary.excluded_count}` },
    { label: 'Down-ranked', value: `${summary.downranked_count}` },
    { label: 'Eligible after hard filters', value: `${summary.eligible_count}` },
    { label: 'Selected in plan', value: `${summary.in_plan_count}` },
  ];

  return (
    <div className="space-y-4 px-5 py-4">
      <LlmBoundary summary={summary} />

      <PipelineFlow summary={summary} trajectory={trajectory} timings={timings} />

      {/* Rendered only when the backend actually ran a longitudinal analysis. */}
      {trajectory ? <LongitudinalContext trajectory={trajectory} /> : null}

      <div>
        <div className="label-caps mb-2">Prompt to plan</div>
        <ol className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-4">
          {stages.map((stage, index) => (
            <li
              key={stage.label}
              className="flex items-center justify-between rounded-lg border border-ink-200 bg-white px-3 py-2"
            >
              <span className="flex items-center gap-1.5 text-2xs text-ink-600">
                <span className="font-mono text-[9px] text-ink-300">{index + 1}</span>
                {stage.label}
              </span>
              <span className="text-xs font-semibold text-navy-900">{stage.value}</span>
            </li>
          ))}
        </ol>
        <p className="mt-1.5 text-[10.5px] text-ink-500">{summary.note}</p>
      </div>

      {summary.counts_by_constraint.length ? (
        <div>
          <div className="label-caps mb-2">Rule categories that fired</div>
          <ul className="space-y-1.5">
            {summary.counts_by_constraint.map((row) => (
              <li key={row.constraint_type} className="flex items-center gap-2">
                <span className="w-40 shrink-0 text-2xs text-ink-600">{row.label}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-ink-100">
                  <div
                    className="h-full rounded-full bg-graph-400"
                    style={{
                      width: `${Math.min(100, (row.exercises_affected / Math.max(1, summary.catalog_count)) * 100)}%`,
                    }}
                  />
                </div>
                <span className="w-28 shrink-0 text-right text-[10.5px] text-ink-500">
                  {row.exercises_affected} exercises
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
