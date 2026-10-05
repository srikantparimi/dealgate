import type { ForecastOutlook } from "../../../api/forecast";
import { formatPercent } from "../sow-workspace/format";

export function CurrentEstimate({ data }: { data: ForecastOutlook }) {
  const estimate = data.current_period_estimate;
  if (!estimate) return null;
  return (
    <section aria-label="Current-period signed estimate" className="space-y-3 border-y border-divider py-4">
      <h2 className="font-semibold">Current-period signed estimate</h2>
      <p className="text-secondary">{estimate.currency} / Through {estimate.cutoff} / Finance-confirmed service coverage</p>
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <dt>Estimated revenue</dt><dd>{estimate.totals.revenue ?? "Unresolved"}</dd>
        <dt>Estimated delivery cost</dt><dd>{estimate.totals.cost ?? "Unresolved"}</dd>
        <dt>Estimated profit</dt><dd>{estimate.totals.profit ?? "Unassessed"}</dd>
        <dt>Estimated GM</dt><dd>{formatPercent(estimate.totals.gm_pct) ?? "Unassessed"}</dd>
      </dl>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] text-left text-sm [&_td]:p-2 [&_th]:p-2">
          <thead><tr>{["Account", "Source version", "Measure", "Signed schedule", "Matched actuals", "Covered scope", "Uncovered forecast", "Estimate"].map(label => <th key={label}>{label}</th>)}</tr></thead>
          <tbody>{estimate.rows.flatMap(row => (["revenue", "cost"] as const).map(measure => (
            <tr key={`${row.row_id}:${measure}`} className="border-t border-divider">
              <td>{data.accounts.find(account => account.account_id === row.account_id)?.name ?? row.account_id}</td>
              <td><span title={row.source_version}>Version {row.source_version.slice(0, 8)}</span><br /><span className="whitespace-nowrap">{row.month}</span></td>
              <td>{measure === "revenue" ? "Recognized revenue" : "Delivery cost"}</td>
              <td>{row[measure].scheduled ?? "Unresolved"}</td>
              <td>{row[measure].actual_ids.length ? row[measure].actual_to_date : "No matched actuals"}</td>
              <td>{formatPercent(row[measure].covered_fraction)}</td>
              <td>{row[measure].uncovered_forecast ?? "Unresolved"}</td>
              <td>{row[measure].estimate ?? "Unresolved"}</td>
            </tr>
          )))}</tbody>
        </table>
      </div>
      {estimate.rows.length === 0 && <p className="text-secondary">No matching current signed service schedule.</p>}
      {estimate.excluded.length > 0 && <details>
        <summary>Unmatched actuals and source exceptions ({estimate.excluded.length})</summary>
        {estimate.excluded.map((row, index) => <p key={`${row.id}:${index}`} className="break-words text-secondary">{row.id}: {row.reason}</p>)}
      </details>}
    </section>
  );
}
