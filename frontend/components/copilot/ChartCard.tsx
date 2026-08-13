'use client';

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { ChartPayload } from '@/lib/types';

/**
 * Charts render a payload computed in Python. The model never emits chart data,
 * so what is plotted is exactly what the member graph holds - a chart is an
 * assertion about data and is treated with the same care as a sentence.
 */
export function ChartCard({ chart }: { chart: ChartPayload }) {
  const data = chart.x.map((label, index) => {
    const row: Record<string, string | number> = { label };
    for (const series of chart.series) {
      row[series.name] = series.values[index];
    }
    return row;
  });

  const axisProps = {
    stroke: 'currentColor',
    fontSize: 11,
    tickLine: false,
    axisLine: false,
  } as const;

  return (
    <figure className="rounded-xl border border-ink-200 bg-white px-3 pb-2 pt-3">
      <figcaption className="mb-2 px-1 text-2xs font-semibold text-ink-700">
        {chart.title}
        {chart.y_label ? (
          <span className="ml-1.5 font-normal text-ink-400">({chart.y_label})</span>
        ) : null}
      </figcaption>

      <div className="h-[168px] w-full text-ink-400">
        <ResponsiveContainer width="100%" height="100%">
          {chart.type === 'line' ? (
            <LineChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 4" vertical={false} opacity={0.35} />
              <XAxis dataKey="label" {...axisProps} tickFormatter={shorten} />
              <YAxis
                {...axisProps}
                domain={chart.y_domain ?? ['auto', 'auto']}
                width={44}
              />
              <Tooltip content={<ChartTooltip unit={chart.y_label} />} />
              {chart.series.map((series) => (
                <Line
                  key={series.name}
                  type="monotone"
                  dataKey={series.name}
                  stroke="#22a18c"
                  strokeWidth={2}
                  dot={{ r: 3, fill: '#22a18c' }}
                  activeDot={{ r: 5 }}
                />
              ))}
            </LineChart>
          ) : (
            <BarChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 4" vertical={false} opacity={0.35} />
              <XAxis dataKey="label" {...axisProps} tickFormatter={shorten} />
              <YAxis
                {...axisProps}
                domain={chart.y_domain ?? ['auto', 'auto']}
                width={44}
              />
              <Tooltip
                cursor={{ fill: 'rgba(34,161,140,0.08)' }}
                content={<ChartTooltip unit={chart.y_label} />}
              />
              {chart.series.map((series) => (
                <Bar
                  key={series.name}
                  dataKey={series.name}
                  fill="#44bda6"
                  radius={[3, 3, 0, 0]}
                />
              ))}
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

function shorten(value: string) {
  return value.replace('Week of ', '').replace('Night ', 'N');
}

function ChartTooltip({
  active,
  payload,
  label,
  unit,
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number }>;
  label?: string;
  unit?: string | null;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-ink-200 bg-white px-2.5 py-1.5 text-2xs shadow-pop">
      <div className="font-medium">{label}</div>
      {payload.map((entry) => (
        <div key={entry.name} className="text-ink-500">
          {entry.name}: <span className="font-mono">{entry.value}</span>
          {unit ? ` ${unit}` : ''}
        </div>
      ))}
    </div>
  );
}
