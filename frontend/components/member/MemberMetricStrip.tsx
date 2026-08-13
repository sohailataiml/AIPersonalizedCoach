'use client';

import type { ReactNode } from 'react';

import { Badge, cx } from '@/components/ui/primitives';
import type { MemberHistory, MemberSummary } from '@/lib/types';

/**
 * KPI strip.
 *
 * Every figure is a real backend value. The sparklines plot the actual
 * observation arrays from /history (4 adherence weeks, 7 sleep nights) - the
 * counts are what the data holds, not a fixed window, and the labels say so.
 */
export function MemberMetricStrip({
  member,
  history,
}: {
  member: MemberSummary;
  history?: MemberHistory;
}) {
  const injury = member.active_injuries[0];
  const adherenceValues = (history?.adherence ?? []).map((point) => point.pct);
  const sleepValues = (history?.sleep ?? []).map((point) => point.hours);

  const adherenceTone = toneForAdherence(member.latest_adherence_pct);
  const churnTone = toneForChurn(member.churn_risk_level);
  const sleepBelowTarget =
    member.avg_sleep_hours != null && member.avg_sleep_hours < 7;

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
      <Metric
        label="Active injury"
        value={injury ? titleCase(injury.region) : 'None'}
        valueClass={injury ? 'text-danger-600' : 'text-safe-600'}
        sub={
          injury
            ? [injury.severity, injury.status].filter(Boolean).join(' · ')
            : 'No recorded injuries'
        }
        aside={injury ? <JointGlyph /> : null}
      />

      <Metric
        label={`Adherence (${adherenceValues.length}w)`}
        value={
          member.latest_adherence_pct != null
            ? `${member.latest_adherence_pct}%`
            : '—'
        }
        valueClass={adherenceTone.text}
        sub={
          member.adherence_trend
            ? `${member.adherence_trend} ${member.adherence_trend === 'declining' ? '↓' : member.adherence_trend === 'improving' ? '↑' : '→'}`
            : undefined
        }
        subClass={adherenceTone.text}
        aside={
          adherenceValues.length > 1 ? (
            <Sparkline values={adherenceValues} stroke="#ef4444" />
          ) : null
        }
      />

      <Metric
        label="Churn risk"
        value={member.churn_risk_level ? titleCase(member.churn_risk_level) : '—'}
        valueClass={churnTone.text}
        sub={member.churn_risk_level ? 'watch closely' : undefined}
        aside={<RiskGauge level={member.churn_risk_level} />}
      />

      <Metric
        label={`Avg sleep (${sleepValues.length}d)`}
        value={member.avg_sleep_hours != null ? `${member.avg_sleep_hours}h` : '—'}
        valueClass={sleepBelowTarget ? 'text-caution-600' : 'text-safe-600'}
        sub={sleepBelowTarget ? 'below target' : 'on target'}
        aside={sleepValues.length ? <SleepBars values={sleepValues} /> : null}
      />

      <div className="card col-span-2 px-4 py-3 md:col-span-3 xl:col-span-1">
        <div className="label-caps">Equipment</div>
        <div className="mt-2 flex flex-wrap gap-1">
          {member.equipment_available.slice(0, 4).map((item) => (
            <Badge key={item} tone="neutral">
              {item}
            </Badge>
          ))}
          {member.equipment_available.length > 4 ? (
            <Badge
              tone="neutral"
              title={member.equipment_available.slice(4).join(', ')}
            >
              +{member.equipment_available.length - 4}
            </Badge>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  sub,
  aside,
  valueClass,
  subClass,
}: {
  label: string;
  value: string;
  sub?: string;
  aside?: ReactNode;
  valueClass?: string;
  subClass?: string;
}) {
  return (
    <div className="card flex items-start justify-between gap-2 px-4 py-3">
      <div className="min-w-0">
        <div className="label-caps">{label}</div>
        <div className={cx('mt-1 truncate text-lg font-semibold tracking-tight', valueClass)}>
          {value}
        </div>
        {sub ? (
          <div className={cx('mt-0.5 truncate text-2xs text-ink-500', subClass)}>{sub}</div>
        ) : null}
      </div>
      {aside ? <div className="shrink-0 pt-1">{aside}</div> : null}
    </div>
  );
}

/** Inline SVG sparkline over the real observation array. */
function Sparkline({ values, stroke }: { values: number[]; stroke: string }) {
  const width = 62;
  const height = 26;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;

  const points = values.map((value, index) => {
    const x = (index / (values.length - 1)) * width;
    const y = height - ((value - min) / span) * (height - 4) - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Trend: ${values.join(', ')}`}
      className="overflow-visible"
    >
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke={stroke}
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle
        cx={points[points.length - 1]?.split(',')[0]}
        cy={points[points.length - 1]?.split(',')[1]}
        r="2"
        fill={stroke}
      />
    </svg>
  );
}

function SleepBars({ values }: { values: number[] }) {
  const max = Math.max(...values, 8);
  return (
    <div
      className="flex h-[26px] items-end gap-[3px]"
      role="img"
      aria-label={`Sleep hours: ${values.join(', ')}`}
    >
      {values.map((value, index) => (
        <span
          key={index}
          className={cx(
            'w-[5px] rounded-sm',
            value < 7 ? 'bg-graph-300' : 'bg-graph-500',
          )}
          style={{ height: `${Math.max(15, (value / max) * 100)}%` }}
        />
      ))}
    </div>
  );
}

function RiskGauge({ level }: { level: string | null }) {
  const fraction =
    level === 'elevated' || level === 'high' ? 0.8 : level === 'moderate' ? 0.5 : 0.2;
  const color = fraction > 0.7 ? '#ef4444' : fraction > 0.4 ? '#f59e0b' : '#10b981';
  const radius = 11;
  const circumference = Math.PI * radius;

  return (
    <svg width="34" height="22" viewBox="0 0 30 18" aria-hidden>
      <path
        d="M3 15a12 12 0 0 1 24 0"
        fill="none"
        stroke="#e3e7ee"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <path
        d="M3 15a12 12 0 0 1 24 0"
        fill="none"
        stroke={color}
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray={`${fraction * circumference} ${circumference}`}
      />
    </svg>
  );
}

function JointGlyph() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" aria-hidden className="text-danger-300">
      <path
        d="M9 3v4.5a3 3 0 0 0 1 2.2l1 1a3 3 0 0 1 1 2.3V21M15 3v4a3 3 0 0 1-1 2.2l-1 1"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
      <circle cx="12" cy="12" r="2.6" fill="currentColor" opacity="0.35" />
    </svg>
  );
}

function toneForAdherence(pct: number | null) {
  if (pct == null) return { text: 'text-ink-700' };
  if (pct >= 80) return { text: 'text-safe-600' };
  if (pct >= 60) return { text: 'text-caution-600' };
  return { text: 'text-danger-600' };
}

function toneForChurn(level: string | null) {
  const normalized = level?.toLowerCase();
  if (normalized === 'elevated' || normalized === 'high') return { text: 'text-danger-600' };
  if (normalized === 'moderate') return { text: 'text-caution-600' };
  return { text: 'text-safe-600' };
}

function titleCase(value: string) {
  return value.replace(/\b\w/g, (character) => character.toUpperCase());
}
