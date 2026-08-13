'use client';

import { cx } from '@/components/ui/primitives';
import type { EvidencePath } from '@/lib/types';

/**
 * Renders a graph traversal as connected nodes rather than a Cypher string.
 *
 * The backend returns `path` as alternating node / "-[EDGE]->" tokens, so what
 * is drawn is exactly what was walked - no re-derivation in the UI.
 */
export function ProvenanceGraph({ path }: { path: EvidencePath }) {
  const steps = parseSteps(path.path);
  if (!steps.length) return null;

  return (
    <ol className="flex flex-col items-start gap-0">
      {steps.map((step, index) => (
        <li key={index} className="flex flex-col items-start">
          <div className={cx('graph-node', nodeStyle(step.kind))}>
            <span className="block">{step.node}</span>
            {step.kind !== 'plain' ? (
              <span className="mt-px block text-[9px] font-normal opacity-70">
                {KIND_LABEL[step.kind]}
              </span>
            ) : null}
          </div>

          {step.edge ? (
            <div className="flex items-center gap-1 py-0.5 pl-3">
              <svg
                className="h-3 w-3 text-ink-300"
                viewBox="0 0 12 12"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                aria-hidden
              >
                <path d="M6 1v10M3 8l3 3 3-3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="font-mono text-[9.5px] font-semibold tracking-wide text-graph-600">
                {step.edge}
              </span>
            </div>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

type NodeKind = 'exercise' | 'anatomy' | 'member' | 'injury' | 'equipment' | 'plain';

const KIND_LABEL: Record<NodeKind, string> = {
  exercise: 'Exercise',
  anatomy: 'Anatomical Region',
  member: 'Member',
  injury: 'Injury Condition',
  equipment: 'Equipment',
  plain: '',
};

interface Step {
  node: string;
  edge?: string;
  kind: NodeKind;
}

function parseSteps(tokens: string[]): Step[] {
  const steps: Step[] = [];
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (isEdge(token)) continue;
    const next = tokens[index + 1];
    steps.push({
      node: token,
      edge: next && isEdge(next) ? next.replace('-[', '').replace(']->', '') : undefined,
      kind: 'plain',
    });
  }
  return steps.map((step, index) => ({
    ...step,
    kind: classify(step, index, steps.length),
  }));
}

function isEdge(token: string) {
  return token.startsWith('-[');
}

/**
 * Node typing is inferred from the edge that leaves or enters it, which is
 * reliable because the safety engine emits a fixed set of path shapes.
 */
function classify(step: Step, index: number, total: number): NodeKind {
  const edge = step.edge;
  if (edge === 'HAS_INJURY' || edge === 'DOES_NOT_HAVE' || edge === 'DISLIKES') return 'member';
  if (edge === 'MAPS_TO') return 'injury';
  if (edge === 'AFFECTS') return 'injury';
  if (edge === 'STRESSES' || edge === 'REQUIRES' || edge === 'HAS_PATTERN') return 'exercise';
  if (edge === 'PART_OF') return 'anatomy';
  if (edge === 'CONTRAINDICATES') return 'injury';
  if (edge === 'IN_FAMILY') return 'plain';
  // Terminal node: infer from what pointed at it.
  if (index === total - 1) return 'anatomy';
  return 'plain';
}

function nodeStyle(kind: NodeKind) {
  switch (kind) {
    case 'exercise':
      return 'border-brand-200 bg-brand-50 text-brand-800';
    case 'anatomy':
      return 'border-graph-200 bg-graph-50 text-graph-800';
    case 'member':
      return 'border-navy-200 bg-navy-50 text-navy-800';
    case 'injury':
      return 'border-danger-200 bg-danger-50 text-danger-800';
    case 'equipment':
      return 'border-caution-200 bg-caution-50 text-caution-800';
    default:
      return 'border-ink-200 bg-ink-50 text-ink-700';
  }
}
