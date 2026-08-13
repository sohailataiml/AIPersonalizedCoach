'use client';

import { Chip } from '@/components/ui/primitives';

export const QUICK_PROMPTS = [
  'Show me the brief',
  "How's adherence trending?",
  'Sleep this week',
  'What changed since last week?',
  'Is there any churn risk?',
  'Show message pattern',
] as const;

export function QuickPrompts({
  onSelect,
  disabled,
}: {
  onSelect: (prompt: string) => void;
  disabled?: boolean;
}) {
  return (
    <section aria-label="Quick prompts" className="border-b border-ink-200 px-5 py-3">
      <ul className="flex flex-wrap gap-1.5">
        {QUICK_PROMPTS.map((prompt) => (
          <li key={prompt}>
            <Chip onClick={() => onSelect(prompt)} disabled={disabled}>
              {prompt}
            </Chip>
          </li>
        ))}
      </ul>
    </section>
  );
}
