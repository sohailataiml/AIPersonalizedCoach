'use client';

import type { ButtonHTMLAttributes, ReactNode } from 'react';

export function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(' ');
}

export type Tone = 'neutral' | 'brand' | 'safe' | 'caution' | 'danger' | 'graph';

const TONE: Record<Tone, string> = {
  neutral: 'bg-ink-100 text-ink-600 ring-ink-200',
  brand: 'bg-brand-50 text-brand-700 ring-brand-200',
  safe: 'bg-safe-50 text-safe-700 ring-safe-200',
  caution: 'bg-caution-50 text-caution-700 ring-caution-200',
  danger: 'bg-danger-50 text-danger-700 ring-danger-200',
  graph: 'bg-graph-50 text-graph-700 ring-graph-200',
};

export function Badge({
  children,
  tone = 'neutral',
  className,
  title,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cx(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5',
        'text-2xs font-medium ring-1 ring-inset',
        TONE[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost';
  size?: 'sm' | 'md';
}

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  className,
  ...rest
}: ButtonProps) {
  const variants = {
    primary:
      'bg-navy-900 text-white hover:bg-navy-800 active:bg-navy-950 disabled:bg-ink-300 disabled:text-ink-500',
    secondary:
      'border border-ink-300 bg-white text-ink-700 hover:bg-ink-50 hover:border-ink-400 active:bg-ink-100',
    ghost: 'text-ink-600 hover:bg-ink-100 hover:text-ink-800',
  }[variant];

  const sizes = {
    sm: 'px-2.5 py-1.5 text-2xs',
    md: 'px-3.5 py-2 text-xs',
  }[size];

  return (
    <button
      {...rest}
      className={cx(
        'inline-flex items-center justify-center gap-1.5 rounded-lg font-semibold',
        'transition-colors duration-150 disabled:cursor-not-allowed',
        variants,
        sizes,
        className,
      )}
    >
      {children}
    </button>
  );
}

/** Small pill used for scenario presets and copilot quick prompts. */
export function Chip({
  children,
  onClick,
  active,
  disabled,
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  active?: boolean;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-pressed={active}
      className={cx(
        'rounded-full border px-2.5 py-1 text-2xs font-medium transition-colors duration-150',
        'disabled:cursor-not-allowed disabled:opacity-50',
        active
          ? 'border-navy-800 bg-navy-900 text-white'
          : 'border-ink-300 bg-white text-ink-600 hover:border-brand-400 hover:text-brand-700',
      )}
    >
      {children}
    </button>
  );
}

export function Card({
  children,
  className,
  id,
}: {
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} className={cx('card', className)}>
      {children}
    </section>
  );
}

export function CardHead({
  step,
  title,
  right,
}: {
  step?: number;
  title: string;
  right?: ReactNode;
}) {
  return (
    <header className="card-head">
      <div className="flex items-center gap-2">
        {step ? <span className="step-badge">{step}</span> : null}
        <h2 className="section-title">{title}</h2>
      </div>
      {right}
    </header>
  );
}

export function Spinner({ label, className }: { label?: string; className?: string }) {
  return (
    <div className={cx('flex items-center gap-2 text-xs text-ink-500', className)} role="status">
      <span
        aria-hidden
        className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-ink-200 border-t-brand-500"
      />
      {label ? <span>{label}</span> : null}
      <span className="sr-only">Loading</span>
    </div>
  );
}

export function EmptyState({
  title,
  body,
  icon,
}: {
  title: string;
  body: string;
  icon?: ReactNode;
}) {
  return (
    <div className="px-5 py-12 text-center">
      {icon ? <div className="mb-2 flex justify-center text-ink-300">{icon}</div> : null}
      <p className="text-xs font-semibold text-ink-700">{title}</p>
      <p className="mx-auto mt-1 max-w-xs text-2xs leading-relaxed text-ink-500">{body}</p>
    </div>
  );
}

export function ErrorNote({
  message,
  className,
}: {
  message: string;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cx(
        'flex items-start gap-2 rounded-lg border border-danger-200 bg-danger-50 px-3 py-2.5',
        'text-2xs leading-relaxed text-danger-700',
        className,
      )}
    >
      <span aria-hidden className="mt-px font-semibold">
        !
      </span>
      <span>{message}</span>
    </div>
  );
}

/**
 * Status is never conveyed by colour alone: every state carries a glyph and a
 * text label alongside its tone.
 */
export function StatusPill({
  status,
}: {
  status: 'safe' | 'cautioned' | 'excluded';
}) {
  const map = {
    safe: { tone: 'safe' as const, glyph: '✓', label: 'Safe' },
    cautioned: { tone: 'caution' as const, glyph: '!', label: 'Down-ranked' },
    excluded: { tone: 'danger' as const, glyph: '✕', label: 'Excluded' },
  }[status];

  return (
    <Badge tone={map.tone}>
      <span aria-hidden>{map.glyph}</span>
      {map.label}
    </Badge>
  );
}
