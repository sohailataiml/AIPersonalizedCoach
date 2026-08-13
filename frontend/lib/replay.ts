/**
 * Turns a decision's traversals into an ordered replay script.
 *
 * This is a pure re-presentation of backend data: the order is the order the
 * safety engine recorded, node and relationship names are used verbatim, and
 * captions are templated from those values rather than written as narrative.
 * Nothing here introduces a hop, a relationship, or a claim that is not already
 * in the traversal.
 */

import type {
  ConstraintType,
  GraphTraceEdge,
  GraphTraceNode,
  GraphTraversal,
} from './types';

export type ReplayStepKind = 'start' | 'hop' | 'fact' | 'decision';

export interface ReplayStep {
  kind: ReplayStepKind;
  /** One-line description of what this step does. */
  caption: string;
  /** Optional supporting text (node type, rule id, reason). */
  detail?: string;
  traversalId: string;
  traversalIndex: number;
  constraintType: ConstraintType;
  /** How many nodes of the traversal are revealed at this step. */
  visibleNodes: number;
  /** Index of the edge being traversed, if this step is a hop. */
  activeEdge: number | null;
  node?: GraphTraceNode;
  edge?: GraphTraceEdge;
}

const CONSTRAINT_TITLE: Record<ConstraintType, string> = {
  injury_anatomy: 'Injury / anatomy check',
  contraindication: 'Contraindication check',
  equipment: 'Equipment check',
  explicit_exclusion: 'Coach exclusion check',
  preference_ranking: 'Preference / ranking check',
  data_gap: 'Catalog data check',
};

export function buildReplaySteps(traversals: GraphTraversal[]): ReplayStep[] {
  const steps: ReplayStep[] = [];

  traversals.forEach((traversal, traversalIndex) => {
    const base = {
      traversalId: traversal.id,
      traversalIndex,
      constraintType: traversal.constraint_type,
    };

    if (traversal.nodes.length) {
      const first = traversal.nodes[0];
      steps.push({
        ...base,
        kind: 'start',
        caption: `Start at ${first.label}`,
        detail: `${CONSTRAINT_TITLE[traversal.constraint_type]} · node type ${first.type}`,
        visibleNodes: 1,
        activeEdge: null,
        node: first,
      });

      traversal.edges.forEach((edge, edgeIndex) => {
        const target = traversal.nodes[edgeIndex + 1];
        if (!target) return;
        const reversed = edge.direction === 'incoming';
        steps.push({
          ...base,
          kind: 'hop',
          caption: reversed
            ? `Follow ${edge.relationship} backwards to ${target.label}`
            : `Follow ${edge.relationship} to ${target.label}`,
          detail: reversed
            ? `Read against the stored arrow: ${target.label} -[${edge.relationship}]-> ${traversal.nodes[edgeIndex].label}`
            : `${traversal.nodes[edgeIndex].label} -[${edge.relationship}]-> ${target.label}`,
          visibleNodes: edgeIndex + 2,
          activeEdge: edgeIndex,
          node: target,
          edge,
        });
      });
    }

    traversal.facts.forEach((fact) => {
      steps.push({
        ...base,
        kind: 'fact',
        caption: fact,
        detail:
          traversal.source === 'deterministic_set_operation'
            ? 'Deterministic set operation — not a graph relationship'
            : 'Deterministic fact recorded alongside the traversal',
        visibleNodes: traversal.nodes.length,
        activeEdge: null,
      });
    });
  });

  // Close with the decision itself, so a replay always ends on the outcome.
  const last = traversals[traversals.length - 1];
  if (last) {
    steps.push({
      kind: 'decision',
      caption: `Decision: ${DECISION_LABEL[last.decision]}`,
      detail: last.reason,
      traversalId: last.id,
      traversalIndex: traversals.length - 1,
      constraintType: last.constraint_type,
      visibleNodes: last.nodes.length,
      activeEdge: null,
    });
  }

  return steps;
}

export const DECISION_LABEL: Record<GraphTraversal['decision'], string> = {
  excluded: 'Excluded',
  downranked: 'Down-ranked',
  allowed: 'Allowed',
};
