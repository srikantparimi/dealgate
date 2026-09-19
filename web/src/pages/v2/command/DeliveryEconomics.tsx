/**
 * Delivery economics — DealGate v2.1 prototype (lines 217–224, 388–393,
 * 594–608).
 *
 * SVG bar chart. Each x-value is one SOW with:
 *   - Series 1 bar (Approved GM) in --s1
 *   - Series 2 bar (Forecast final GM) in --s2
 *   - Text-colored floor line above the pair
 *   - Red value label rendered only when the forecast dips below the floor
 *
 * A legend precedes the chart and a hover tooltip sits above the SVG. No
 * math in the browser — every number is a Decimal string owned by the
 * server.
 */

import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { cn } from "../../../lib/cn";

export interface EconomicsRow {
  /** Short label rendered on the x-axis, e.g. "Summit Semi." */
  name: string;
  /** Approved GM as a percentage number (e.g. `39.6`). */
  approved: number | null;
  /** Forecast final GM as a percentage number. */
  forecast: number | null;
  /** Floor GM as a percentage number (US 35, India 50, mixed weighted). */
  floor: number | null;
  /** `US | India | Mixed` — controls the floor dashing. */
  geography?: "US" | "India" | "Mixed" | null;
  /**
   * S10-02: when the row's SOW came in through the bulk-import
   * pipeline (``governance_status === 'legacy_not_evidenced'``), the
   * chart's row label prefixes with a small "Legacy" chip so readers
   * see it at a glance. Optional; missing = not legacy.
   */
  legacy?: boolean;
}

export interface DeliveryEconomicsProps {
  rows: EconomicsRow[];
  title?: string;
  caption?: string;
  drillLabel?: string;
  drillHref?: string;
}

const PADDING = { left: 110, right: 20, top: 16, bottom: 30 };
const MAX_PCT = 60;

interface TooltipData {
  x: number;
  y: number;
  row: EconomicsRow;
}

export function DeliveryEconomics({
  rows,
  title = "Delivery economics",
  caption,
  drillLabel,
  drillHref,
}: DeliveryEconomicsProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);

  const dims = useMemo(() => {
    const W = 900;
    const H = 230;
    const cw = W - PADDING.left - PADDING.right;
    const ch = H - PADDING.top - PADDING.bottom;
    const y = (v: number) => PADDING.top + ch - (v / MAX_PCT) * ch;
    const gw = rows.length > 0 ? cw / rows.length : cw;
    const bw = Math.min(24, gw * 0.2);
    return { W, H, cw, ch, y, gw, bw };
  }, [rows.length]);

  return (
    <section
      aria-label={title}
      className="relative rounded-card border border-border bg-surface"
    >
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-5 pt-4">
        <h2 className="text-section font-semibold text-text">{title}</h2>
        {caption ? (
          <span className="text-[12px] text-text-muted">{caption}</span>
        ) : null}
        {drillLabel && drillHref ? (
          <Link
            to={drillHref}
            className="ml-auto text-[13px] text-primaryText hover:underline focus-visible:outline-focus"
          >
            {drillLabel}
          </Link>
        ) : null}
      </header>

      <Legend />

      <div
        ref={containerRef}
        className="relative overflow-x-auto px-5 pb-5 pt-2"
      >
        {rows.length === 0 ? (
          <div
            role="status"
            className="p-6 text-center text-body text-text-secondary"
          >
            Delivery economics are unavailable right now.
          </div>
        ) : (
          <svg
            role="img"
            aria-label={title}
            viewBox={`0 0 ${dims.W} ${dims.H}`}
            width="100%"
            className="block min-w-[640px]"
            onMouseLeave={() => setTooltip(null)}
          >
            {[0, 20, 40, 60].map((t) => (
              <g key={t}>
                <line
                  x1={PADDING.left}
                  x2={dims.W - PADDING.right}
                  y1={dims.y(t)}
                  y2={dims.y(t)}
                  stroke="var(--dg-border)"
                  strokeWidth="1"
                />
                <text
                  x={PADDING.left - 8}
                  y={dims.y(t) + 4}
                  textAnchor="end"
                  fontFamily="var(--font-sans, Inter, sans-serif)"
                  fill="var(--dg-text-secondary)"
                  fontSize="11"
                >
                  {t}%
                </text>
              </g>
            ))}
            {rows.map((r, i) => {
              const cx = PADDING.left + dims.gw * i + dims.gw / 2;
              const approved = r.approved ?? 0;
              const forecast = r.forecast ?? 0;
              const floor = r.floor ?? 0;
              const belowFloor =
                r.forecast != null && r.floor != null && r.forecast < r.floor;
              return (
                <g
                  key={r.name + i}
                  onMouseMove={(e) => {
                    const container = containerRef.current;
                    if (!container) return;
                    const bounds = container.getBoundingClientRect();
                    setTooltip({
                      x: e.clientX - bounds.left + 12,
                      y: e.clientY - bounds.top - 40,
                      row: r,
                    });
                  }}
                >
                  {r.approved != null ? (
                    <rect
                      x={cx - dims.bw - 3}
                      y={dims.y(approved)}
                      width={dims.bw}
                      height={dims.y(0) - dims.y(approved)}
                      rx="3"
                      fill="var(--dg-chart-series-1)"
                    />
                  ) : null}
                  {r.forecast != null ? (
                    <rect
                      x={cx + 3}
                      y={dims.y(forecast)}
                      width={dims.bw}
                      height={dims.y(0) - dims.y(forecast)}
                      rx="3"
                      fill="var(--dg-chart-series-2)"
                    />
                  ) : null}
                  {r.floor != null ? (
                    <line
                      x1={cx - dims.bw - 10}
                      x2={cx + dims.bw + 10}
                      y1={dims.y(floor)}
                      y2={dims.y(floor)}
                      stroke="var(--dg-text)"
                      strokeWidth="1.5"
                      strokeDasharray={r.geography === "Mixed" ? "3 3" : "0"}
                    />
                  ) : null}
                  {belowFloor && r.forecast != null && r.floor != null ? (
                    <text
                      x={cx + 3 + dims.bw / 2}
                      y={Math.min(dims.y(r.forecast), dims.y(r.floor)) - 6}
                      textAnchor="middle"
                      fill="var(--dg-danger)"
                      fontSize="11"
                      fontWeight="600"
                      fontFamily="var(--font-sans, Inter, sans-serif)"
                    >
                      {r.forecast.toFixed(1)}%
                    </text>
                  ) : null}
                  <text
                    x={cx}
                    y={dims.H - 10}
                    textAnchor="middle"
                    fill="var(--dg-text-secondary)"
                    fontSize="11"
                    fontFamily="var(--font-sans, Inter, sans-serif)"
                    data-testid={
                      r.legacy ? `legacy-row-${r.name}` : undefined
                    }
                  >
                    {r.legacy ? "Legacy · " : ""}
                    {r.name}
                  </text>
                  <rect
                    x={PADDING.left + dims.gw * i}
                    y={PADDING.top}
                    width={dims.gw}
                    height={dims.ch}
                    fill="transparent"
                  />
                </g>
              );
            })}
          </svg>
        )}
        {tooltip ? (
          <div
            role="tooltip"
            className={cn(
              "pointer-events-none absolute rounded-[6px] bg-plum",
              "px-2 py-[6px] text-[12px] text-onPlum",
              "shadow-menu",
            )}
            style={{ left: tooltip.x, top: tooltip.y }}
          >
            <b>{tooltip.row.name}</b>
            {tooltip.row.geography ? ` · ${tooltip.row.geography}` : ""}
            <br />
            Approved {tooltip.row.approved?.toFixed(1) ?? "—"}% · Forecast{" "}
            {tooltip.row.forecast?.toFixed(1) ?? "—"}% · Floor{" "}
            {tooltip.row.floor?.toFixed(1) ?? "—"}%
          </div>
        ) : null}
      </div>
    </section>
  );
}

function Legend(): ReactNode {
  return (
    <div className="flex gap-4 px-5 pt-3 text-[12px] text-text-secondary">
      <span className="inline-flex items-center gap-[6px]">
        <span
          aria-hidden
          className="inline-block h-[10px] w-[10px] rounded-[2px]"
          style={{ background: "var(--dg-chart-series-1)" }}
        />
        Approved GM
      </span>
      <span className="inline-flex items-center gap-[6px]">
        <span
          aria-hidden
          className="inline-block h-[10px] w-[10px] rounded-[2px]"
          style={{ background: "var(--dg-chart-series-2)" }}
        />
        Forecast final GM
      </span>
      <span className="inline-flex items-center gap-[6px]">
        <span
          aria-hidden
          className="inline-block h-[12px] w-[2px]"
          style={{ background: "var(--dg-text)" }}
        />
        Policy floor
      </span>
    </div>
  );
}
