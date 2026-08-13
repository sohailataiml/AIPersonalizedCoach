'use client';

import type { Injury } from '@/lib/types';

/**
 * Verbatim clinical note from the member record.
 *
 * Rendered as-is with no paraphrasing or inference. The contraindications this
 * note describes are what the graph turned into CONTRAINDICATES edges, so
 * showing it unaltered lets a coach check the system's reading against the
 * source.
 */
export function ClinicalNoteBanner({ injury }: { injury: Injury | undefined }) {
  if (!injury?.notes) return null;

  return (
    <div
      role="note"
      className="flex items-start gap-2.5 rounded-card border border-caution-200
                 bg-caution-50 px-4 py-2.5"
    >
      <span
        aria-hidden
        className="mt-px flex h-4 w-4 shrink-0 items-center justify-center rounded-full
                   bg-caution-500 text-[10px] font-bold text-white"
      >
        !
      </span>
      <p className="text-2xs leading-relaxed text-caution-800">
        <span className="font-semibold">Clinical note: </span>
        {injury.notes}
      </p>
    </div>
  );
}
