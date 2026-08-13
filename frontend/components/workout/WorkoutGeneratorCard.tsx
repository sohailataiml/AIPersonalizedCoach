'use client';

import { useMemo, useState } from 'react';

import {
  Badge,
  Button,
  Card,
  CardHead,
  Chip,
  EmptyState,
  ErrorNote,
  Spinner,
} from '@/components/ui/primitives';
import { estimateMinutes } from '@/lib/presentation';
import type { GenerateWorkoutResponse, ProvenanceItem } from '@/lib/types';
import { ConceptResolution } from './ConceptResolution';
import { DurationSelector } from './DurationSelector';
import { WorkoutSectionCard } from './WorkoutSectionCard';

/** The three assessment scenarios, one click away for a reviewer. */
export const SCENARIOS = [
  {
    id: 'injury',
    label: 'Injury',
    prompt:
      'Create a 45-minute lower-body workout. Her left knee is bothering her and she only has dumbbells and a kettlebell.',
    duration: 45,
  },
  {
    id: 'equipment',
    label: 'Equipment',
    prompt:
      'Build a full-body workout. She has no barbell, only dumbbells and a kettlebell.',
    duration: 45,
  },
  {
    id: 'exclusion',
    label: 'Exclusion',
    prompt: 'Create a lower-body workout but exclude deadlifts.',
    duration: 45,
  },
] as const;

export function WorkoutGeneratorCard({
  prompt,
  duration,
  onPromptChange,
  onDurationChange,
  onGenerate,
  isGenerating,
  error,
  result,
  onInspect,
}: {
  prompt: string;
  duration: number;
  onPromptChange: (value: string) => void;
  onDurationChange: (value: number) => void;
  onGenerate: () => void;
  isGenerating: boolean;
  error?: Error | null;
  result?: GenerateWorkoutResponse | null;
  onInspect?: (exerciseId: string) => void;
}) {
  const [activeScenario, setActiveScenario] = useState<string | null>('injury');

  const provenanceById = useMemo(() => {
    const map = new Map<string, ProvenanceItem>();
    for (const item of result?.provenance ?? []) map.set(item.exercise_id, item);
    return map;
  }, [result]);

  const totals = useMemo(() => {
    const exercises = result?.workout.sections.flatMap((s) => s.exercises) ?? [];
    return { count: exercises.length, minutes: estimateMinutes(exercises) };
  }, [result]);

  const hasNoSafeCandidates =
    result != null && result.safety.eligible === 0;

  return (
    <Card className="flex flex-col">
      <CardHead
        step={1}
        title="Workout generator"
        right={
          result ? (
            <Badge tone="safe" title="Every exercise re-checked against the graph">
              Graph-validated ✓
            </Badge>
          ) : (
            <span className="text-2xs text-ink-400">Graph-filtered candidates</span>
          )
        }
      />

      <form
        className="px-5 py-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (!isGenerating && prompt.trim()) onGenerate();
        }}
      >
        <label htmlFor="workout-prompt" className="label-caps mb-1.5 block">
          Your request
        </label>
        <textarea
          id="workout-prompt"
          value={prompt}
          onChange={(event) => {
            onPromptChange(event.target.value);
            setActiveScenario(null);
          }}
          rows={2}
          disabled={isGenerating}
          placeholder="e.g. 45-minute lower body, avoid her left knee, dumbbells only"
          className="w-full resize-y rounded-lg border border-ink-300 bg-white px-3 py-2
                     text-xs leading-relaxed text-ink-800 placeholder:text-ink-400
                     focus:border-brand-400 disabled:bg-ink-50"
        />

        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          {SCENARIOS.map((scenario) => (
            <Chip
              key={scenario.id}
              active={activeScenario === scenario.id}
              disabled={isGenerating}
              onClick={() => {
                onPromptChange(scenario.prompt);
                onDurationChange(scenario.duration);
                setActiveScenario(scenario.id);
              }}
            >
              {scenario.label}
            </Chip>
          ))}
        </div>

        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <DurationSelector
            value={duration}
            onChange={onDurationChange}
            disabled={isGenerating}
          />
          <Button type="submit" disabled={isGenerating || !prompt.trim()}>
            {isGenerating
              ? 'Reasoning over graph…'
              : result
                ? 'Regenerate workout'
                : 'Generate workout'}
          </Button>
        </div>
      </form>

      {isGenerating ? (
        <div className="border-t border-ink-200 px-5 py-4">
          <Spinner label="Resolving concepts, traversing anatomy, validating plan…" />
        </div>
      ) : null}

      {error ? (
        <div className="border-t border-ink-200 px-5 py-4">
          <ErrorNote message={error.message} />
        </div>
      ) : null}

      {hasNoSafeCandidates ? (
        <div className="border-t border-ink-200 px-5 py-4">
          <ErrorNote
            message="No exercises survived the safety filters for this request. Loosen the
                     constraints or review the filtered list below — the system fails closed
                     rather than returning an unvalidated plan."
          />
        </div>
      ) : null}

      {result && !isGenerating && !hasNoSafeCandidates ? (
        <div className="animate-fade-up border-t border-ink-200">
          <ConceptResolution
            resolved={result.resolved_concepts}
            unresolved={result.unresolved_concepts}
          />

          {!result.safety.post_validation_passed ? (
            <div className="mx-5 mb-3 rounded-lg border border-caution-200 bg-caution-50 px-3 py-2.5">
              <p className="text-2xs font-semibold text-caution-800">
                Safety gate corrected this plan
              </p>
              <p className="mt-0.5 text-2xs leading-relaxed text-caution-700">
                {result.safety.post_validation_rejections} exercise(s) returned by the
                model were rejected by deterministic re-validation;{' '}
                {result.safety.post_validation_replacements} replaced from the safe pool.
              </p>
            </div>
          ) : null}

          <div className="space-y-2.5 px-5 pb-4">
            {result.workout.sections.map((section) => (
              <WorkoutSectionCard
                key={section.name}
                section={section}
                provenanceById={provenanceById}
                onInspect={onInspect}
              />
            ))}
          </div>

          <footer
            className="flex items-center justify-between border-t border-ink-200 px-5 py-2.5"
          >
            <span className="text-2xs text-ink-500">
              {totals.count} exercises · est. {totals.minutes} min
            </span>
            <div className="flex items-center gap-2">
              <span className="text-2xs text-ink-400">
                {result.safety.eligible} of {result.safety.catalog_total} eligible
              </span>
              <button
                type="button"
                onClick={() =>
                  document
                    .getElementById('graph-reasoning')
                    ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                }
                className="rounded-lg border border-graph-300 bg-graph-50 px-2.5 py-1
                           text-2xs font-semibold text-graph-700 transition-colors
                           hover:bg-graph-100"
              >
                View graph reasoning →
              </button>
            </div>
          </footer>
        </div>
      ) : null}

      {!result && !isGenerating && !error ? (
        <EmptyState
          title="No plan yet"
          body="Pick a scenario or write a request. Exercises are filtered by graph traversal before the model sees them."
        />
      ) : null}
    </Card>
  );
}
