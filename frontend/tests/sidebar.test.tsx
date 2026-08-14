import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Sidebar } from '@/components/app-shell/Sidebar';

/**
 * These cover the three ways the rail was previously broken:
 *
 * 1. Workouts and Copilot sit in the same grid row on wide viewports, so
 *    scrolling alone produced no observable change. Focus is what makes the
 *    click legible.
 * 2. Graph/Quality used `window.location.href`, a full document reload.
 * 3. The highlight tracked the last click rather than the page.
 */

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

/** The dashboard sections the rail scrolls to. */
function mountSections() {
  document.body.insertAdjacentHTML(
    'beforeend',
    `<header id="overview" tabindex="-1"></header>
     <div id="workout-generator" tabindex="-1"></div>
     <div id="copilot" tabindex="-1"></div>`,
  );
}

beforeEach(() => {
  push.mockClear();
  // jsdom implements neither, and the component must not depend on them.
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  document.body.innerHTML = '';
});

describe('Sidebar navigation', () => {
  it('moves focus to the workout generator so the click is visible', async () => {
    mountSections();
    render(<Sidebar />);

    await userEvent.click(screen.getByRole('button', { name: /Workouts/ }));

    expect(document.activeElement).toBe(document.getElementById('workout-generator'));
  });

  it('distinguishes Copilot from Workouts even when neither scrolls', async () => {
    mountSections();
    render(<Sidebar />);

    await userEvent.click(screen.getByRole('button', { name: /Workouts/ }));
    await userEvent.click(screen.getByRole('button', { name: /Copilot/ }));

    // The regression: both share an offsetTop, so scroll position alone could
    // not tell these apart.
    expect(document.activeElement).toBe(document.getElementById('copilot'));
  });

  it('sends Overview to the top of the page and focuses the header', async () => {
    mountSections();
    render(<Sidebar />);

    await userEvent.click(screen.getByRole('button', { name: /Overview/ }));

    expect(window.scrollTo).toHaveBeenCalledWith(
      expect.objectContaining({ top: 0 }),
    );
    expect(document.activeElement).toBe(document.getElementById('overview'));
  });

  it('marks the clicked destination as the current page', async () => {
    mountSections();
    render(<Sidebar />);

    await userEvent.click(screen.getByRole('button', { name: /Copilot/ }));

    expect(screen.getByRole('button', { name: /Copilot/ })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('routes to Graph client-side rather than reloading the document', async () => {
    render(<Sidebar />);

    await userEvent.click(screen.getByRole('button', { name: /Graph/ }));

    expect(push).toHaveBeenCalledWith('/graph');
  });

  it('routes to Quality client-side', async () => {
    render(<Sidebar />);

    await userEvent.click(screen.getByRole('button', { name: /Quality/ }));

    expect(push).toHaveBeenCalledWith('/system');
  });

  it('reflects the route it was rendered on', () => {
    render(<Sidebar current="graph" />);

    expect(screen.getByRole('button', { name: /Graph/ })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('leaves unbuilt destinations disabled and honest', async () => {
    render(<Sidebar />);

    const members = screen.getByRole('button', { name: /Members/ });
    expect(members).toBeDisabled();
    expect(members).toHaveAttribute('title', expect.stringContaining('not in this build'));

    await userEvent.click(members);
    expect(push).not.toHaveBeenCalled();
  });

  it('does not throw when the sections are absent', async () => {
    render(<Sidebar current="system" />);

    await userEvent.click(screen.getByRole('button', { name: /Workouts/ }));

    expect(push).not.toHaveBeenCalled();
  });
});
