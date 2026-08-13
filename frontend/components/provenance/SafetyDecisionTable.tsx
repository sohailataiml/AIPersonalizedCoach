'use client';

import { StatusPill, cx } from '@/components/ui/primitives';
import { statusOf, summarize } from '@/lib/presentation';
import type { ProvenanceItem } from '@/lib/types';

/**
 * The decision table. Rows are buttons so selection is keyboard-reachable, and
 * the selected row drives the provenance panel beside it.
 */
export function SafetyDecisionTable({
  items,
  selectedId,
  onSelect,
  emptyLabel,
}: {
  items: ProvenanceItem[];
  selectedId: string | null;
  onSelect: (exerciseId: string) => void;
  emptyLabel: string;
}) {
  if (!items.length) {
    return (
      <div className="px-4 py-10 text-center text-2xs text-ink-500">{emptyLabel}</div>
    );
  }

  return (
    <div className="scrollbar-slim max-h-[420px] overflow-y-auto">
      <table className="w-full border-collapse text-left">
        <thead className="sticky top-0 z-10 bg-white">
          <tr className="border-b border-ink-200">
            <th scope="col" className="label-caps px-4 py-2 font-semibold">
              Exercise
            </th>
            <th scope="col" className="label-caps px-2 py-2 font-semibold">
              Status
            </th>
            <th scope="col" className="label-caps px-4 py-2 font-semibold">
              Why it is safe / excluded
            </th>
          </tr>
        </thead>

        <tbody>
          {items.map((item) => {
            const status = statusOf(item);
            const selected = selectedId === item.exercise_id;
            return (
              <tr
                key={item.exercise_id}
                className={cx(
                  'cursor-pointer border-b border-ink-100 transition-colors',
                  selected ? 'bg-brand-50' : 'hover:bg-ink-50',
                )}
                onClick={() => onSelect(item.exercise_id)}
                aria-selected={selected}
              >
                <td className="px-4 py-2 align-top">
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      onSelect(item.exercise_id);
                    }}
                    className={cx(
                      'text-left text-2xs font-semibold',
                      selected ? 'text-brand-800' : 'text-navy-900 hover:text-brand-700',
                    )}
                  >
                    {item.exercise}
                  </button>
                </td>
                <td className="px-2 py-2 align-top">
                  <StatusPill status={status} />
                </td>
                <td className="px-4 py-2 align-top text-2xs leading-relaxed text-ink-600">
                  {summarize(item)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
