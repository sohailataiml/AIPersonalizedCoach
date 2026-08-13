'use client';

import { cx } from '@/components/ui/primitives';
import { CONCEPT_METHOD_STYLE, conceptLabel } from '@/lib/presentation';
import type { ResolvedConcept } from '@/lib/types';

/**
 * Shows how the coach's words became canonical graph concepts.
 *
 * This is the coach-facing proof that the system understood the request, so
 * each chip renders the source phrase, the canonical concept, and the pass that
 * matched it. Confidence is available on hover rather than on the chip, to keep
 * the row scannable. Unresolved phrases are shown too - never hidden - because
 * a silently dropped clinical phrase is the failure worth surfacing.
 */
export function ConceptResolution({
  resolved,
  unresolved,
}: {
  resolved: ResolvedConcept[];
  unresolved: ResolvedConcept[];
}) {
  if (!resolved.length && !unresolved.length) return null;

  return (
    <section aria-label="Concept resolution" className="px-5 py-3">
      <div className="label-caps mb-2">Concept resolution</div>

      <ul className="flex flex-wrap gap-1.5">
        {resolved.map((concept) => {
          const style = CONCEPT_METHOD_STYLE[concept.method];
          return (
            <li
              key={`${concept.source_text}-${concept.canonical_id}`}
              className="inline-flex items-center gap-1.5 rounded-lg border border-ink-200
                         bg-ink-50 py-1 pl-2 pr-1.5"
              title={`Confidence ${(concept.confidence * 100).toFixed(0)}%`}
            >
              <span className="text-2xs text-ink-600">“{concept.source_text}”</span>
              <span aria-hidden className="text-ink-300">
                →
              </span>
              <span className="font-mono text-[10.5px] font-medium text-navy-800">
                {conceptLabel(concept.canonical_id)}
              </span>
              <span
                className={cx(
                  'rounded px-1.5 py-px text-[9.5px] font-semibold ring-1 ring-inset',
                  style.className,
                )}
              >
                {style.label}
              </span>
            </li>
          );
        })}

        {unresolved.map((concept) => (
          <li
            key={`unresolved-${concept.source_text}`}
            title={`Best near-miss ${(concept.confidence * 100).toFixed(0)}% — below threshold, so not applied`}
            className="inline-flex items-center gap-1.5 rounded-lg border border-dashed
                       border-danger-300 bg-danger-50 py-1 pl-2 pr-1.5"
          >
            <span className="text-2xs text-danger-700">“{concept.source_text}”</span>
            <span
              className="rounded bg-danger-100 px-1.5 py-px text-[9.5px] font-semibold
                         text-danger-700 ring-1 ring-inset ring-danger-200"
            >
              unresolved
            </span>
          </li>
        ))}
      </ul>

      {unresolved.length ? (
        <p className="mt-1.5 text-[10.5px] text-ink-500">
          Unresolved phrases are reported rather than guessed — no safety rule was
          applied from them.
        </p>
      ) : null}
    </section>
  );
}
