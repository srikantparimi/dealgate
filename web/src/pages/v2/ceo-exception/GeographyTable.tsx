import type { CeoBriefJson } from "../../../api/client";
import { MarginCell } from "../../../ui-v2/MarginCell";
import { MoneyCell } from "../../../ui-v2/MoneyCell";
import { formatPercent, formatPpGap, formatUsd } from "./format";

/**
 * Full-width geography table (spec §14 — the CEO must see BOTH under-floor
 * components independently, never merged into a single blended number).
 */
export function GeographyTable({ brief }: { brief: CeoBriefJson }) {
  const rows = [
    {
      location: "US",
      revenue: brief.revenue.us,
      cost: brief.cost.us,
      gm: brief.gm.us.value,
      floor: brief.gm.us.floor,
      passes: brief.gm.us.passes,
      uplift: brief.price_uplift.us,
    },
    {
      location: "India",
      revenue: brief.revenue.india,
      cost: brief.cost.india,
      gm: brief.gm.india.value,
      floor: brief.gm.india.floor,
      passes: brief.gm.india.passes,
      uplift: brief.price_uplift.india,
    },
  ];

  return (
    <section
      aria-label="Geography breakdown"
      className="rounded-panel border border-divider bg-surface p-4"
    >
      <h2 className="text-section text-text mb-3">Geography</h2>
      <div
        role="region"
        aria-label="Geography scroll region"
        className="overflow-x-auto"
      >
        <table
          className="min-w-full text-body"
          aria-label="Geography breakdown"
        >
          <thead>
            <tr className="text-left text-text-secondary text-secondary uppercase">
              <th className="py-2 pr-4">Location</th>
              <th className="py-2 pr-4 text-right">Allocated revenue</th>
              <th className="py-2 pr-4 text-right">Cost</th>
              <th className="py-2 pr-4 text-right">Proposed GM</th>
              <th className="py-2 pr-4 text-right">Required GM</th>
              <th className="py-2 pr-4 text-right">Shortfall (pp)</th>
              <th className="py-2 pr-4 text-right">Compliant revenue</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.location}
                data-testid={`geo-row-${r.location.toLowerCase()}`}
                className="border-t border-divider"
              >
                <td className="py-2 pr-4 text-text">{r.location}</td>
                <td className="py-2 pr-4">
                  <MoneyCell value={formatUsd(r.revenue) ?? undefined} />
                </td>
                <td className="py-2 pr-4">
                  <MoneyCell value={formatUsd(r.cost) ?? undefined} />
                </td>
                <td className="py-2 pr-4">
                  <MarginCell
                    value={formatPercent(r.gm) ?? undefined}
                    outcome={
                      r.passes == null
                        ? "unavailable"
                        : r.passes
                          ? "pass"
                          : "fail"
                    }
                  />
                </td>
                <td className="py-2 pr-4">
                  <MoneyCell value={formatPercent(r.floor) ?? undefined} />
                </td>
                <td className="py-2 pr-4">
                  <MoneyCell value={formatPpGap(r.gm, r.floor) ?? undefined} />
                </td>
                <td className="py-2 pr-4">
                  <MoneyCell value={formatUsd(r.uplift) ?? undefined} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
