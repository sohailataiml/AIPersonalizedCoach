'use client';

import { useState } from 'react';
import { cx } from '@/components/ui/primitives';

/**
 * Navigation rail.
 *
 * The app is intentionally a single page for this assessment, so only Overview
 * is a live destination. The remaining items are presented as disabled with an
 * explicit "not in this build" affordance rather than as links that silently do
 * nothing - a dead nav item is worse than an honest one.
 */

type NavId =
  | 'overview'
  | 'workouts'
  | 'copilot'
  | 'system'
  | 'members'
  | 'insights'
  | 'library'
  | 'settings';

interface NavItem {
  id: NavId;
  label: string;
  icon: React.ReactNode;
  available: boolean;
  /** Scroll target within the single-page dashboard. */
  target?: string;
  /** A real route, for destinations outside the coach dashboard. */
  href?: string;
}

const ICON = 'h-4 w-4';

function Icon({ path, viewBox = '0 0 24 24' }: { path: string; viewBox?: string }) {
  return (
    <svg
      className={ICON}
      viewBox={viewBox}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={path} />
    </svg>
  );
}

const NAV: NavItem[] = [
  {
    id: 'overview',
    label: 'Overview',
    available: true,
    target: 'top',
    icon: <Icon path="M3 10.5 12 3l9 7.5M5 9.5V21h14V9.5" />,
  },
  {
    id: 'workouts',
    label: 'Workouts',
    available: true,
    target: 'workout-generator',
    icon: <Icon path="M6.5 6.5v11M17.5 6.5v11M3 9.5v5M21 9.5v5M6.5 12h11" />,
  },
  {
    id: 'copilot',
    label: 'Copilot',
    available: true,
    target: 'copilot',
    icon: <Icon path="M12 3a9 9 0 0 0-9 9v5a2 2 0 0 0 2 2h2v-6H5v-1a7 7 0 0 1 14 0v1h-2v6h2a2 2 0 0 0 2-2v-5a9 9 0 0 0-9-9Z" />,
  },
  {
    // A developer/operator surface, deliberately outside the coach's daily
    // workflow: "how is the system performing overall?" rather than "what
    // happened for this workout?".
    id: 'system',
    label: 'Quality',
    available: true,
    href: '/system',
    icon: <Icon path="M12 3l7.5 3.75v5.25c0 4.35-3.1 8.1-7.5 9-4.4-.9-7.5-4.65-7.5-9V6.75L12 3Zm-2.5 8.5 2 2 3.5-3.75" />,
  },
  {
    id: 'members',
    label: 'Members',
    available: false,
    icon: <Icon path="M16 19v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1M9.5 10a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM21 19v-1a4 4 0 0 0-3-3.87M16.5 3.13a4 4 0 0 1 0 7.75" />,
  },
  {
    id: 'insights',
    label: 'Insights',
    available: false,
    icon: <Icon path="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  },
  {
    id: 'library',
    label: 'Library',
    available: false,
    icon: <Icon path="M4 5.5A1.5 1.5 0 0 1 5.5 4H9v16H5.5A1.5 1.5 0 0 1 4 18.5v-13ZM9 4h5.5A1.5 1.5 0 0 1 16 5.5v13a1.5 1.5 0 0 1-1.5 1.5H9M18 6.5l2.5 12" />,
  },
  {
    id: 'settings',
    label: 'Settings',
    available: false,
    icon: <Icon path="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-2.9 1.2V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-2.9-1.2l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15H4.5a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.2-2.9l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 11.5 4.6V4.5a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 2.9 1.2l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 11h.1a2 2 0 1 1 0 4h-.1Z" />,
  },
];

export function Sidebar({
  coachName = 'Coach Olivia',
  current = 'overview',
}: {
  coachName?: string;
  /** The active destination when the rail is rendered on a real route. */
  current?: NavId;
}) {
  const [active, setActive] = useState<NavId>(current);

  function go(item: NavItem) {
    if (!item.available) return;
    if (item.href) {
      window.location.href = item.href;
      return;
    }
    setActive(item.id);
    if (item.target === 'top') {
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }
    document
      .getElementById(item.target ?? '')
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  return (
    <nav
      aria-label="Main navigation"
      className="sticky top-0 z-20 flex h-screen w-[68px] shrink-0 flex-col
                 items-center gap-1 border-r border-navy-800 bg-navy-950 py-4"
    >
      <div
        className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg
                   bg-gradient-to-br from-brand-500 to-graph-600 text-sm font-bold text-white"
        aria-label="Future"
      >
        F
      </div>

      <ul className="flex w-full flex-col items-center gap-0.5">
        {NAV.map((item) => {
          const isActive = active === item.id && item.available;
          return (
            <li key={item.id} className="w-full">
              <button
                type="button"
                onClick={() => go(item)}
                disabled={!item.available}
                aria-current={isActive ? 'page' : undefined}
                title={item.available ? item.label : `${item.label} — not in this build`}
                className={cx(
                  'group relative flex w-full flex-col items-center gap-1 rounded-lg px-1 py-2',
                  'transition-colors duration-150',
                  isActive
                    ? 'text-white'
                    : item.available
                      ? 'text-navy-300 hover:bg-navy-900 hover:text-white'
                      : 'cursor-not-allowed text-navy-500/70',
                )}
              >
                {isActive ? (
                  <span
                    aria-hidden
                    className="absolute left-0 top-1/2 h-7 w-0.5 -translate-y-1/2 rounded-r bg-brand-400"
                  />
                ) : null}
                <span
                  className={cx(
                    'flex h-8 w-8 items-center justify-center rounded-lg',
                    isActive && 'bg-navy-800',
                  )}
                >
                  {item.icon}
                </span>
                <span className="text-[9.5px] font-medium leading-none">{item.label}</span>
              </button>
            </li>
          );
        })}
      </ul>

      <div className="mt-auto flex flex-col items-center gap-1.5">
        <div
          className="flex h-8 w-8 items-center justify-center rounded-full
                     bg-navy-700 text-2xs font-semibold text-navy-100"
          title={coachName}
        >
          CO
        </div>
        <span className="max-w-[60px] text-center text-[9.5px] leading-tight text-navy-300">
          {coachName}
        </span>
      </div>
    </nav>
  );
}
