/**
 * Small inline-SVG horizontal bar chart (spec §17: "no decorative pie
 * charts"). The component is display-only: it never computes totals or
 * proportions — the caller passes pre-formatted labels and a max value
 * so the geometry mirrors what the server already validated.
 *
 * The chart is decorative on its own; the accessible summary is the
 * companion data table the caller renders alongside. To make the chart
 * itself screen-reader-friendly we expose an aria-label and a hidden
 * text summary of each bar.
 */

import type { ReactNode } from "react";

export interface BarChartDatum {
  label: string;
  /** Raw numeric size — server-provided, never math'd here. */
  value: number;
  /** Pre-formatted string for the visible legend (e.g. "$1.2M"). */
  display: string;
}

export interface BarChartProps {
  data: BarChartDatum[];
  ariaLabel: string;
  emptyLabel?: ReactNode;
  /** Optional caller-supplied max; otherwise the largest value wins. */
  max?: number;
}

export function BarChart({ data, ariaLabel, emptyLabel, max }: BarChartProps) {
  if (data.length === 0) {
    return (
      <div
        role="img"
        aria-label={ariaLabel}
        className="rounded-panel border border-dashed border-divider p-6 text-body text-text-secondary"
      >
        {emptyLabel ?? "No verified source"}
      </div>
    );
  }

  const upper = Math.max(max ?? 0, ...data.map((d) => d.value), 1);
  const rowH = 28;
  const height = data.length * rowH;

  return (
    <div className="rounded-panel border border-divider bg-surface p-4">
      <svg
        role="img"
        aria-label={ariaLabel}
        viewBox={`0 0 400 ${height}`}
        className="w-full"
        preserveAspectRatio="none"
      >
        {data.map((d, i) => {
          const w = upper === 0 ? 0 : (d.value / upper) * 260;
          const y = i * rowH + 4;
          return (
            <g key={`${d.label}-${i}`}>
              <text
                x={0}
                y={y + 14}
                className="fill-current text-text-secondary"
                fontSize={11}
              >
                {d.label}
              </text>
              <rect
                x={130}
                y={y}
                width={w}
                height={rowH - 10}
                className="fill-current text-primary"
                rx={2}
              />
              <text
                x={130 + w + 4}
                y={y + 14}
                className="fill-current text-text"
                fontSize={11}
              >
                {d.display}
              </text>
            </g>
          );
        })}
      </svg>
      <ul className="sr-only">
        {data.map((d, i) => (
          <li key={`${d.label}-summary-${i}`}>
            {d.label}: {d.display}
          </li>
        ))}
      </ul>
    </div>
  );
}
