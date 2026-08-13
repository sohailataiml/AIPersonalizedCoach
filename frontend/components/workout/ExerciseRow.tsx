'use client';

import { Badge, cx } from '@/components/ui/primitives';
import { exerciseTags, formatPrescription, statusOf } from '@/lib/presentation';
import type { ProvenanceItem, WorkoutExercise } from '@/lib/types';

/**
 * One exercise in the plan.
 *
 * The rationale and any safety caveat come from the backend - the rationale is
 * the model's composition note, the caveat is the graph's. They are visually
 * distinct so a coach can tell which is which at a glance.
 */
export function ExerciseRow({
  exercise,
  provenance,
  onInspect,
}: {
  exercise: WorkoutExercise;
  provenance?: ProvenanceItem;
  onInspect?: (exerciseId: string) => void;
}) {
  const status = provenance ? statusOf(provenance) : 'safe';
  const tags = exerciseTags(provenance);

  return (
    <li className="group flex items-start gap-3 px-4 py-2.5 transition-colors hover:bg-ink-50">
      <span
        aria-hidden
        className={cx(
          'mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full',
          status === 'safe'
            ? 'bg-safe-500'
            : status === 'cautioned'
              ? 'bg-caution-500'
              : 'bg-danger-500',
        )}
      />

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
          <button
            type="button"
            onClick={() => onInspect?.(exercise.exercise_id)}
            className="text-left text-xs font-semibold text-navy-900 hover:text-brand-700
                       hover:underline focus-visible:underline"
            title="Show this exercise in the provenance inspector"
          >
            {exercise.name}
          </button>
          <span className="font-mono text-[10.5px] text-ink-500">
            {formatPrescription(exercise)}
          </span>
        </div>

        {exercise.substituted_for ? (
          <p className="mt-0.5 text-[10.5px] font-medium text-caution-700">
            Substituted by the safety gate for “{exercise.substituted_for}”
          </p>
        ) : null}

        {exercise.coaching_note ? (
          <p className="mt-0.5 flex items-start gap-1 text-[10.5px] text-caution-700">
            <span aria-hidden>⚠</span>
            <span>{exercise.coaching_note}</span>
          </p>
        ) : null}

        {exercise.rationale ? (
          <p className="mt-0.5 line-clamp-1 text-[10.5px] text-ink-500">
            {exercise.rationale}
          </p>
        ) : null}
      </div>

      {tags.length ? (
        <div className="hidden shrink-0 gap-1 sm:flex">
          {tags.map((tag) => (
            <Badge key={tag} tone={tag === 'Member dislikes' ? 'caution' : 'safe'}>
              {tag}
            </Badge>
          ))}
        </div>
      ) : null}
    </li>
  );
}
