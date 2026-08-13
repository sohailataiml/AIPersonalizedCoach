'use client';

import { Badge, StatusPill, cx } from '@/components/ui/primitives';
import type { GraphTraversal, PathKind } from '@/lib/types';
import { TraversalPath } from './TraversalPath';

/**
 * A focused path viewer for one exercise's decision.
 *
 * Paths are grouped by `path_kind`, which the **backend** assigns from the node
 * kinds the safety engine recorded. The UI does not decide which path is the
 * member's and which is the exercise's — reconstructing that here from edge
 * names or reason text would be invented structure inside the panel meant to
 * prove nothing is invented.
 *
 * A traversal arriving without `path_kind` (older backend) falls into a single
 * "Evidence" group rather than being guessed at.
 */

const GROUPS: Array<{ kind: PathKind; title: string; hint: string }> = [
  {
    kind: 'member_context',
    title: 'Member path',
    hint: "Walked through this member's own graph",
  },
  {
    kind: 'anatomy_hierarchy',
    title: 'Anatomy path',
    hint: 'PART_OF closure — the injury sits below the joint the catalog annotates',
  },
  {
    kind: 'exercise_structure',
    title: 'Exercise path',
    hint: 'Walked through the exercise catalog',
  },
  {
    kind: 'set_operation',
    title: 'Deterministic facts',
    hint: 'No edge was walked — this is a set difference or a data gap',
  },
];

export function DecisionPaths({ traversals }: { traversals: GraphTraversal[] }) {
  if (!traversals.length) return null;

  const decision = traversals[0].decision;
  const ruleIds = Array.from(
    new Set(traversals.map((t) => t.rule_id).filter((id): id is string => Boolean(id))),
  );
  const ungrouped = traversals.filter((t) => !t.path_kind);

  return (
    <section aria-label="Decision paths" className="space-y-3">
      {GROUPS.map((group) => {
        const items = traversals.filter((t) => t.path_kind === group.kind);
        if (!items.length) return null;
        return (
          <div key={group.kind}>
            <div className="mb-1 flex flex-wrap items-baseline gap-2">
              <span className="label-caps">{group.title}</span>
              <span className="text-[9.5px] text-ink-400">{group.hint}</span>
            </div>
            <div className="space-y-2">
              {items.map((traversal) => (
                <TraversalPath key={traversal.id} traversal={traversal} />
              ))}
            </div>
          </div>
        );
      })}

      {ungrouped.length ? (
        <div>
          <div className="label-caps mb-1">Evidence</div>
          <div className="space-y-2">
            {ungrouped.map((traversal) => (
              <TraversalPath key={traversal.id} traversal={traversal} />
            ))}
          </div>
        </div>
      ) : null}

      <div className="rounded-lg border border-ink-200 bg-ink-50 p-2.5">
        <div className="mb-1.5 flex items-center gap-2">
          <span className="label-caps">Decision</span>
          <StatusPill
            status={
              decision === 'excluded'
                ? 'excluded'
                : decision === 'downranked'
                  ? 'cautioned'
                  : 'safe'
            }
          />
        </div>
        {ruleIds.length ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-[9.5px] text-ink-400">Rules:</span>
            {ruleIds.map((ruleId) => (
              <Badge key={ruleId} tone="neutral">
                <span className="font-mono text-[9.5px]">{ruleId}</span>
              </Badge>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}

export function pathKindCount(traversals: GraphTraversal[], kind: PathKind): number {
  return traversals.filter((t) => t.path_kind === kind).length;
}

export const PATH_KIND_TITLE: Record<PathKind, string> = GROUPS.reduce(
  (acc, group) => ({ ...acc, [group.kind]: group.title }),
  {} as Record<PathKind, string>,
);

export const decisionToneClass = (decision: GraphTraversal['decision']) =>
  cx(
    decision === 'excluded' && 'text-danger-700',
    decision === 'downranked' && 'text-caution-700',
    decision === 'allowed' && 'text-safe-700',
  );
