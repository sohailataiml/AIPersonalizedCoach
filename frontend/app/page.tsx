'use client';

import { useMutation, useQuery } from '@tanstack/react-query';
import { useCallback, useState } from 'react';

import { Sidebar } from '@/components/app-shell/Sidebar';
import { CopilotCard, type CopilotTurn } from '@/components/copilot/CopilotCard';
import { GraphReasoningPanel } from '@/components/graph/GraphReasoningPanel';
import { ClinicalNoteBanner } from '@/components/member/ClinicalNoteBanner';
import { MemberHeader } from '@/components/member/MemberHeader';
import { MemberMetricStrip } from '@/components/member/MemberMetricStrip';
import { SafetyInspector } from '@/components/provenance/SafetyInspector';
import { TechnicalDetails } from '@/components/provenance/TechnicalDetails';
import { ErrorNote, Spinner } from '@/components/ui/primitives';
import {
  SCENARIOS,
  WorkoutGeneratorCard,
} from '@/components/workout/WorkoutGeneratorCard';
import {
  AdjustmentDiffView,
  WorkoutAdjustment,
} from '@/components/workout/WorkoutAdjustment';
import { DEFAULT_MEMBER_ID, api } from '@/lib/api';
import type { AdjustmentDiff, GenerateWorkoutResponse } from '@/lib/types';

export default function DashboardPage() {
  const memberId = DEFAULT_MEMBER_ID;

  const [prompt, setPrompt] = useState<string>(SCENARIOS[0].prompt);
  const [duration, setDuration] = useState<number>(SCENARIOS[0].duration);
  const [result, setResult] = useState<GenerateWorkoutResponse | null>(null);
  const [selectedExerciseId, setSelectedExerciseId] = useState<string | null>(null);
  const [turns, setTurns] = useState<CopilotTurn[]>([]);
  const [generatedAt, setGeneratedAt] = useState<Date | null>(null);
  // The diff belongs to the last adjustment, so it is cleared whenever a fresh
  // plan is generated - showing a stale diff beside a new plan would misreport
  // what changed.
  const [adjustment, setAdjustment] = useState<{
    text: string;
    diff: AdjustmentDiff;
  } | null>(null);

  const member = useQuery({
    queryKey: ['member', memberId],
    queryFn: () => api.member(memberId),
  });

  const history = useQuery({
    queryKey: ['history', memberId],
    queryFn: () => api.memberHistory(memberId),
  });

  const health = useQuery({ queryKey: ['health'], queryFn: api.health });

  const generate = useMutation({
    mutationFn: () =>
      api.generateWorkout({
        member_id: memberId,
        prompt,
        duration_minutes: duration,
      }),
    onSuccess: (data) => {
      setResult(data);
      setAdjustment(null);
      setGeneratedAt(new Date());
      // Default the inspector to the first removed exercise, which is the most
      // interesting thing a reviewer can look at.
      const firstFiltered = data.filtered_exercises.find(
        (item) => item.decision === 'filtered',
      );
      setSelectedExerciseId(firstFiltered?.exercise_id ?? null);
    },
  });

  const adjust = useMutation({
    mutationFn: (text: string) =>
      api.adjustWorkout({
        member_id: memberId,
        base_prompt: prompt,
        adjustment: text,
        duration_minutes: duration,
        previous_exercise_ids:
          result?.workout.sections.flatMap((section) =>
            section.exercises.map((exercise) => exercise.exercise_id),
          ) ?? [],
      }),
    onSuccess: (data) => {
      // The adjusted response is a full plan with its own provenance and graph
      // reasoning, so it simply replaces the current result.
      setResult(data);
      setAdjustment({ text: data.adjustment, diff: data.diff });
      setGeneratedAt(new Date());
      const firstRemoved = data.diff.removed[0]?.exercise_id;
      const firstFiltered = data.filtered_exercises.find(
        (item) => item.decision === 'filtered',
      );
      setSelectedExerciseId(firstRemoved ?? firstFiltered?.exercise_id ?? null);
    },
  });

  const copilot = useMutation({
    mutationFn: (message: string) =>
      api.copilotChat({ member_id: memberId, message }),
    onSuccess: (response) => {
      setTurns((current) => [
        ...current,
        { role: 'assistant', text: response.answer, response },
      ]);
    },
    onError: (error: Error) => {
      setTurns((current) => [
        ...current,
        {
          role: 'assistant',
          text: `I could not answer that: ${error.message}`,
          failed: true,
        },
      ]);
    },
  });

  const ask = useCallback(
    (message: string) => {
      setTurns((current) => [...current, { role: 'coach', text: message }]);
      copilot.mutate(message);
    },
    [copilot],
  );

  const inspect = useCallback((exerciseId: string) => {
    setSelectedExerciseId(exerciseId);
    document
      .getElementById('safety-inspector')
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, []);

  if (member.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Loading member context…" />
      </div>
    );
  }

  if (member.isError || !member.data) {
    return (
      <main className="mx-auto max-w-lg px-6 py-24">
        <h1 className="text-xl font-semibold text-navy-900">Backend unavailable</h1>
        <p className="mt-2 text-xs leading-relaxed text-ink-500">
          The dashboard needs the FastAPI service. Start it with{' '}
          <code className="rounded bg-ink-100 px-1.5 py-0.5 font-mono text-[11px]">
            make dev
          </code>{' '}
          or{' '}
          <code className="rounded bg-ink-100 px-1.5 py-0.5 font-mono text-[11px]">
            docker compose up --build
          </code>
          .
        </p>
        <div className="mt-4">
          <ErrorNote message={(member.error as Error)?.message ?? 'Unknown error'} />
        </div>
      </main>
    );
  }

  const injury = member.data.active_injuries[0];

  return (
    <div className="flex min-h-screen">
      <Sidebar />

      <div className="min-w-0 flex-1">
        {/* `tabIndex={-1}` so the Overview nav item has something to focus.
            Sections are focus targets, not tab stops. */}
        <header
          id="overview"
          tabIndex={-1}
          className="scroll-mt-4 rounded-none border-b border-ink-200 bg-white px-6 py-5
                     outline-none focus:ring-2 focus:ring-inset focus:ring-brand-400/60"
        >
          <div className="mx-auto max-w-[1500px]">
            <MemberHeader
              member={member.data}
              lastUpdatedLabel={
                generatedAt
                  ? `${Math.max(1, Math.round((Date.now() - generatedAt.getTime()) / 60000))}m ago`
                  : undefined
              }
              onNewWorkout={() => {
                if (!generate.isPending) generate.mutate();
              }}
              isBusy={generate.isPending}
            />
          </div>
        </header>

        <main className="mx-auto max-w-[1500px] space-y-4 px-6 py-5 pb-16">
          <MemberMetricStrip member={member.data} history={history.data} />

          <ClinicalNoteBanner injury={injury} />

          <div className="grid items-start gap-4 xl:grid-cols-2">
            <div
              id="workout-generator"
              tabIndex={-1}
              aria-label="Workout generator"
              className="scroll-mt-4 rounded-card outline-none
                         focus:ring-2 focus:ring-brand-400/60 focus:ring-offset-2"
            >
              <WorkoutGeneratorCard
                prompt={prompt}
                duration={duration}
                onPromptChange={setPrompt}
                onDurationChange={setDuration}
                onGenerate={() => generate.mutate()}
                isGenerating={generate.isPending}
                error={generate.error as Error | null}
                result={result}
                onInspect={inspect}
              />

              {result ? (
                <div className="card mt-4">
                  <WorkoutAdjustment
                    onAdjust={(text) => adjust.mutate(text)}
                    isPending={adjust.isPending}
                    error={adjust.error as Error | null}
                    disabled={!result}
                  />
                  {adjustment ? (
                    <AdjustmentDiffView
                      diff={adjustment.diff}
                      adjustment={adjustment.text}
                    />
                  ) : null}
                </div>
              ) : null}
            </div>

            <div
              id="copilot"
              tabIndex={-1}
              aria-label="Coach copilot"
              className="scroll-mt-4 rounded-card outline-none
                         focus:ring-2 focus:ring-brand-400/60 focus:ring-offset-2"
            >
              <CopilotCard
                member={member.data}
                history={history.data}
                turns={turns}
                onAsk={ask}
                isPending={copilot.isPending}
                error={null}
              />
            </div>
          </div>

          {/* Graph reasoning sits between the generator and the inspector: it
              explains how the candidate set was produced, and shares selection
              state with the inspector below. */}
          <GraphReasoningPanel
            result={result}
            selectedExerciseId={selectedExerciseId}
            onSelect={setSelectedExerciseId}
          />

          <SafetyInspector
            result={result}
            selectedExerciseId={selectedExerciseId}
            onSelect={setSelectedExerciseId}
          />

          <TechnicalDetails result={result} health={health.data} />

          <footer className="flex flex-wrap items-center justify-between gap-2 pt-1 text-[10.5px] text-ink-400">
            <span>
              Safety decisions are produced by deterministic graph traversal and
              re-validated after generation. Synthetic data only.
            </span>
            {health.data ? (
              <span className="font-mono">
                graph.{health.data.graph_backend} · llm.{health.data.llm_provider} ·{' '}
                {health.data.graph_stats['node:Exercise'] ?? 0} exercises
              </span>
            ) : null}
          </footer>
        </main>
      </div>
    </div>
  );
}
