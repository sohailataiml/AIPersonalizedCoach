'use client';

import { cx } from '@/components/ui/primitives';

export const DURATIONS = [20, 30, 45, 60] as const;

/** Segmented control. Radio semantics so arrow keys and screen readers work. */
export function DurationSelector({
  value,
  onChange,
  disabled,
}: {
  value: number;
  onChange: (minutes: number) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <span id="duration-label" className="label-caps">
        Duration
      </span>
      <div
        role="radiogroup"
        aria-labelledby="duration-label"
        className="inline-flex overflow-hidden rounded-lg border border-ink-300 bg-white"
      >
        {DURATIONS.map((minutes) => {
          const selected = value === minutes;
          return (
            <button
              key={minutes}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={disabled}
              onClick={() => onChange(minutes)}
              className={cx(
                'px-3 py-1.5 text-2xs font-semibold transition-colors duration-150',
                'border-r border-ink-200 last:border-r-0',
                'disabled:cursor-not-allowed disabled:opacity-50',
                selected
                  ? 'bg-navy-900 text-white'
                  : 'text-ink-600 hover:bg-ink-50 hover:text-ink-800',
              )}
            >
              {minutes} min
            </button>
          );
        })}
      </div>
    </div>
  );
}
