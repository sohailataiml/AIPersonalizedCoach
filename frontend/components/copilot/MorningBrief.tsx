'use client';

import { Badge } from '@/components/ui/primitives';
import type { MemberSummary } from '@/lib/types';

/**
 * The coach's morning brief, rendered verbatim from the member's CoachBrief
 * node. Task types come from the data (`celebrate`, `review_risk`); we style
 * them but never rewrite the text.
 */
export function MorningBrief({ member }: { member: MemberSummary }) {
  if (!member.morning_tasks.length) return null;

  return (
    <section
      aria-label="Morning brief"
      className="border-b border-ink-200 px-5 py-3.5"
    >
      <div className="label-caps mb-2">
        Morning brief{member.brief_date ? ` · ${member.brief_date}` : ''}
      </div>

      <ul className="space-y-2">
        {member.morning_tasks.map((task, index) => (
          <li key={index} className="flex items-start gap-2">
            <Badge tone={task.type === 'celebrate' ? 'safe' : 'caution'}>
              {task.type === 'celebrate' ? 'celebrate' : 'review risk'}
            </Badge>
            <p className="min-w-0 flex-1 text-2xs leading-relaxed text-ink-700">
              {task.text}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}
