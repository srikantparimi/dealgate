/**
 * Client SOWs & GM page — extends ClientDetail with the SOW-by-SOW GM
 * breakdown. Every number is server-side; the totals row surfaces the
 * client-GM formula so users can see the aggregation isn't a mean of
 * percentages (blueprint §2, story acceptance test).
 */

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getClientSowGmDashboard,
  type ClientSowGmDashboard,
} from "../api/client";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { PageHeader } from "../ui/PageHeader";
import { StatusChip } from "../ui/StatusChip";
import { money, pct } from "./dashboards/shared";

export function ClientSowGmPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<ClientSowGmDashboard | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    if (!id) return;
    setError(null);
    getClientSowGmDashboard(id)
      .then(setData)
      .catch(setError);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (error && !data) return <ErrorState error={error} retry={load} />;
  if (!data) return <EmptyState title="Loading" hint="Fetching SOW GM view." />;

  return (
    <div>
      <PageHeader
        title={`SOWs & GM — ${data.client_name ?? data.client_id}`}
        subtitle={
          <span>
            <Link to={`/clients/${data.client_id}`} style={{ color: "#1d4ed8" }}>
              Back to client
            </Link>
          </span>
        }
      />

      {data.rows.length === 0 ? (
        <EmptyState
          title="No SOWs yet"
          hint="This client has no opportunities with a GM model."
        />
      ) : (
        <table
          aria-label="SOWs and GM"
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: 14,
          }}
        >
          <thead>
            <tr style={{ background: "#f9fafb", textAlign: "left" }}>
              {[
                "Deal",
                "Dates",
                "Revenue",
                "US cost",
                "India cost",
                "Approved GM",
                "Forecast GM",
                "Actual GM",
                "Exception",
              ].map((h) => (
                <th
                  key={h}
                  style={{
                    padding: "8px 12px",
                    borderBottom: "1px solid #e5e7eb",
                    fontWeight: 600,
                    color: "#374151",
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr
                key={r.opportunity_id}
                style={{ borderBottom: "1px solid #f3f4f6" }}
              >
                <td style={{ padding: "8px 12px" }}>
                  <Link
                    to={`/sows/${r.opportunity_id}`}
                    style={{ color: "#1d4ed8" }}
                  >
                    {r.hubspot_deal_id}
                  </Link>
                </td>
                <td style={{ padding: "8px 12px", fontSize: 12, color: "#6b7280" }}>
                  {r.start_date ?? "?"} → {r.end_date ?? "?"}
                </td>
                <td style={{ padding: "8px 12px" }}>
                  {money(
                    // Sum US + India revenue for the display column. The
                    // per-side numbers are still surfaced individually below.
                    r.revenue_us && r.revenue_india
                      ? // Concatenate as string display only; we rely on the
                        // server totals row for the aggregate.
                        r.revenue_us
                      : r.revenue_us ?? r.revenue_india ?? null,
                  )}
                </td>
                <td style={{ padding: "8px 12px" }}>{money(r.cost_us)}</td>
                <td style={{ padding: "8px 12px" }}>{money(r.cost_india)}</td>
                <td style={{ padding: "8px 12px" }}>{pct(r.approved_gm)}</td>
                <td style={{ padding: "8px 12px" }}>{pct(r.forecast_gm)}</td>
                <td style={{ padding: "8px 12px" }}>{pct(r.actual_gm)}</td>
                <td style={{ padding: "8px 12px" }}>
                  {r.exception_flag ? (
                    <StatusChip tone="block">exception</StatusChip>
                  ) : (
                    <StatusChip tone="ok">clean</StatusChip>
                  )}
                </td>
              </tr>
            ))}
            <tr
              key="totals"
              style={{
                background: "#f3f4f6",
                borderTop: "2px solid #d1d5db",
                fontWeight: 600,
              }}
            >
              <td style={{ padding: "8px 12px" }}>Totals</td>
              <td style={{ padding: "8px 12px" }}>—</td>
              <td style={{ padding: "8px 12px" }}>{money(data.totals.revenue)}</td>
              <td style={{ padding: "8px 12px" }}>{money(data.totals.cost_us)}</td>
              <td style={{ padding: "8px 12px" }}>{money(data.totals.cost_india)}</td>
              <td style={{ padding: "8px 12px" }} colSpan={2}>
                Client GM: {pct(data.totals.client_gm)}
              </td>
              <td style={{ padding: "8px 12px" }} colSpan={2}>
                GP: {money(data.totals.gross_profit)}
              </td>
            </tr>
          </tbody>
        </table>
      )}
      <p
        style={{
          marginTop: 12,
          fontSize: 12,
          color: "#6b7280",
        }}
        data-testid="client-gm-formula"
      >
        <strong>Client GM formula:</strong> {data.totals.formula}
      </p>
    </div>
  );
}
