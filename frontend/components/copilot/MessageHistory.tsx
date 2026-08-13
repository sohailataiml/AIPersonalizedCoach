'use client';

import { cx } from '@/components/ui/primitives';
import type { MemberHistory } from '@/lib/types';

/**
 * Recent coach/member conversation from the member graph.
 *
 * Attachments are rendered as a metadata row using the supplied caption. The
 * synthetic data contains no actual image bytes, so we show what is recorded
 * rather than inventing a picture.
 */
export function MessageHistory({ history }: { history?: MemberHistory }) {
  const messages = [...(history?.chat ?? [])].sort((a, b) =>
    b.ts.localeCompare(a.ts),
  );

  if (!messages.length) return null;

  return (
    <section aria-label="Recent messages" className="px-5 py-3.5">
      <div className="label-caps mb-2">Recent coach ↔ member messages</div>

      <ul className="space-y-2">
        {messages.map((message, index) => {
          const isCoach = message.from === 'coach';
          return (
            <li
              key={index}
              className={cx(
                'rounded-xl border px-3 py-2',
                isCoach
                  ? 'ml-5 border-brand-200 bg-brand-50'
                  : 'mr-5 border-ink-200 bg-white',
              )}
            >
              <div className="mb-0.5 flex items-center gap-1.5">
                <span
                  className={cx(
                    'text-[9.5px] font-semibold uppercase tracking-[0.08em]',
                    isCoach ? 'text-brand-700' : 'text-ink-500',
                  )}
                >
                  {message.from}
                </span>
                <span className="text-[9.5px] text-ink-400">
                  · {message.ts.slice(0, 10)}
                </span>
              </div>

              <p className="text-2xs leading-relaxed text-ink-700">{message.text}</p>

              {message.attachments.map((attachment, attachmentIndex) => (
                <div
                  key={attachmentIndex}
                  className="mt-1.5 flex items-center gap-1.5 rounded-lg border
                             border-dashed border-ink-300 bg-ink-50 px-2 py-1"
                >
                  <span aria-hidden className="text-[11px]">
                    🖼
                  </span>
                  <span className="text-[10px] text-ink-500">
                    {attachment.caption ?? attachment.type}
                  </span>
                </div>
              ))}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
