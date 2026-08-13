'use client';

import { Badge } from '@/components/ui/primitives';
import type { ConceptGrounding, MappingRelation } from '@/lib/types';

/**
 * Compact ontology-grounding surface.
 *
 * The design constraint is that a coach should never have to read a SNOMED
 * code. The default state is one short line — *"SNOMED CT · exactMatch"* — and
 * the code, URI, evidence and version live behind a collapsed
 * `<details>` for the reviewer who wants to audit the mapping.
 *
 * Everything here is rendered verbatim from the backend payload. The component
 * derives no clinical meaning from a code and never uses grounding to infer
 * whether something is safe.
 */

const RELATION_COPY: Record<MappingRelation, { label: string; hint: string }> = {
  exactMatch: {
    label: 'exactMatch',
    hint: 'The local concept and the published concept denote the same thing.',
  },
  closeMatch: {
    label: 'closeMatch',
    hint: 'The local concept is a coarser product grouping that overlaps the published concept.',
  },
  broadMatch: {
    label: 'broadMatch',
    hint: 'The published concept is broader — our concept is a narrower part of it.',
  },
};

/** The one-line chip. Safe to render inline next to a concept or node label. */
export function GroundingChip({ grounding }: { grounding: ConceptGrounding }) {
  if (grounding.status !== 'verified' || !grounding.mapping_relation) return null;
  const relation = RELATION_COPY[grounding.mapping_relation];

  return (
    <Badge tone="graph" title={relation.hint}>
      <span className="font-semibold">{sourceLabel(grounding.ontology_source)}</span>
      <span aria-hidden className="text-graph-400">
        ·
      </span>
      <span>{relation.label}</span>
    </Badge>
  );
}

/**
 * Chip plus collapsed technical detail.
 *
 * `label` names the concept the mapping belongs to, so the disclosure still
 * makes sense when several are listed together.
 */
export function GroundingDetail({
  grounding,
  label,
}: {
  grounding: ConceptGrounding;
  label?: string;
}) {
  if (grounding.status !== 'verified' || !grounding.mapping_relation) return null;

  return (
    <div className="mt-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        {label ? <span className="text-[10.5px] text-ink-500">{label}</span> : null}
        <GroundingChip grounding={grounding} />
      </div>

      <details className="group mt-1">
        <summary className="cursor-pointer list-none text-[9.5px] text-ink-400 transition-colors hover:text-ink-600">
          <span className="group-open:hidden">Ontology detail</span>
          <span className="hidden group-open:inline">Hide ontology detail</span>
        </summary>

        <dl className="mt-1 space-y-0.5 rounded-lg bg-ink-50 p-2">
          <Row term="Local ID" value={grounding.local_id} mono />
          <Row term="Ontology" value={sourceLabel(grounding.ontology_source)} />
          <Row term="Code" value={grounding.ontology_code} mono />
          <Row term="Term" value={grounding.ontology_term} />
          <Row term="Mapping" value={`skos:${grounding.mapping_relation}`} mono />
          <Row term="Version" value={grounding.mapping_version} mono />
          {grounding.ontology_uri ? (
            <div className="flex gap-1.5">
              <dt className="w-16 shrink-0 text-[9.5px] text-ink-400">URI</dt>
              <dd className="min-w-0 break-all font-mono text-[9.5px] text-ink-600">
                {grounding.browser_url ? (
                  <a
                    href={grounding.browser_url}
                    target="_blank"
                    rel="noreferrer"
                    className="underline decoration-dotted underline-offset-2 hover:text-graph-700"
                  >
                    {grounding.ontology_uri}
                  </a>
                ) : (
                  grounding.ontology_uri
                )}
              </dd>
            </div>
          ) : null}
          {grounding.mapping_evidence ? (
            <div className="pt-1">
              <dt className="text-[9.5px] text-ink-400">Evidence</dt>
              <dd className="text-[9.5px] leading-relaxed text-ink-600">
                {grounding.mapping_evidence}
              </dd>
            </div>
          ) : null}
        </dl>
      </details>
    </div>
  );
}

function Row({
  term,
  value,
  mono = false,
}: {
  term: string;
  value: string | null;
  mono?: boolean;
}) {
  if (!value) return null;
  return (
    <div className="flex gap-1.5">
      <dt className="w-16 shrink-0 text-[9.5px] text-ink-400">{term}</dt>
      <dd
        className={
          mono
            ? 'min-w-0 break-all font-mono text-[9.5px] text-ink-600'
            : 'min-w-0 text-[9.5px] text-ink-600'
        }
      >
        {value}
      </dd>
    </div>
  );
}

/** "SNOMED_CT" is a YAML key, not something to show a coach. */
export function sourceLabel(source: string | null): string {
  if (!source) return 'Unmapped';
  return source.replace(/_/g, ' ').replace(/\bCT\b/, 'CT');
}
