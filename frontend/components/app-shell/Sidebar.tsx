'use client';

import { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { cx } from '@/components/ui/primitives';

/**
 * Navigation rail.
 *
 * The coach dashboard is one page with in-page sections; Graph and Quality are
 * real routes. Items that do not exist in this build stay visibly disabled with
 * a "not in this build" title rather than rendering as links that silently do
 * nothing - a dead nav item is worse than an honest one.
 *
 * Two things here are less obvious than they look:
 *
 * **Scrolling alone is not feedback.** On an `xl` viewport the Workouts and
 * Copilot panels are siblings in the same grid row, so they share an
 * `offsetTop` and are usually both already on screen. `scrollIntoView` then
 * resolves to the same position for either one and the click reads as broken.
 * Each section therefore also receives focus, which moves the caret and paints
 * a ring on the panel you asked for - unambiguous even when nothing scrolls,
 * and the behaviour a screen reader needs regardless.
 *
 * **The highlight has to follow the page, not the last click.** Without a
 * scroll spy the rail keeps asserting whatever was clicked last, which is
 * wrong the moment the coach scrolls.
 */

type NavId =
  | 'overview'
  | 'workouts'
  | 'copilot'
  | 'graph'
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

/** Above this scroll offset the page counts as "at the top" for the spy. */
const TOP_THRESHOLD_PX = 120;

/** Focus target for Overview - the dashboard header. */
const OVERVIEW_ANCHOR_ID = 'overview';

/** The route that owns the in-page sections. */
const DASHBOARD_ROUTE = '/';

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
    // Read-only inspection of the application's own graph. Not a database
    // console - see components/graph-explorer.
    id: 'graph',
    label: 'Graph',
    available: true,
    href: '/graph',
    icon: <Icon path="M12 3.5a2 2 0 1 1 0 4 2 2 0 0 1 0-4ZM5 16.5a2 2 0 1 1 0 4 2 2 0 0 1 0-4ZM19 16.5a2 2 0 1 1 0 4 2 2 0 0 1 0-4ZM11 7.4 6 15m7-7.6 5 7.6M7 18.5h10" />,
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
  const router = useRouter();
  const pathname = usePathname();
  const [active, setActive] = useState<NavId>(current);

  // The rail is rendered on three routes; when the prop changes the highlight
  // has to follow it. `useState` only reads its argument once.
  useEffect(() => setActive(current), [current]);

  // Scroll spy, so the highlight reflects where the page actually is rather
  // than what was clicked last. Only runs where the in-page sections exist,
  // which keeps it inert on /graph and /system.
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return;

    const sections = NAV.filter((item) => item.target && item.target !== 'top')
      .map((item) => ({ id: item.id, el: document.getElementById(item.target as string) }))
      .filter((entry): entry is { id: NavId; el: HTMLElement } => entry.el !== null);
    if (!sections.length) return;

    const observer = new IntersectionObserver(
      (entries) => {
        // Near the top of the document "Overview" is the honest answer, even
        // though a section may technically still be intersecting.
        if (window.scrollY < TOP_THRESHOLD_PX) {
          setActive('overview');
          return;
        }
        const topmost = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (!topmost) return;
        const match = sections.find((section) => section.el === topmost.target);
        if (match) setActive(match.id);
      },
      { rootMargin: '-15% 0px -65% 0px', threshold: 0 },
    );
    sections.forEach((section) => observer.observe(section.el));

    const onScroll = () => {
      if (window.scrollY < TOP_THRESHOLD_PX) setActive('overview');
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();

    return () => {
      observer.disconnect();
      window.removeEventListener('scroll', onScroll);
    };
  }, []);

  function go(item: NavItem) {
    if (!item.available) return;

    // Client-side navigation: a full document load would throw away the React
    // Query cache and re-fetch member context for no reason.
    if (item.href) {
      router.push(item.href);
      return;
    }

    // The in-page sections belong to the dashboard. From /graph or /system
    // there is nothing to scroll to, so these have to be a real navigation
    // first - previously they silently did nothing, which read as a dead rail.
    // The section travels as a hash because the dashboard renders its content
    // only after member context resolves; the page consumes it once ready.
    if (pathname !== DASHBOARD_ROUTE) {
      router.push(
        item.target && item.target !== 'top'
          ? `${DASHBOARD_ROUTE}#${item.target}`
          : DASHBOARD_ROUTE,
      );
      return;
    }

    setActive(item.id);

    const targetId = item.target === 'top' ? OVERVIEW_ANCHOR_ID : item.target;
    const el = targetId ? document.getElementById(targetId) : null;

    if (item.target === 'top') {
      window.scrollTo?.({ top: 0, behavior: 'smooth' });
    } else {
      el?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
    }

    // The part that makes the click legible when both panels are already
    // visible. `preventScroll` so focus does not fight the smooth scroll.
    el?.focus?.({ preventScroll: true });
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
