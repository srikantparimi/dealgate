/**
 * Portfolio tab table (spec §15). Default sort surfaces deterioration
 * (worst forecast vs approved variance) and overdue reviews, not the
 * largest revenue — the row identity is the client/project, not a
 * headline number.
 */

import type { ReactNode } from "react";
import { StatusBadge, type StatusTone } from "../../../ui-v2/StatusBadge";
import { MoneyCell } from "../../../ui-v2/MoneyCell";
import { MarginCell } from "../../../ui-v2/MarginCell";
import { fmtMoney, fmtPercent, fmtVariancePp } from "./format";

/**
 * Row shape shared with the loader in `ProjectsActuals.tsx`. Kept
 * intentionally flat so the table stays a pure display component.
 */
export interface PortfolioRow {
  id: string;
  clientProject: string;
  sowEndDate: string | null;
  deliveryOwner: string | null;
  signedValue: string | null;
  approvedFinalGm: string | null;
  forecastFinalGm: string | null;
  /** Server-evaluated risk tier — never inferred from colour alone. */
  risk: {
    label: string;
    tone: StatusTone;
  };
  nextReview: string | null;
}

export interface PortfolioTableProps {
  rows: PortfolioRow[];
  onRowClick?: (row: PortfolioRow) => void;
  emptyMessage?: ReactNode;
}

/**
 * Deterioration-first ordering: rows whose forecast final GM is furthest
 * below the approved baseline sort to the top. Missing values do not
 * pretend to be zero; they sort to the bottom so a genuine deterioration
 * always appears above the "we cannot tell" rows.
 */
export function sortByDeterioration(rows: PortfolioRow[]): PortfolioRow[] {
  const withVariance = rows.map((r) => {
    const a = r.approvedFinalGm ? Number(r.approvedFinalGm) : null;
    const f = r.forecastFinalGm ? Number(r.forecastFinalGm) : null;
    const v = a !== null && f !== null && Number.isFinite(a) && Number.isFinite(f)
      ? f - a
      : null;
    return { row: r, variance: v };
  });
  return withVariance
    .sort((x, y) => {
      // nulls last
      if (x.variance === null && y.variance === null) return 0;
      if (x.variance === null) return 1;
      if (y.variance === null) return -1;
      return x.variance - y.variance; // most negative first
    })
    .map((wv) => wv.row);
}

export function PortfolioTable({
  rows,
  onRowClick,
  emptyMessage,
}: PortfolioTableProps) {
  if (rows.length === 0) {
    return (
      <div
        role="status"
        className="rounded-panel border border-dashed border-divider p-6 text-body text-text-secondary"
      >
        {emptyMessage ?? "No portfolio rows to show yet."}
      </div>
    );
  }

  const sorted = sortByDeterioration(rows);
  return (
    <div className="overflow-x-auto rounded-panel border border-divider">
      <table
        className="w-full text-body"
        aria-label="Portfolio"
        data-testid="portfolio-table"
      >
        <thead className="bg-primary-subtle/40">
          <tr className="text-left text-secondary text-text-secondary">
            <th className="px-3 py-2 font-medium">Client · Project</th>
            <th className="px-3 py-2 font-medium">SOW end</th>
            <th className="px-3 py-2 font-medium">Delivery owner</th>
            <th className="px-3 py-2 font-medium text-right">Signed value</th>
            <th className="px-3 py-2 font-medium text-right">Approved final GM</th>
            <th className="px-3 py-2 font-medium text-right">Forecast final GM</th>
            <th className="px-3 py-2 font-medium text-right">Variance (pts)</th>
            <th className="px-3 py-2 font-medium">Risk</th>
            <th className="px-3 py-2 font-medium">Next review</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => {
            const varStr = fmtVariancePp(r.approvedFinalGm, r.forecastFinalGm);
            const approvedPct = fmtPercent(r.approvedFinalGm);
            const forecastPct = fmtPercent(r.forecastFinalGm);
            return (
              <tr
                key={r.id}
                data-testid={`portfolio-row-${r.id}`}
                className="cursor-pointer border-t border-divider hover:bg-primary-subtle/30"
                onClick={() => onRowClick?.(r)}
              >
                <td className="px-3 py-3 align-top text-text">
                  {r.clientProject}
                </td>
                <td className="px-3 py-3 align-top tnum text-text-secondary">
                  {r.sowEndDate ?? "Unavailable"}
                </td>
                <td className="px-3 py-3 align-top text-text-secondary">
                  {r.deliveryOwner ?? "Unassigned"}
                </td>
                <td className="px-3 py-3 align-top">
                  <MoneyCell value={fmtMoney(r.signedValue) ?? undefined} />
                </td>
                <td className="px-3 py-3 align-top">
                  <MarginCell
                    value={approvedPct ?? undefined}
                    outcome={approvedPct === null ? "unavailable" : undefined}
                  />
                </td>
                <td className="px-3 py-3 align-top">
                  <MarginCell
                    value={forecastPct ?? undefined}
                    outcome={forecastPct === null ? "unavailable" : undefined}
                  />
                </td>
                <td className="px-3 py-3 align-top">
                  <MarginCell value={varStr ?? undefined} />
                </td>
                <td className="px-3 py-3 align-top">
                  <StatusBadge tone={r.risk.tone} label={r.risk.label} />
                </td>
                <td className="px-3 py-3 align-top tnum text-text-secondary">
                  {r.nextReview ?? "Not scheduled"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
