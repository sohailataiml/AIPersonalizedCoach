'use client';

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { formatDate } from '@/lib/presentation';
import type { MemberHistory } from '@/lib/types';

/**
 * Adherence trend from the member graph.
 *
 * Plots exactly the observations that exist - the supplied member has 4 weekly
 * values, so the heading says "last 4 weeks" rather than assuming a fixed
 * window. A text summary accompanies the chart so the trend is available
 * without reading the plot.
 */
export function AdherenceChart({ history }: { history?: MemberHistory }) {
  const points = history?.adherence ?? [];

  if (points.length < 2) {
    return (
      <section aria-label="Adherence trend" className="border-b border-ink-200 px-5 py-3.5">
        <div className="label-caps mb-1">Adherence</div>
        <p className="text-2xs text-ink-500">
          {points.length === 1
            ? `Only one weekly observation on record (${points[0].pct}%). A trend needs at least two.`
            : 'No adherence observations recorded for this member.'}
        </p>
      </section>
    );
  }

  const data = points.map((point) => ({
    label: formatDate(point.week_of),
    week: point.week_of,
    pct: point.pct,
  }));

  const first = points[0].pct;
  const last = points[points.length - 1].pct;
  const delta = Math.round((last - first) * 10) / 10;
  const direction = delta < 0 ? 'declining' : delta > 0 ? 'improving' : 'flat';
  const stroke = delta < 0 ? '#ef4444' : delta > 0 ? '#10b981' : '#697586';

  return (
    <section aria-label="Adherence trend" className="border-b border-ink-200 px-5 py-3.5">
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <div className="label-caps">Adherence (last {points.length} weeks)</div>
        <span className="text-2xs font-medium text-ink-500">
          {first}% → {last}%{' '}
          <span className={delta < 0 ? 'text-danger-600' : 'text-safe-600'}>
            ({delta > 0 ? '+' : ''}
            {delta} pts)
          </span>
        </span>
      </div>

      {/* Text alternative to the plot. */}
      <p className="sr-only">
        Weekly completion is {direction}, from {first} percent in the week of{' '}
        {points[0].week_of} to {last} percent in the week of{' '}
        {points[points.length - 1].week_of}.
      </p>

      <div className="h-[150px] w-full text-ink-400">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 10, left: -22, bottom: 0 }}>
            <CartesianGrid strokeDasharray="2 4" vertical={false} stroke="#e3e7ee" />
            <XAxis
              dataKey="label"
              stroke="currentColor"
              fontSize={10}
              tickLine={false}
              axisLine={false}
              dy={4}
            />
            <YAxis
              stroke="currentColor"
              fontSize={10}
              tickLine={false}
              axisLine={false}
              domain={[0, 100]}
              ticks={[0, 25, 50, 75, 100]}
              width={40}
              tickFormatter={(value) => `${value}%`}
            />
            <Tooltip content={<ChartTooltip />} />
            <Line
              type="monotone"
              dataKey="pct"
              name="Completion"
              stroke={stroke}
              strokeWidth={2}
              dot={{ r: 3, fill: stroke, strokeWidth: 0 }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: { week: string; pct: number } }>;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded-lg border border-ink-200 bg-white px-2.5 py-1.5 text-2xs shadow-pop">
      <div className="font-medium text-navy-900">Week of {point.week}</div>
      <div className="text-ink-500">
        Completion <span className="font-mono">{point.pct}%</span>
      </div>
    </div>
  );
}
