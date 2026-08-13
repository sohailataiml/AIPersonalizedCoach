'use client';

import { cx } from '@/components/ui/primitives';
import { estimateMinutes } from '@/lib/presentation';
import type { ProvenanceItem, WorkoutSection } from '@/lib/types';
import { ExerciseRow } from './ExerciseRow';

const SECTION_META: Record<
  WorkoutSection['name'],
  { label: string; dot: string }
> = {
  warmup: { label: 'Warm-up', dot: 'bg-brand-400' },
  main: { label: 'Main', dot: 'bg-navy-800' },
  cooldown: { label: 'Cool-down', dot: 'bg-graph-400' },
};

export function WorkoutSectionCard({
  section,
  provenanceById,
  onInspect,
}: {
  section: WorkoutSection;
  provenanceById: Map<string, ProvenanceItem>;
  onInspect?: (exerciseId: string) => void;
}) {
  const meta = SECTION_META[section.name];
  const minutes = estimateMinutes(section.exercises);

  return (
    <section
      className="overflow-hidden rounded-xl border border-ink-200"
      aria-label={meta.label}
    >
      <header className="flex items-center gap-2 border-b border-ink-200 bg-ink-50 px-4 py-2">
        <span aria-hidden className={cx('h-1.5 w-1.5 rounded-full', meta.dot)} />
        <h4 className="text-2xs font-semibold uppercase tracking-[0.09em] text-ink-700">
          {meta.label}
        </h4>
        <span className="ml-auto text-[10.5px] text-ink-500">est. {minutes} min</span>
      </header>

      <ul className="divide-y divide-ink-100">
        {section.exercises.map((exercise) => (
          <ExerciseRow
            key={exercise.exercise_id}
            exercise={exercise}
            provenance={provenanceById.get(exercise.exercise_id)}
            onInspect={onInspect}
          />
        ))}
      </ul>
    </section>
  );
}
