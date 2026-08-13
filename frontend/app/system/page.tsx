'use client';

import { useQuery } from '@tanstack/react-query';

import { Sidebar } from '@/components/app-shell/Sidebar';
import { EvaluationHistoryPanel } from '@/components/system/EvaluationHistoryPanel';
import { EvaluationMatrix } from '@/components/system/EvaluationMatrix';
import {
  KpiCards,
  QualityByCategory,
  SafetyInvariants,
} from '@/components/system/EvaluationOverview';
import {
  ExecutionTraces,
  McpObservability,
} from '@/components/system/ExecutionTraces';
import { Badge, Card, EmptyState, ErrorNote, Spinner } from '@/components/ui/primitives';
import { api } from '@/lib/api';

/**
 * System Quality — the developer / operator surface.
 *
 * Two distinct questions live here, deliberately not blended:
 *
 *   Offline evaluation  — "does the system behave correctly across known
 *                          scenarios?"  (artifacts from `make eval`)
 *   Runtime observability — "what happened during this particular request?"
 *                          (in-process trace buffer)
 *
 * The coach dashboard at `/` stays clean; everything here is engineering.
 */
export default function SystemQualityPage() {
  const evaluation = useQuery({
    queryKey: ['evaluation', 'latest'],
    queryFn: api.latestEvaluation,
  });

  const history = useQuery({
    queryKey: ['evaluation', 'history'],
    queryFn: () => api.evaluationHistory(10),
  });

  const traces = useQuery({
    queryKey: ['traces'],
    queryFn: () => api.traces(25),
    refetchInterval: 10_000,
  });

  const run = evaluation.data ?? null;

  return (
    <div className="flex min-h-screen">
      <Sidebar current="system" />

      <div className="min-w-0 flex-1">
        <header className="border-b border-ink-200 bg-white px-6 py-5">
          <div className="mx-auto flex max-w-[1500px] flex-wrap items-end justify-between gap-3">
            <div>
              <h1 className="text-lg font-semibold tracking-tight text-navy-900">
                System quality
              </h1>
              <p className="mt-0.5 text-2xs text-ink-500">
                Offline evaluation and runtime tracing for the AI system. Not part
                of the coach workflow.
              </p>
            </div>
            {run ? (
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={run.status === 'pass' ? 'safe' : 'danger'}>
                  {run.status.toUpperCase()}
                </Badge>
                <span className="text-[10px] text-ink-500">
                  last evaluation {run.started_at} · graph.{run.graph_backend} ·
                  llm.{run.llm_provider}
                </span>
              </div>
            ) : null}
          </div>
        </header>

        <main className="mx-auto max-w-[1500px] space-y-4 px-6 py-5 pb-16">
          {evaluation.isLoading ? (
            <Spinner label="Loading evaluation results…" />
          ) : evaluation.isError ? (
            <ErrorNote
              message={
                (evaluation.error as Error)?.message ??
                'Could not reach the API for evaluation results.'
              }
            />
          ) : run ? (
            <>
              <KpiCards run={run} />
              <div className="grid items-start gap-4 xl:grid-cols-2">
                <SafetyInvariants invariants={run.invariants} />
                <QualityByCategory metrics={run.metrics} />
              </div>
              <EvaluationMatrix results={run.results} />
            </>
          ) : (
            <Card>
              <EmptyState
                title="No evaluation has been run"
                body="Run the offline suite to populate this page. Nothing here is hard-coded, so it stays empty until real results exist."
              />
              <div className="px-5 pb-4">
                <code className="rounded bg-ink-100 px-2 py-1 font-mono text-[11px] text-ink-700">
                  make eval
                </code>
              </div>
            </Card>
          )}

          {history.data ? (
            <EvaluationHistoryPanel history={history.data} />
          ) : null}

          <ExecutionTraces traces={traces.data?.traces ?? []} />
          <McpObservability traces={traces.data?.traces ?? []} />

          <footer className="pt-1 text-[10.5px] text-ink-400">
            Evaluation results are read from{' '}
            <code className="font-mono">artifacts/evals/</code>. Traces are held
            in memory for this process only and contain no member payload, prompt
            body or model reasoning.
          </footer>
        </main>
      </div>
    </div>
  );
}
