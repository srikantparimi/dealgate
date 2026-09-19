/**
 * BarChart — v2.1 chart primitive.
 *
 * Inline SVG, up to two series in fixed order (`chartSeries1`,
 * `chartSeries2`), a floor drawn as a text-colored horizontal line, a red
 * value label only where the forecast is below the floor, and a hover
 * tooltip. A `showTable` prop swaps to an accessible summary table for
 * users who prefer the numbers.
 *
 * All arithmetic in this component is display-only. Any percentage,
 * currency or margin value passed in must have been computed upstream
 * with Decimal (per DealGate rule 2).
 */
import { useMemo, useState } from "react";
import { cn } from "../lib/cn";

export interface BarChartDatum {
  label: string;
  /** Primary series value. */
  value: number;
  /** Optional second series value; renders as a grouped bar. */
  value2?: number;
  /** Optional per-point floor override; falls back to the top-level floor. */
  floor?: number;
}

export interface BarChartProps {
  data: BarChartDatum[];
  /** Optional axis floor (drawn as a text-colored horizontal line). */
  floor?: number;
  /** Human labels for the two series (used in tooltip + legend). */
  seriesLabels?: [string, string?];
  /** Formatter for values (default: two decimals). */
  format?: (n: number) => string;
  /** Toggle the accessible table view. */
  showTable?: boolean;
  className?: string;
  /** Accessible label for the chart region. */
  ariaLabel?: string;
}

const CHART_WIDTH = 480;
const CHART_HEIGHT = 220;
const PAD_TOP = 24;
const PAD_BOTTOM = 40;
const PAD_LEFT = 40;
const PAD_RIGHT = 12;

export function BarChart({
  data,
  floor,
  seriesLabels = ["Series 1", "Series 2"],
  format = (n) => n.toFixed(2),
  showTable = false,
  className,
  ariaLabel = "Bar chart",
}: BarChartProps) {
  const [hover, setHover] = useState<number | null>(null);

  const { max, groups } = useMemo(() => {
    let m = 0;
    for (const d of data) {
      m = Math.max(m, d.value, d.value2 ?? 0, floor ?? 0);
    }
    // Pad the ceiling by 10% so bars never touch the top.
    m = m === 0 ? 1 : m * 1.1;
    return { max: m, groups: data };
  }, [data, floor]);

  if (showTable) {
    return (
      <table
        className={cn(
          "w-full border-collapse text-table tnum",
          className,
        )}
        aria-label={ariaLabel}
      >
        <thead>
          <tr className="border-b border-border text-left text-secondary text-text-secondary">
            <th className="py-2">Label</th>
            <th className="py-2">{seriesLabels[0]}</th>
            {data.some((d) => d.value2 !== undefined) ? (
              <th className="py-2">{seriesLabels[1] ?? "Series 2"}</th>
            ) : null}
            {floor !== undefined ? <th className="py-2">Floor</th> : null}
          </tr>
        </thead>
        <tbody>
          {data.map((d) => {
            const belowFloor =
              floor !== undefined && d.value < (d.floor ?? floor);
            return (
              <tr key={d.label} className="border-b border-border">
                <td className="py-2">{d.label}</td>
                <td className={cn("py-2", belowFloor && "text-danger font-semibold")}>
                  {format(d.value)}
                </td>
                {data.some((x) => x.value2 !== undefined) ? (
                  <td className="py-2">
                    {d.value2 !== undefined ? format(d.value2) : "—"}
                  </td>
                ) : null}
                {floor !== undefined ? (
                  <td className="py-2">{format(d.floor ?? floor)}</td>
                ) : null}
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  }

  const usableW = CHART_WIDTH - PAD_LEFT - PAD_RIGHT;
  const usableH = CHART_HEIGHT - PAD_TOP - PAD_BOTTOM;
  const groupWidth = usableW / Math.max(groups.length, 1);
  const hasSecondSeries = data.some((d) => d.value2 !== undefined);
  const barWidth = hasSecondSeries
    ? Math.min(18, groupWidth / 3)
    : Math.min(28, groupWidth * 0.5);

  const yFor = (v: number) => PAD_TOP + usableH - (v / max) * usableH;

  return (
    <div className={cn("relative", className)}>
      <svg
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        role="img"
        aria-label={ariaLabel}
        className="block w-full h-auto"
      >
        {/* Axis baseline */}
        <line
          x1={PAD_LEFT}
          x2={CHART_WIDTH - PAD_RIGHT}
          y1={PAD_TOP + usableH}
          y2={PAD_TOP + usableH}
          className="stroke-border"
          strokeWidth={1}
        />

        {/* Floor line — text-colored (v2.1 chart rule: floor/target is a
            text-colored line, not a third series colour). */}
        {floor !== undefined ? (
          <>
            <line
              x1={PAD_LEFT}
              x2={CHART_WIDTH - PAD_RIGHT}
              y1={yFor(floor)}
              y2={yFor(floor)}
              className="stroke-text"
              strokeDasharray="4 3"
              strokeWidth={1}
            />
            <text
              x={CHART_WIDTH - PAD_RIGHT}
              y={yFor(floor) - 4}
              textAnchor="end"
              className="fill-text text-[10px] tnum"
            >
              floor {format(floor)}
            </text>
          </>
        ) : null}

        {groups.map((d, i) => {
          const gx = PAD_LEFT + i * groupWidth;
          const groupCenter = gx + groupWidth / 2;
          const perFloor = d.floor ?? floor;
          const belowFloor =
            perFloor !== undefined && d.value < perFloor;
          const bar1X = hasSecondSeries
            ? groupCenter - barWidth - 2
            : groupCenter - barWidth / 2;
          const bar2X = groupCenter + 2;
          const y1 = yFor(d.value);
          const y2 = d.value2 !== undefined ? yFor(d.value2) : null;
          return (
            <g
              key={d.label}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
              tabIndex={0}
              aria-label={`${d.label}: ${format(d.value)}${d.value2 !== undefined ? `, ${format(d.value2)}` : ""}`}
              className="focus:outline-none"
            >
              {/* Series 1 bar */}
              <rect
                x={bar1X}
                y={y1}
                width={barWidth}
                height={PAD_TOP + usableH - y1}
                className="fill-chartSeries1"
              />
              {/* Series 2 bar (optional) */}
              {y2 !== null ? (
                <rect
                  x={bar2X}
                  y={y2}
                  width={barWidth}
                  height={PAD_TOP + usableH - y2}
                  className="fill-chartSeries2"
                />
              ) : null}

              {/* Label */}
              <text
                x={groupCenter}
                y={CHART_HEIGHT - PAD_BOTTOM + 16}
                textAnchor="middle"
                className="fill-text-secondary text-[10px]"
              >
                {d.label}
              </text>

              {/* Value label — red only when below floor. */}
              <text
                x={bar1X + barWidth / 2}
                y={y1 - 4}
                textAnchor="middle"
                className={cn(
                  "text-[10px] tnum",
                  belowFloor ? "fill-danger font-semibold" : "fill-text-secondary",
                )}
              >
                {format(d.value)}
              </text>
            </g>
          );
        })}
      </svg>

      {hover !== null ? (
        <div
          role="tooltip"
          className={cn(
            "pointer-events-none absolute top-2 right-2 rounded-card border border-border",
            "bg-surface shadow-overlay p-2 text-secondary text-text tnum",
          )}
        >
          <div className="font-semibold">{groups[hover].label}</div>
          <div>
            {seriesLabels[0]}: {format(groups[hover].value)}
          </div>
          {groups[hover].value2 !== undefined ? (
            <div>
              {seriesLabels[1] ?? "Series 2"}: {format(groups[hover].value2!)}
            </div>
          ) : null}
          {floor !== undefined ? (
            <div>floor: {format(groups[hover].floor ?? floor)}</div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
