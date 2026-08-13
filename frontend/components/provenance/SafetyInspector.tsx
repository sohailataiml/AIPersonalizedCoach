'use client';

import { useEffect, useMemo, useState } from 'react';

import {
  Badge,
  Card,
  CardHead,
  EmptyState,
  StatusPill,
  cx,
} from '@/components/ui/primitives';
import { RULE_LABEL, ruleLabel, statusOf } from '@/lib/presentation';
import type {
  GenerateWorkoutResponse,
  GraphTraversal,
  ProvenanceItem,
} from '@/lib/types';
import { TraversalPath } from '@/components/graph/TraversalPath';
import { ProvenanceGraph } from './ProvenanceGraph';
import { SafetyDecisionTable } from './SafetyDecisionTable';

type TabId = 'filtered' | 'downranked' | 'in-plan' | 'evidence';

export function SafetyInspector({
  result,
  selectedExerciseId,
  onSelect,
}: {
  result: GenerateWorkoutResponse | null;
  selectedExerciseId: string | null;
  onSelect: (exerciseId: string) => void;
}) {
  const traversalsById = useMemo(() => {
    const map = new Map<string, GraphTraversal[]>();
    for (const traversal of result?.graph_reasoning?.traversals ?? []) {
      const list = map.get(traversal.exercise_id) ?? [];
      list.push(traversal);
      map.set(traversal.exercise_id, list);
    }
    return map;
  }, [result]);
  const [tab, setTab] = useState<TabId>('filtered');

  const groups = useMemo(() => {
    const filtered = (result?.filtered_exercises ?? []).filter(
      (item) => item.decision === 'filtered',
    );
    const inPlan = result?.provenance ?? [];

    // A down-ranked exercise can still be selected for the plan, in which case
    // the backend reports it under `provenance` rather than
    // `filtered_exercises`. Including both keeps this tab's count equal to
    // `safety.downranked` instead of silently showing only the unused ones.
    const downranked = [
      ...(result?.filtered_exercises ?? []).filter(
        (item) => item.decision === 'downranked',
      ),
      ...inPlan.filter((item) => statusOf(item) === 'cautioned'),
    ];

    return { filtered, downranked, inPlan };
  }, [result]);

  const activeItems =
    tab === 'filtered'
      ? groups.filtered
      : tab === 'downranked'
        ? groups.downranked
        : tab === 'in-plan'
          ? groups.inPlan
          : [];

  const allItems = useMemo(
    () => [...groups.filtered, ...groups.downranked, ...groups.inPlan],
    [groups],
  );

  const selected =
    allItems.find((item) => item.exercise_id === selectedExerciseId) ??
    activeItems[0] ??
    null;

  // Keep a sensible selection when the tab changes or a new plan arrives.
  useEffect(() => {
    if (!activeItems.length) return;
    const stillVisible = activeItems.some(
      (item) => item.exercise_id === selectedExerciseId,
    );
    if (!stillVisible) onSelect(activeItems[0].exercise_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, result?.request_id]);

  if (!result) {
    return (
      <Card id="safety-inspector">
        <CardHead step={3} title="Safety & provenance inspector" />
        <EmptyState
          title="Nothing to inspect yet"
          body="Generate a workout to see the graph paths behind every include, down-rank and removal."
        />
      </Card>
    );
  }

  const tabs: Array<{ id: TabId; label: string; count: number }> = [
    { id: 'filtered', label: 'Filtered out', count: groups.filtered.length },
    { id: 'downranked', label: 'Down-ranked', count: groups.downranked.length },
    { id: 'in-plan', label: 'In the plan', count: groups.inPlan.length },
    { id: 'evidence', label: 'Member evidence', count: result.member_facts.length },
  ];

  return (
    <Card id="safety-inspector">
      <CardHead
        step={3}
        title="Safety & provenance inspector"
        right={
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone="danger">{groups.filtered.length} removed</Badge>
            <Badge tone="caution">{groups.downranked.length} down-ranked</Badge>
            <Badge tone="safe">{result.safety.in_plan} in plan</Badge>
          </div>
        }
      />

      <div role="tablist" aria-label="Safety decisions" className="flex gap-1 border-b border-ink-200 px-5 pt-2.5">
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`tab-${item.id}`}
            aria-selected={tab === item.id}
            aria-controls={`panel-${item.id}`}
            onClick={() => setTab(item.id)}
            className={cx(
              '-mb-px border-b-2 px-3 py-2 text-2xs font-semibold transition-colors',
              tab === item.id
                ? 'border-navy-800 text-navy-900'
                : 'border-transparent text-ink-500 hover:text-ink-700',
            )}
          >
            {item.label}
            <span
              className={cx(
                'ml-1.5 rounded-full px-1.5 py-px text-[9.5px]',
                tab === item.id ? 'bg-navy-100 text-navy-700' : 'bg-ink-100 text-ink-500',
              )}
            >
              {item.count}
            </span>
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id={`panel-${tab}`}
        aria-labelledby={`tab-${tab}`}
        className="grid gap-0 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]"
      >
        {tab === 'evidence' ? (
          <MemberEvidence result={result} />
        ) : (
          <>
            <SafetyDecisionTableLazy
              items={activeItems}
              selectedId={selected?.exercise_id ?? null}
              onSelect={onSelect}
              tab={tab}
            />
            <ProvenancePanel
              item={selected}
              traversals={
                selected ? (traversalsById.get(selected.exercise_id) ?? []) : []
              }
            />
          </>
        )}
      </div>
    </Card>
  );
}

function SafetyDecisionTableLazy({
  items,
  selectedId,
  onSelect,
  tab,
}: {
  items: ProvenanceItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  tab: TabId;
}) {
  const empty =
    tab === 'filtered'
      ? 'Nothing was removed for this request.'
      : tab === 'downranked'
        ? 'Nothing was down-ranked for this request.'
        : 'No exercises in the plan.';

  return (
    <div className="border-b border-ink-200 lg:border-b-0 lg:border-r">
      <SafetyDecisionTable
        items={items}
        selectedId={selectedId}
        onSelect={onSelect}
        emptyLabel={empty}
      />
    </div>
  );
}

function ProvenancePanel({
  item,
  traversals,
}: {
  item: ProvenanceItem | null;
  traversals: GraphTraversal[];
}) {
  if (!item) {
    return (
      <div className="p-5">
        <EmptyState
          title="Select an exercise"
          body="Choose a row to see the graph paths that produced its decision."
        />
      </div>
    );
  }

  const status = statusOf(item);
  const contraindications = item.rule_ids.filter((rule) =>
    rule.startsWith('injury_'),
  ).length;
  const preferences = item.rule_ids.filter((rule) =>
    rule.startsWith('preference_'),
  ).length;

  return (
    <section
      aria-label="Provenance detail"
      className="scrollbar-slim max-h-[420px] overflow-y-auto bg-ink-50/50 p-5"
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-semibold tracking-tight text-navy-900">
          {item.exercise}
        </h3>
        <StatusPill status={status} />
      </div>

      <div className="mt-3">
        <div className="label-caps mb-1">Reason</div>
        <ul className="space-y-1">
          {item.reasons.map((reason, index) => (
            <li key={index} className="flex gap-1.5 text-2xs leading-relaxed text-ink-700">
              <span aria-hidden className="text-ink-300">
                •
              </span>
              <span>{reason}</span>
            </li>
          ))}
        </ul>
      </div>

      {item.rule_ids.length ? (
        <div className="mt-3 flex flex-wrap gap-1">
          {item.rule_ids.map((rule) => (
            <Badge
              key={rule}
              tone={rule === 'preference_dislike' ? 'neutral' : 'caution'}
              title={rule}
            >
              {ruleLabel(rule)}
            </Badge>
          ))}
        </div>
      ) : null}

      {traversals.length ? (
        <div className="mt-4">
          <div className="label-caps mb-2">Graph path</div>
          <div className="space-y-2">
            {traversals.map((traversal) => (
              <TraversalPath key={traversal.id} traversal={traversal} />
            ))}
          </div>
        </div>
      ) : item.evidence.length ? (
        <div className="mt-4">
          <div className="label-caps mb-2">Graph path</div>
          <div className="flex flex-wrap gap-5">
            {item.evidence.map((path, index) => (
              <ProvenanceGraph key={index} path={path} />
            ))}
          </div>
        </div>
      ) : (
        <p className="mt-4 rounded-lg border border-ink-200 bg-white px-3 py-2 text-2xs text-ink-500">
          No traversal was needed — this exercise triggered no graph rule.
        </p>
      )}

      <div className="mt-4 border-t border-ink-200 pt-3">
        <div className="label-caps mb-1">Evidence</div>
        <p className="text-2xs text-ink-600">
          {item.evidence.length} graph path{item.evidence.length === 1 ? '' : 's'} ·{' '}
          {contraindications} contraindication{contraindications === 1 ? '' : 's'} ·{' '}
          {preferences} preference{preferences === 1 ? '' : 's'}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <Badge tone={item.decision_source === 'knowledge_graph' ? 'safe' : 'caution'}>
            ✓{' '}
            {item.decision_source === 'knowledge_graph'
              ? 'Knowledge graph'
              : item.decision_source === 'post_validation'
                ? 'Post-generation gate'
                : 'LLM composition'}
          </Badge>
          <Badge tone="neutral">✕ LLM did not decide safety</Badge>
        </div>
      </div>
    </section>
  );
}

function MemberEvidence({ result }: { result: GenerateWorkoutResponse }) {
  return (
    <div className="col-span-full p-5">
      <div className="grid gap-5 md:grid-cols-2">
        <div>
          <div className="label-caps mb-2">Member facts used</div>
          <ul className="space-y-1.5">
            {result.member_facts.map((fact, index) => (
              <li key={index} className="flex gap-2 text-2xs leading-relaxed text-ink-700">
                <span aria-hidden className="text-brand-500">
                  ▸
                </span>
                {fact}
              </li>
            ))}
          </ul>
        </div>

        <div>
          <div className="label-caps mb-2">Rules applied in this request</div>
          <ul className="flex flex-wrap gap-1.5">
            {Array.from(
              new Set(
                [...result.filtered_exercises, ...result.provenance].flatMap(
                  (item) => item.rule_ids,
                ),
              ),
            ).map((rule) => (
              <li key={rule}>
                <Badge tone="neutral" title={rule}>
                  {RULE_LABEL[rule] ?? rule}
                </Badge>
              </li>
            ))}
          </ul>

          {result.post_validation.rejected.length ? (
            <div className="mt-4">
              <div className="label-caps mb-2">Post-generation rejections</div>
              <ul className="space-y-1.5">
                {result.post_validation.rejected.map((rejection, index) => (
                  <li
                    key={index}
                    className="rounded-lg border border-danger-200 bg-danger-50 px-2.5 py-1.5
                               text-2xs text-danger-700"
                  >
                    <span className="font-semibold">{rejection.name}</span> —{' '}
                    {rejection.reason}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
