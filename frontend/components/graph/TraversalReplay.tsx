'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Badge, EmptyState, StatusPill, cx } from '@/components/ui/primitives';
import { buildReplaySteps, type ReplayStep } from '@/lib/replay';
import type { GraphTraversal } from '@/lib/types';
import { CONSTRAINT_LABEL, CONSTRAINT_TONE, TraversalPath } from './TraversalPath';

const SPEEDS = [
  { label: '0.5×', ms: 2400 },
  { label: '1×', ms: 1200 },
  { label: '2×', ms: 600 },
] as const;

/**
 * Steps through the exact hops the safety engine walked for one decision.
 *
 * The script is built from the traversal's own ordering - this replays what
 * happened, it does not re-derive or dramatise it. Autoplay is off by default
 * and disabled entirely under `prefers-reduced-motion`; stepping is always
 * available, and the whole control is keyboard-driven.
 */
export function TraversalReplay({
  traversals,
  exerciseName,
}: {
  traversals: GraphTraversal[];
  exerciseName: string;
}) {
  const steps = useMemo(() => buildReplaySteps(traversals), [traversals]);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const containerRef = useRef<HTMLDivElement>(null);

  const total = steps.length;
  const step: ReplayStep | undefined = steps[index];

  // Restart whenever the selected decision changes.
  useEffect(() => {
    setIndex(0);
    setPlaying(false);
  }, [exerciseName, total]);

  const next = useCallback(() => {
    setIndex((current) => {
      if (current >= total - 1) {
        setPlaying(false);
        return current;
      }
      return current + 1;
    });
  }, [total]);

  const previous = useCallback(() => setIndex((c) => Math.max(0, c - 1)), []);

  const restart = useCallback(() => {
    setIndex(0);
    setPlaying(false);
  }, []);

  useEffect(() => {
    if (!playing) return;
    const reduced =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reduced) {
      setPlaying(false);
      return;
    }
    const timer = window.setInterval(next, SPEEDS[speed].ms);
    return () => window.clearInterval(timer);
  }, [playing, speed, next]);

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      next();
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      previous();
    } else if (event.key === ' ' || event.key === 'Spacebar') {
      event.preventDefault();
      setPlaying((p) => !p);
    }
  }

  if (!steps.length || !step) {
    return (
      <EmptyState
        title="Nothing to replay"
        body="This decision has no recorded traversal steps."
      />
    );
  }

  const activeTraversal = traversals[step.traversalIndex];
  const isFinal = step.kind === 'decision';

  return (
    <div
      ref={containerRef}
      role="group"
      aria-label="Traversal replay"
      tabIndex={0}
      onKeyDown={onKeyDown}
      className="rounded-xl border border-ink-200 bg-white p-3 focus-visible:ring-2"
    >
      <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <h4 className="text-xs font-semibold text-navy-900">{exerciseName}</h4>
          <StatusPill
            status={
              traversals[0].decision === 'excluded'
                ? 'excluded'
                : traversals[0].decision === 'downranked'
                  ? 'cautioned'
                  : 'safe'
            }
          />
        </div>
        <span className="font-mono text-[10px] text-ink-500" data-testid="replay-position">
          Step {index + 1} of {total}
        </span>
      </div>

      {/* Controls */}
      <div className="mb-3 flex flex-wrap items-center gap-1.5">
        <IconButton label="Restart" onClick={restart} disabled={index === 0 && !playing}>
          <path d="M3 8a5 5 0 1 1 1.6 3.7M3 4v4h4" />
        </IconButton>
        <IconButton label="Previous step" onClick={previous} disabled={index === 0}>
          <path d="M10 3 5 8l5 5M4 3v10" />
        </IconButton>
        <button
          type="button"
          onClick={() => setPlaying((p) => !p)}
          disabled={index >= total - 1}
          aria-label={playing ? 'Pause replay' : 'Play replay'}
          className="inline-flex items-center gap-1.5 rounded-lg bg-navy-900 px-3 py-1.5
                     text-2xs font-semibold text-white transition-colors hover:bg-navy-800
                     disabled:cursor-not-allowed disabled:bg-ink-300"
        >
          {playing ? 'Pause' : 'Play'}
        </button>
        <IconButton
          label="Next step"
          onClick={next}
          disabled={index >= total - 1}
        >
          <path d="M6 3l5 5-5 5M12 3v10" />
        </IconButton>

        <div className="ml-auto flex overflow-hidden rounded-lg border border-ink-300">
          {SPEEDS.map((option, optionIndex) => (
            <button
              key={option.label}
              type="button"
              onClick={() => setSpeed(optionIndex)}
              aria-pressed={speed === optionIndex}
              className={cx(
                'px-2 py-1 text-[10px] font-semibold transition-colors',
                speed === optionIndex
                  ? 'bg-navy-900 text-white'
                  : 'text-ink-600 hover:bg-ink-50',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {/* Progress */}
      <ol className="mb-3 flex gap-0.5" aria-hidden>
        {steps.map((item, itemIndex) => (
          <li
            key={itemIndex}
            className={cx(
              'h-1 flex-1 rounded-full transition-colors',
              itemIndex < index
                ? 'bg-graph-400'
                : itemIndex === index
                  ? 'bg-graph-600'
                  : 'bg-ink-200',
            )}
          />
        ))}
      </ol>

      {/* Caption - announced to screen readers as it changes */}
      <div
        aria-live="polite"
        className={cx(
          'mb-3 rounded-lg border px-3 py-2',
          isFinal
            ? 'border-navy-300 bg-navy-50'
            : step.kind === 'fact'
              ? 'border-ink-200 bg-ink-50'
              : 'border-graph-200 bg-graph-50',
        )}
      >
        <div className="flex items-start gap-2">
          <span
            aria-hidden
            className={cx(
              'mt-px flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] font-bold text-white',
              isFinal ? 'bg-navy-800' : step.kind === 'fact' ? 'bg-ink-400' : 'bg-graph-600',
            )}
          >
            {index + 1}
          </span>
          <div className="min-w-0">
            <p
              className={cx(
                'text-2xs font-semibold',
                isFinal ? 'text-navy-900' : 'text-ink-800',
              )}
            >
              {step.caption}
            </p>
            {step.detail ? (
              <p className="mt-0.5 text-[10.5px] leading-relaxed text-ink-500">
                {step.detail}
              </p>
            ) : null}
          </div>
        </div>
      </div>

      {/* The graph, revealed up to the current step */}
      <div className="mb-1.5 flex items-center gap-1.5">
        <Badge tone={CONSTRAINT_TONE[step.constraintType]}>
          {CONSTRAINT_LABEL[step.constraintType]}
        </Badge>
        {traversals.length > 1 ? (
          <span className="text-[10px] text-ink-400">
            path {step.traversalIndex + 1} of {traversals.length}
          </span>
        ) : null}
      </div>

      {activeTraversal ? (
        <TraversalPath
          traversal={activeTraversal}
          visibleNodes={step.visibleNodes}
          activeEdge={step.activeEdge}
          showFacts={step.kind === 'fact' || isFinal}
        />
      ) : null}

      <p className="mt-2 text-[10px] text-ink-400">
        Replays the hops the safety engine recorded, in order. Use ← → to step,
        space to play.
      </p>
    </div>
  );
}

function IconButton({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className="inline-flex h-7 w-7 items-center justify-center rounded-lg border
                 border-ink-300 bg-white text-ink-600 transition-colors
                 hover:bg-ink-50 disabled:cursor-not-allowed disabled:opacity-40"
    >
      <svg
        className="h-3.5 w-3.5"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        {children}
      </svg>
    </button>
  );
}
