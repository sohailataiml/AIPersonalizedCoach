/**
 * Deployment-surface tests.
 *
 * Two properties that only matter once this leaves a laptop:
 *
 * 1. The Technical Details panel reports deployment facts from the **backend**
 *    — environment, whether the graph is seeded, how many ontology mappings —
 *    so an interviewer can point at something real.
 * 2. Nothing shipped to the browser carries a graph credential, a Bolt URI or
 *    an internal hostname. The API client is the only way out, and it speaks
 *    HTTPS to FastAPI.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { TechnicalDetails } from '@/components/provenance/TechnicalDetails';
import type { HealthResponse } from '@/lib/types';

const RENDER_HEALTH: HealthResponse = {
  status: 'ok',
  graph_backend: 'neo4j',
  llm_provider: 'stub',
  graph_stats: { 'node:Exercise': 50, 'node:OntologyConcept': 29 },
  environment: 'render',
  graph_seeded: true,
  seed_version: '2026.08.13-1',
  ontology_mappings: 29,
};

async function open(health: HealthResponse) {
  const user = userEvent.setup();
  const { container } = render(<TechnicalDetails result={null} health={health} />);
  const summary = container.querySelector('summary');
  if (summary) await user.click(summary);
  return container;
}

describe('Technical details on a deployment', () => {
  it('reports the environment and graph backend from the backend', async () => {
    await open(RENDER_HEALTH);
    expect(screen.getByText('render')).toBeInTheDocument();
    expect(screen.getByText('29 verified')).toBeInTheDocument();
  });

  it('states whether the graph is seeded', async () => {
    await open(RENDER_HEALTH);
    expect(screen.getByText('graph seeded')).toBeInTheDocument();
    expect(screen.getByText('yes')).toBeInTheDocument();
  });

  it('says no when the graph is not seeded rather than hiding it', async () => {
    await open({ ...RENDER_HEALTH, graph_seeded: false });
    expect(screen.getByText('no')).toBeInTheDocument();
  });

  it('degrades to local defaults on an older backend', async () => {
    const legacy: HealthResponse = {
      status: 'ok',
      graph_backend: 'memory',
      llm_provider: 'stub',
      graph_stats: { 'node:Exercise': 50 },
    };
    await open(legacy);
    expect(screen.getByText('local')).toBeInTheDocument();
  });

  it('never renders a hostname, URI or credential', async () => {
    const container = await open(RENDER_HEALTH);
    const text = (container.textContent ?? '').toLowerCase();
    for (const forbidden of ['bolt://', 'neo4j://', 'password', 'onrender.com', '7687']) {
      expect(text).not.toContain(forbidden);
    }
  });
});
