/**
 * Ontology-grounding UI tests.
 *
 * Two properties, both about restraint:
 *
 *   1. The coach-facing default stays quiet. A grounded concept shows one short
 *      line; codes, URIs and evidence stay behind a collapsed disclosure.
 *   2. The UI never invents a mapping. A concept the backend sent without
 *      grounding renders no grounding at all — not a placeholder, not an
 *      "unmapped" badge competing for attention.
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { GraphReasoningPanel } from '@/components/graph/GraphReasoningPanel';
import {
  GroundingChip,
  GroundingDetail,
} from '@/components/graph/OntologyGrounding';
import type { ConceptGrounding, GenerateWorkoutResponse } from '@/lib/types';
import { workoutFixture } from './fixtures';

const KNEE: ConceptGrounding = {
  local_id: 'anatomy:knee',
  label: 'Knee',
  ontology_source: 'SNOMED_CT',
  ontology_code: '72696002',
  ontology_term: 'Knee region structure',
  ontology_uri: 'http://snomed.info/id/72696002',
  browser_url:
    'https://evsexplore.semantics.cancer.gov/evsexplore/concept/snomedct_us/72696002',
  mapping_relation: 'exactMatch',
  mapping_evidence: 'NCI EVS snomedct_us 2025_09_01: concept 72696002 active.',
  mapping_version: '2025_09_01',
  status: 'verified',
};

const UNMAPPED: ConceptGrounding = {
  local_id: 'equipment',
  label: 'equipment',
  ontology_source: null,
  ontology_code: null,
  ontology_term: null,
  ontology_uri: null,
  browser_url: null,
  mapping_relation: null,
  mapping_evidence: 'OPE is only distributed through BioPortal, which needs an API key.',
  mapping_version: null,
  status: 'unmapped',
};

function Panel({ result = workoutFixture }: { result?: GenerateWorkoutResponse }) {
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <GraphReasoningPanel
      result={result}
      selectedExerciseId={selected}
      onSelect={setSelected}
    />
  );
}

async function openConcepts() {
  const user = userEvent.setup();
  render(<Panel />);
  await user.click(screen.getByRole('tab', { name: /prompt concepts/i }));
  return user;
}

describe('GroundingChip', () => {
  it('shows the source and mapping relation, not the code', () => {
    render(<GroundingChip grounding={KNEE} />);
    expect(screen.getByText('SNOMED CT')).toBeInTheDocument();
    expect(screen.getByText('exactMatch')).toBeInTheDocument();
    expect(screen.queryByText('72696002')).not.toBeInTheDocument();
  });

  it('renders nothing for a concept with no verified mapping', () => {
    const { container } = render(<GroundingChip grounding={UNMAPPED} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when a relation is missing despite a code', () => {
    const { container } = render(
      <GroundingChip grounding={{ ...KNEE, mapping_relation: null }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe('GroundingDetail', () => {
  it('keeps codes and URIs collapsed by default', () => {
    render(<GroundingDetail grounding={KNEE} />);

    // The summary line is always visible; the code is present in the DOM but
    // inside a closed <details>, which is what "collapsed" means for a
    // disclosure element.
    expect(screen.getAllByText('SNOMED CT').length).toBeGreaterThan(0);
    const disclosure = screen.getByText('Ontology detail').closest('details');
    expect(disclosure).not.toBeNull();
    expect((disclosure as HTMLDetailsElement).open).toBe(false);
    expect(screen.getByText('72696002').closest('details')).toBe(disclosure);
  });

  it('exposes the full auditable mapping when expanded', async () => {
    const user = userEvent.setup();
    render(<GroundingDetail grounding={KNEE} />);
    await user.click(screen.getByText('Ontology detail'));

    expect(screen.getByText('anatomy:knee')).toBeInTheDocument();
    expect(screen.getByText('72696002')).toBeInTheDocument();
    expect(screen.getByText('Knee region structure')).toBeInTheDocument();
    expect(screen.getByText('skos:exactMatch')).toBeInTheDocument();
    expect(screen.getByText('2025_09_01')).toBeInTheDocument();
    expect(screen.getByText(KNEE.mapping_evidence!)).toBeInTheDocument();
  });

  it('links the code to the published concept browser', async () => {
    const user = userEvent.setup();
    render(<GroundingDetail grounding={KNEE} />);
    await user.click(screen.getByText('Ontology detail'));

    const link = screen.getByRole('link', { name: KNEE.ontology_uri! });
    expect(link).toHaveAttribute('href', KNEE.browser_url);
    expect(link).toHaveAttribute('rel', expect.stringContaining('noreferrer'));
  });

  it('renders nothing at all for an unmapped concept', () => {
    const { container } = render(<GroundingDetail grounding={UNMAPPED} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('omits fields the backend left null rather than showing blanks', async () => {
    const user = userEvent.setup();
    render(
      <GroundingDetail
        grounding={{ ...KNEE, mapping_version: null, mapping_evidence: null }}
      />,
    );
    await user.click(screen.getByText('Ontology detail'));

    expect(screen.queryByText('Version')).not.toBeInTheDocument();
    expect(screen.queryByText('Evidence')).not.toBeInTheDocument();
    expect(screen.getByText('72696002')).toBeInTheDocument();
  });
});

describe('Prompt concepts tab grounding', () => {
  it('grounds the clinical concept the coach actually named', async () => {
    await openConcepts();

    const card = screen.getByText('“left knee”').closest('li') as HTMLElement;
    expect(card).not.toBeNull();
    expect(within(card).getAllByText('SNOMED CT').length).toBeGreaterThan(0);
    expect(within(card).getAllByText('exactMatch').length).toBeGreaterThan(0);
  });

  it('shows no grounding for concepts the backend did not ground', async () => {
    await openConcepts();

    for (const phrase of ['“dumbbells”', '“kettlebell”', '“45-minute lower-body”']) {
      const card = screen.getByText(phrase).closest('li') as HTMLElement;
      expect(within(card).queryByText('SNOMED CT')).not.toBeInTheDocument();
      expect(within(card).queryByText('Ontology detail')).not.toBeInTheDocument();
    }
  });

  it('keeps the local canonical id visible alongside the mapping', async () => {
    await openConcepts();

    const card = screen.getByText('“left knee”').closest('li') as HTMLElement;
    // The local id is what the system reasons on. It sits in the primary view;
    // the ontology code is one disclosure deeper and never replaces it.
    const localId = within(card).getByText('anatomy.knee');
    expect(localId).toBeInTheDocument();
    expect(localId.closest('details')).toBeNull();
    expect(within(card).getByText('72696002').closest('details')).not.toBeNull();
  });

  it('degrades cleanly when the backend omits grounding entirely', async () => {
    const stripped: GenerateWorkoutResponse = {
      ...workoutFixture,
      graph_reasoning: {
        ...workoutFixture.graph_reasoning!,
        prompt_concepts: workoutFixture.graph_reasoning!.prompt_concepts.map(
          ({ grounding: _grounding, ...rest }) => rest,
        ),
      },
    };

    const user = userEvent.setup();
    render(
      <GraphReasoningPanel
        result={stripped}
        selectedExerciseId={null}
        onSelect={() => {}}
      />,
    );
    await user.click(screen.getByRole('tab', { name: /prompt concepts/i }));

    expect(screen.getByText('“left knee”')).toBeInTheDocument();
    expect(screen.queryByText('SNOMED CT')).not.toBeInTheDocument();
  });
});
