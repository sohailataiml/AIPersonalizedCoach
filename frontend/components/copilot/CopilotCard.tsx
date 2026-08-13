'use client';

import { useEffect, useRef, useState } from 'react';

import { ChartCard } from '@/components/copilot/ChartCard';
import {
  Badge,
  Card,
  CardHead,
  ErrorNote,
  Spinner,
  cx,
} from '@/components/ui/primitives';
import type {
  CopilotResponse,
  MemberHistory,
  MemberSummary,
  SafetyEvidence,
} from '@/lib/types';
import { AdherenceChart } from './AdherenceChart';
import { MessageHistory } from './MessageHistory';
import { MorningBrief } from './MorningBrief';
import { QuickPrompts } from './QuickPrompts';

export interface CopilotTurn {
  role: 'coach' | 'assistant';
  text: string;
  response?: CopilotResponse;
  failed?: boolean;
}

/**
 * Shown when the backend returns no prose. Never the raw payload: an
 * unformatted answer is a backend failure, and dumping the object in its place
 * would put the coach back where this component started.
 */
const MISSING_ANSWER_TEXT =
  'Safety evidence was retrieved, but the explanation could not be formatted.';

export function CopilotCard({
  member,
  history,
  turns,
  onAsk,
  isPending,
  error,
}: {
  member: MemberSummary;
  history?: MemberHistory;
  turns: CopilotTurn[];
  onAsk: (message: string) => void;
  isPending: boolean;
  error?: Error | null;
}) {
  const [draft, setDraft] = useState('');
  const streamRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    streamRef.current?.scrollTo({
      top: streamRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [turns.length, isPending]);

  function submit(message: string) {
    const trimmed = message.trim();
    if (!trimmed || isPending) return;
    onAsk(trimmed);
    setDraft('');
  }

  const churn = member.churn_risk_level?.toLowerCase();

  return (
    <Card className="flex flex-col" >
      <CardHead
        step={2}
        title="AI copilot"
        right={
          member.churn_risk_level ? (
            <Badge tone={churn === 'elevated' || churn === 'high' ? 'danger' : 'caution'}>
              churn: {member.churn_risk_level}
            </Badge>
          ) : null
        }
      />

      <MorningBrief member={member} />
      <QuickPrompts onSelect={submit} disabled={isPending} />

      {/* Conversation stream. Before the first question we show the real
          adherence chart and prior messages so the panel is useful on arrival. */}
      <div
        ref={streamRef}
        className="scrollbar-slim min-h-[300px] flex-1 overflow-y-auto"
        aria-live="polite"
      >
        {turns.length === 0 ? (
          <>
            <AdherenceChart history={history} />
            <MessageHistory history={history} />
          </>
        ) : (
          <div className="space-y-3 px-5 py-4">
            {turns.map((turn, index) => (
              <TurnBubble key={index} turn={turn} />
            ))}
          </div>
        )}

        {isPending ? (
          <div className="px-5 pb-4">
            <Spinner label="Retrieving member context…" />
          </div>
        ) : null}
      </div>

      {error ? (
        <div className="px-5 pb-3">
          <ErrorNote message={error.message} />
        </div>
      ) : null}

      <form
        className="flex items-center gap-2 border-t border-ink-200 px-5 py-3"
        onSubmit={(event) => {
          event.preventDefault();
          submit(draft);
        }}
      >
        <label htmlFor="copilot-input" className="sr-only">
          Ask about this member
        </label>
        <input
          id="copilot-input"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          disabled={isPending}
          placeholder="Ask about adherence, sleep, labs, history…"
          className="min-w-0 flex-1 rounded-lg border border-ink-300 bg-white px-3 py-2
                     text-xs text-ink-800 placeholder:text-ink-400 focus:border-brand-400
                     disabled:bg-ink-50"
        />
        <button
          type="submit"
          disabled={isPending || !draft.trim()}
          aria-label="Send message"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg
                     bg-navy-900 text-white transition-colors hover:bg-navy-800
                     disabled:cursor-not-allowed disabled:bg-ink-300"
        >
          <svg
            className="h-4 w-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden
          >
            <path d="m22 2-7 20-4-9-9-4Z" />
          </svg>
        </button>
      </form>
    </Card>
  );
}

/**
 * How the answer was grounded: two badges, the tools that ran, and the
 * deterministic evidence behind a safety verdict - collapsed by default.
 *
 * Everything here is a string the backend already rendered. The component
 * decides layout, never meaning.
 */
function GroundingStrip({
  toolsUsed,
  authoritative,
  corrected,
  evidence,
}: {
  toolsUsed: string[];
  authoritative: boolean;
  corrected: boolean;
  evidence: SafetyEvidence | null;
}) {
  const excluded = evidence?.decision === 'excluded';

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-1">
        <span
          className="inline-flex items-center gap-1 rounded border border-graph-200
                     bg-graph-50 px-1.5 py-0.5 text-[9.5px] font-medium text-graph-700"
        >
          <span aria-hidden>◈</span> MCP grounded
        </span>

        {authoritative ? (
          <span
            className={cx(
              'inline-flex items-center gap-1 rounded border px-1.5 py-0.5',
              'text-[9.5px] font-medium',
              // Semantic, per the palette: red means the graph removed it.
              excluded
                ? 'border-danger-200 bg-danger-50 text-danger-700'
                : 'border-safe-200 bg-safe-50 text-safe-700',
            )}
          >
            <span aria-hidden>⛨</span> Safety authoritative
          </span>
        ) : null}

        {corrected ? (
          <Badge tone="caution">verdict corrected</Badge>
        ) : null}
      </div>

      {toolsUsed.length ? (
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-[9.5px] uppercase tracking-wide text-ink-400">
            Tools used
          </span>
          {toolsUsed.map((tool) => (
            <code
              key={tool}
              className="rounded border border-ink-200 bg-ink-50 px-1 py-0.5
                         font-mono text-[9.5px] text-ink-600"
            >
              {tool}
            </code>
          ))}
        </div>
      ) : null}

      {evidence ? <EvidenceDisclosure evidence={evidence} /> : null}
    </div>
  );
}

function EvidenceDisclosure({ evidence }: { evidence: SafetyEvidence }) {
  return (
    <details className="group rounded border border-ink-200 bg-ink-50/60">
      <summary
        className="cursor-pointer list-none px-2 py-1 text-[9.5px] text-ink-600
                   transition-colors hover:text-ink-800"
      >
        <span aria-hidden className="inline-block transition-transform group-open:rotate-90">
          ▸
        </span>{' '}
        View evidence
      </summary>

      <div className="space-y-2 border-t border-ink-200 px-2 py-1.5">
        <p className="text-[9.5px] text-ink-600">
          <span className="font-medium text-ink-800">{evidence.exercise_name}</span>
          {' — '}
          <span
            className={cx(
              'font-medium',
              evidence.decision === 'excluded' ? 'text-danger-700' : 'text-ink-700',
            )}
          >
            {evidence.decision}
          </span>
        </p>

        {evidence.reasons.length ? (
          <ul className="space-y-0.5">
            {evidence.reasons.map((reason) => (
              <li key={reason.rule_id + reason.message} className="text-[9.5px] text-ink-600">
                <code className="font-mono text-[9px] text-graph-700">{reason.rule_id}</code>{' '}
                {reason.message}
              </li>
            ))}
          </ul>
        ) : null}

        {/* Real traversals, rendered by the graph engine. Never reconstructed here. */}
        {evidence.graph_paths.length ? (
          <div className="scrollbar-slim overflow-x-auto">
            <ul className="space-y-0.5">
              {evidence.graph_paths.map((path) => (
                <li
                  key={path}
                  className="whitespace-nowrap font-mono text-[9px] leading-relaxed text-graph-700"
                >
                  {path}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {evidence.evidence_note ? (
          <p className="text-[9.5px] italic text-ink-500">{evidence.evidence_note}</p>
        ) : null}
      </div>
    </details>
  );
}

function TurnBubble({ turn }: { turn: CopilotTurn }) {
  if (turn.role === 'coach') {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-2xl rounded-br-sm bg-navy-900 px-3 py-2 text-2xs text-white">
          {turn.text}
        </p>
      </div>
    );
  }

  return (
    <div className="animate-fade-up space-y-2">
      <div
        className={cx(
          'max-w-[92%] rounded-2xl rounded-bl-sm border px-3 py-2.5',
          turn.failed ? 'border-danger-200 bg-danger-50' : 'border-ink-200 bg-white',
        )}
      >
        <p
          className={cx(
            'whitespace-pre-line text-2xs leading-relaxed',
            turn.failed ? 'text-danger-700' : 'text-ink-700',
          )}
        >
          {turn.text.trim() || MISSING_ANSWER_TEXT}
        </p>
      </div>

      {turn.response?.chart ? <ChartCard chart={turn.response.chart} /> : null}

      {turn.response?.grounding?.mode === 'mcp' ? (
        <GroundingStrip
          toolsUsed={turn.response.grounding.tools_used}
          authoritative={turn.response.grounding.authoritative_safety}
          corrected={turn.response.grounding.safety_corrected}
          evidence={turn.response.safety_evidence ?? null}
        />
      ) : null}

      {turn.response?.citations.length ? (
        <div className="flex flex-wrap gap-1">
          {turn.response.citations.map((citation, index) => (
            <span
              key={index}
              title={citation.detail}
              className="inline-flex items-center gap-1 rounded border border-ink-200
                         bg-ink-50 px-1.5 py-0.5 text-[9.5px] text-ink-500"
            >
              <span aria-hidden>▪</span>
              {citation.source}
            </span>
          ))}
          {turn.response.generator === 'deterministic' ? (
            <Badge tone="caution">no data — not invented</Badge>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
