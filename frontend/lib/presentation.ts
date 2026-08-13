/**
 * Presentation helpers.
 *
 * Everything here is a *transform of real backend data* - shortening verbose
 * reason strings, mapping rule ids to labels, formatting prescriptions. Nothing
 * here invents a fact, and no safety logic lives here: the backend has already
 * decided status, and this module only chooses how to say it.
 */

import type { ProvenanceItem, ResolvedConcept, WorkoutExercise } from './types';

export type DecisionStatus = 'safe' | 'cautioned' | 'excluded';

/** Rule ids that represent a graph-derived caution rather than a removal. */
const CAUTION_RULES = new Set([
  'injury_region_stress',
  'injury_contraindicated_pattern',
  'injury_side_specific',
  'unknown_anatomy',
]);

export function statusOf(item: ProvenanceItem): DecisionStatus {
  if (item.decision === 'filtered') return 'excluded';
  if (item.decision === 'downranked') return 'cautioned';
  // In the plan, but the graph still flagged something worth showing.
  return item.rule_ids.some((rule) => CAUTION_RULES.has(rule)) ? 'cautioned' : 'safe';
}

export const STATUS_LABEL: Record<DecisionStatus, string> = {
  safe: 'Safe',
  cautioned: 'Down-ranked',
  excluded: 'Excluded',
};

/**
 * Human-readable rule labels. Used as compact tags so a coach does not have to
 * read a full sentence to see why something was flagged.
 */
export const RULE_LABEL: Record<string, string> = {
  equipment_unavailable: 'Equipment unavailable',
  explicit_exclusion: 'Coach exclusion',
  injury_contraindicated_pattern: 'Contraindicated pattern',
  injury_region_stress: 'Injured-region stress',
  injury_side_specific: 'Injured side',
  unknown_anatomy: 'Anatomy unknown',
  preference_dislike: 'Member dislikes',
  goal_alignment: 'Goal aligned',
  history_recency: 'Recently performed',
};

export function ruleLabel(rule: string): string {
  return RULE_LABEL[rule] ?? rule.replace(/_/g, ' ');
}

/**
 * A one-line "why" for the decision table.
 *
 * Prefers the backend's own first reason, trimmed to a scannable length. We
 * shorten wording but never change meaning, and the full reason list is always
 * visible in the provenance panel beside the table.
 */
export function summarize(item: ProvenanceItem): string {
  const first = item.reasons[0];
  if (!first) {
    return item.decision === 'filtered'
      ? 'Removed by the safety engine.'
      : 'No graph contraindication found.';
  }
  return tighten(first);
}

const SHORTENINGS: Array<[RegExp, string]> = [
  [/^Bodyweight - no equipment required\.$/, 'Bodyweight; no equipment needed.'],
  [/^No graph-derived contraindication against .*$/, 'No graph contraindication for this injury.'],
  [
    /^Catalog lists no joints for this exercise, so it cannot be certified.*$/,
    'No joint data in catalog; cannot be certified safe.',
  ],
  [/ Preference affects ranking only - this is not a safety exclusion\./, ''],
  [/, so this is down-ranked and needs a range-of-motion caveat rather than removed\./, '.'],
  [/ which is inside the region affected by /, ' inside injured region: '],
];

function tighten(text: string): string {
  let out = text;
  for (const [pattern, replacement] of SHORTENINGS) {
    out = out.replace(pattern, replacement);
  }
  out = out.trim();
  return out.length > 130 ? `${out.slice(0, 127).trimEnd()}…` : out;
}

/** Short tags shown on an exercise row inside the plan. */
export function exerciseTags(item: ProvenanceItem | undefined): string[] {
  if (!item) return [];
  const tags: string[] = [];

  if (item.reasons.some((r) => r.startsWith('supports goal'))) tags.push('Goal aligned');
  if (item.reasons.some((r) => r.includes('matches requested focus'))) tags.push('On focus');
  if (item.rule_ids.includes('preference_dislike')) tags.push('Member dislikes');
  if (statusOf(item) === 'safe' && !tags.length) tags.push('Graph safe');

  return tags.slice(0, 2);
}

/** "3 × 8-12 · rest 75s" or "45s · rest 15s" - built only from returned fields. */
export function formatPrescription(exercise: WorkoutExercise): string {
  const parts: string[] = [];
  if (exercise.sets && exercise.reps) parts.push(`${exercise.sets} × ${exercise.reps}`);
  else if (exercise.sets && exercise.duration_seconds)
    parts.push(`${exercise.sets} × ${exercise.duration_seconds}s`);
  else if (exercise.duration_seconds) parts.push(`${exercise.duration_seconds}s`);
  else if (exercise.reps) parts.push(exercise.reps);
  if (exercise.rest_seconds) parts.push(`rest ${exercise.rest_seconds}s`);
  return parts.join(' · ');
}

/**
 * Estimated section minutes, derived from the prescription the backend
 * returned. Marked "est." in the UI because it is arithmetic on sets/reps/rest,
 * not a value the backend computed.
 */
export function estimateMinutes(exercises: WorkoutExercise[]): number {
  const seconds = exercises.reduce((total, exercise) => {
    const sets = exercise.sets ?? 1;
    const work = exercise.duration_seconds ?? estimateRepSeconds(exercise.reps);
    const rest = exercise.rest_seconds ?? 0;
    return total + sets * (work + rest);
  }, 0);
  return Math.max(1, Math.round(seconds / 60));
}

function estimateRepSeconds(reps: string | null): number {
  if (!reps) return 40;
  const highest = reps
    .split(/[^0-9]+/)
    .filter(Boolean)
    .map(Number);
  const count = highest.length ? Math.max(...highest) : 10;
  return count * 3; // ~3s per controlled rep
}

export const CONCEPT_METHOD_STYLE: Record<
  ResolvedConcept['method'],
  { label: string; className: string }
> = {
  exact: { label: 'exact', className: 'bg-safe-50 text-safe-700 ring-safe-200' },
  alias: { label: 'alias', className: 'bg-brand-50 text-brand-700 ring-brand-200' },
  fuzzy: { label: 'fuzzy', className: 'bg-caution-50 text-caution-700 ring-caution-200' },
  embedding: { label: 'embedding', className: 'bg-graph-50 text-graph-700 ring-graph-200' },
  unresolved: { label: 'unresolved', className: 'bg-danger-50 text-danger-700 ring-danger-200' },
};

/** "anatomy:knee" -> "anatomy.knee" for a calmer chip. */
export function conceptLabel(canonicalId: string | null): string {
  return canonicalId ? canonicalId.replace(':', '.') : 'unresolved';
}

export function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export function relativeTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const minutes = Math.round((Date.now() - date.getTime()) / 60000);
  if (minutes < 60) return `${Math.max(1, minutes)}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}
