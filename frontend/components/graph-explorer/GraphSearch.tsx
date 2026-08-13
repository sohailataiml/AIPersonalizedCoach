'use client';

import { useEffect, useState } from 'react';

import { Badge, cx } from '@/components/ui/primitives';
import type { GraphSearchHit } from '@/lib/types';

/**
 * Graph search.
 *
 * Deliberately *not* concept resolution. The resolver must choose exactly one
 * canonical concept and refuse when unsure, because a wrong choice applies a
 * wrong safety rule. Search has no such consequence, so it shows several
 * candidates and lets a human pick — and never auto-selects on their behalf.
 */
export function GraphSearch({
  value,
  onChange,
  hits,
  isLoading,
  selectedId,
  onSelect,
  truncated,
}: {
  value: string;
  onChange: (query: string) => void;
  hits: GraphSearchHit[];
  isLoading: boolean;
  selectedId: string | null;
  onSelect: (hit: GraphSearchHit) => void;
  truncated: boolean;
}) {
  const [draft, setDraft] = useState(value);

  // Debounced so typing does not fire a request per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => onChange(draft.trim()), 200);
    return () => clearTimeout(timer);
  }, [draft, onChange]);

  return (
    <div>
      <label className="sr-only" htmlFor="graph-search">
        Search knowledge graph
      </label>
      <input
        id="graph-search"
        type="search"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        placeholder="Search knowledge graph… e.g. knee, PFPS, Static Jump, dumbbell"
        className={cx(
          'w-full rounded-lg border border-ink-200 px-3 py-2 text-2xs',
          'placeholder:text-ink-400 focus:border-brand-400 focus:outline-none',
        )}
      />

      <div className="mt-2 max-h-[220px] overflow-y-auto scrollbar-slim">
        {isLoading ? (
          <p className="px-1 text-[10px] text-ink-400">Searching…</p>
        ) : !draft.trim() ? (
          <p className="px-1 text-[10px] text-ink-400">
            Search by label, canonical id or alias.
          </p>
        ) : hits.length === 0 ? (
          <p className="px-1 text-[10px] text-ink-500">
            No nodes match “{draft.trim()}”. Nothing was auto-selected.
          </p>
        ) : (
          <ul aria-label="Search results">
            {hits.map((hit) => (
              <li key={hit.id}>
                <button
                  type="button"
                  onClick={() => onSelect(hit)}
                  aria-label={`Open ${hit.label}`}
                  aria-current={selectedId === hit.id ? 'true' : undefined}
                  className={cx(
                    'flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left',
                    selectedId === hit.id ? 'bg-brand-50' : 'hover:bg-ink-50',
                  )}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-2xs font-medium text-navy-900">
                      {hit.label}
                    </span>
                    <span className="block truncate font-mono text-[9px] text-ink-400">
                      {hit.canonical_id ?? hit.id}
                    </span>
                  </span>
                  <Badge tone="neutral">{hit.kind}</Badge>
                  <span className="w-8 shrink-0 text-right text-[9px] text-ink-400">
                    {hit.match}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {truncated ? (
          <p className="px-1 pt-1 text-[9.5px] text-ink-400">
            More matches exist than are shown — refine the search.
          </p>
        ) : null}
      </div>
    </div>
  );
}
