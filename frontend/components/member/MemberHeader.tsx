'use client';

import { Badge, Button } from '@/components/ui/primitives';
import { initialsOf } from '@/lib/presentation';
import type { MemberSummary } from '@/lib/types';

/**
 * Identity strip. Everything shown is a real field from /api/members/{id};
 * there is no avatar in the supplied data, so we render initials rather than
 * inventing a photo.
 */
export function MemberHeader({
  member,
  lastUpdatedLabel,
  onNewWorkout,
  isBusy,
}: {
  member: MemberSummary;
  lastUpdatedLabel?: string;
  onNewWorkout?: () => void;
  isBusy?: boolean;
}) {
  const subtitle = [
    member.age ? String(member.age) : null,
    member.tier,
    member.primary_goal,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex items-center gap-3.5">
        <div
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full
                     bg-gradient-to-br from-navy-700 to-navy-900 text-sm font-semibold text-white"
          aria-hidden
        >
          {initialsOf(member.name)}
        </div>

        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold tracking-tight text-navy-900">
              {member.name}
            </h1>
            <Badge tone="safe">Active</Badge>
            {member.brief_date ? (
              <Badge tone="brand">Brief · {member.brief_date}</Badge>
            ) : null}
          </div>
          <p className="mt-0.5 text-xs text-ink-500">{subtitle}</p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {lastUpdatedLabel ? (
          <span className="hidden text-2xs text-ink-400 sm:inline">
            Last updated {lastUpdatedLabel}
          </span>
        ) : null}
        <Button onClick={onNewWorkout} disabled={isBusy}>
          {isBusy ? 'Generating…' : 'New workout'}
        </Button>
      </div>
    </div>
  );
}
