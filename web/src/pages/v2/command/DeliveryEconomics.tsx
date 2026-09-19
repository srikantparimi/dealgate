/**
 * Delivery economics — spec §5 item 5.
 *
 * Approved vs forecast margin on active signed SOWs, split by geography
 * (US, India, Blended). Distinguishes signed value from open pipeline
 * and recognised revenue by labelling each column explicitly. Every
 * number is server-computed (blueprint §2, CLAUDE.md rule 2).
 */

import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { cn } from "../../../lib/cn";
import { MoneyCell } from "../../../ui-v2/MoneyCell";
import { MarginCell } from "../../../ui-v2/MarginCell";

export interface EconomicsRow {
  geography: "US" | "India" | "Blended";
  approvedMargin: string | null;
  forecastMargin: string | null;
  variance: string | null;
  floor: string | null;
  outcome?: "pass" | "fail" | "unavailable";
}

export interface DeliveryEconomicsProps {
  rows: EconomicsRow[];
  signedValue: string | null;
  openPipeline: string | null;
  recognisedRevenue: string | null;
  drillHref?: string;
  basis?: ReactNode;
}

function Th({ children, align = "left" }: { children: ReactNode; align?: "left" | "right" }) {
  return (
    <th
      scope="col"
      className={cn(
        "px-3 py-2 text-secondary uppercase tracking-wide",
        "text-text-secondary font-medium",
        align === "right" ? "text-right" : "text-left",
      )}
    >
      {children}
    </th>
  );
}

export function DeliveryEconomics({
  rows,
  signedValue,
  openPipeline,
  recognisedRevenue,
  drillHref = "/dashboard",
  basis,
}: DeliveryEconomicsProps) {
  return (
    <section aria-label="Delivery economics">
      <div className="mb-3 flex items-end justify-between gap-3">
        <div>
          <h2 className="text-section text-text">Delivery economics</h2>
          <p className="text-secondary text-text-secondary">
            Approved vs forecast margin on active signed SOWs — geography
            floors are policy, not display defaults.
          </p>
        </div>
        <Link
          to={drillHref}
          className="text-body text-primary hover:underline focus-visible:outline-focus"
        >
          Drill through
        </Link>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <ValueTile label="Signed value" value={signedValue} />
        <ValueTile label="Open pipeline" value={openPipeline} />
        <ValueTile label="Recognised revenue" value={recognisedRevenue} />
      </div>
      <div className="mt-4 overflow-x-auto rounded-panel border border-divider bg-surface">
        <table className="min-w-full text-body">
          <thead className="border-b border-divider bg-canvas/60">
            <tr>
              <Th>Geography</Th>
              <Th align="right">Approved GM</Th>
              <Th align="right">Forecast GM</Th>
              <Th align="right">Variance</Th>
              <Th align="right">Floor</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.geography}
                className="border-b border-divider last:border-0"
              >
                <td className="px-3 py-3 text-body text-text">
                  {r.geography === "Blended"
                    ? "Blended"
                    : `${r.geography} floor`}
                </td>
                <td className="px-3 py-3">
                  <MarginCell value={r.approvedMargin} outcome={r.outcome} />
                </td>
                <td className="px-3 py-3">
                  <MarginCell value={r.forecastMargin} />
                </td>
                <td className="px-3 py-3">
                  <MarginCell value={r.variance} />
                </td>
                <td className="px-3 py-3">
                  <MarginCell value={r.floor} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {basis ? (
        <p className="mt-3 text-secondary text-text-secondary">{basis}</p>
      ) : null}
    </section>
  );
}

function ValueTile({
  label,
  value,
}: {
  label: string;
  value: string | null;
}) {
  return (
    <div className="rounded-panel border border-divider bg-surface p-4">
      <span className="text-secondary uppercase tracking-wide text-text-secondary">
        {label}
      </span>
      <div className="mt-1">
        <MoneyCell value={value} className="text-left text-metric" />
      </div>
    </div>
  );
}
