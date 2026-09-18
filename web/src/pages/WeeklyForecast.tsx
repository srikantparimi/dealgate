/**
 * WeeklyForecast — Delivery lead posts one number per resource line each
 * week (``remaining_hours``); the API freezes a ``forecast_period`` row
 * with the resulting forecast GM per component (S6 E9,
 * ``docs/backlog/s6-weekly-forecast.md``).
 *
 * Read is Delivery / HR / Finance / CEO / SystemAdmin; write is Delivery
 * / SystemAdmin. Both gates live on the API — the page mirrors them for
 * UX so buttons render only for callers who can plausibly succeed.
 *
 * No business math in the browser (blueprint §2, CLAUDE.md rule 2). GM,
 * revenue and cost fields are Decimal strings the API pre-computes; the
 * sparkline just plots the already-computed ``forecast_gm_us`` values.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getForecastHistory,
  getLatestDeliveryModel,
  getLatestForecast,
  postForecast,
  type DeliveryResourceLineRow,
  type ForecastLineInput,
  type ForecastPeriod,
  type UUID,
} from "../api/client";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { StatusChip } from "../ui/StatusChip";
import { Table, type Column } from "../ui/Table";

// Blueprint §2 defaults. The API is the truth for what the policy is;
// this is just the pass/fail hint the panel renders on first paint before
// the compute lands. The API's own floor pass/fail drives the toast.
const US_FLOOR = 0.35;
const INDIA_FLOOR = 0.5;

interface Props {
  gmModelId: UUID;
  opportunityId: UUID;
}

interface RowState {
  // The resource line id doubles as the row key for ``Table``.
  id: string;
  line: DeliveryResourceLineRow;
  remaining_hours: string;
}

function toneForGm(gm: string | null, floor: number): "ok" | "block" | "neutral" {
  if (gm === null) return "neutral";
  const value = Number.parseFloat(gm);
  if (Number.isNaN(value)) return "neutral";
  return value >= floor ? "ok" : "block";
}

function formatGm(gm: string | null): string {
  if (gm === null) return "—";
  const value = Number.parseFloat(gm);
  if (Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function formatMoney(value: string | null): string {
  if (value === null) return "—";
  const num = Number.parseFloat(value);
  if (Number.isNaN(num)) return value;
  return `$${num.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

/** Tiny SVG sparkline of the last 12 GM values. Pure paint — no math. */
function Sparkline({ values }: { values: number[] }) {
  if (values.length === 0) {
    return (
      <div data-testid="sparkline-empty" style={{ fontSize: 12, color: "#6b7280" }}>
        No trend yet
      </div>
    );
  }
  const width = 220;
  const height = 40;
  const padding = 4;
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const span = max - min || 1;
  const step = values.length > 1 ? (width - padding * 2) / (values.length - 1) : 0;
  const points = values
    .map((v, i) => {
      const x = padding + step * i;
      const y = height - padding - ((v - min) / span) * (height - padding * 2);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  return (
    <svg
      role="img"
      aria-label="Forecast GM trend"
      data-testid="forecast-sparkline"
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      style={{ display: "block" }}
    >
      <polyline
        fill="none"
        stroke="#1d4ed8"
        strokeWidth={2}
        points={points}
      />
    </svg>
  );
}

export function WeeklyForecast({ gmModelId, opportunityId }: Props) {
  const [rows, setRows] = useState<RowState[]>([]);
  const [latest, setLatest] = useState<ForecastPeriod | null>(null);
  const [history, setHistory] = useState<ForecastPeriod[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [recoveryToast, setRecoveryToast] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!gmModelId || !opportunityId) return;
    setLoading(true);
    setError(null);
    Promise.all([
      getLatestDeliveryModel(opportunityId),
      getLatestForecast(gmModelId),
      getForecastHistory(gmModelId, 12),
    ])
      .then(([dm, latestRow, hist]) => {
        const lines = dm.gm_model?.resource_lines ?? [];
        const prev = new Map<string, string>();
        if (latestRow) {
          for (const snap of latestRow.forecast_lines_json) {
            prev.set(snap.resource_line_id, snap.remaining_hours);
          }
        }
        setRows(
          lines.map((line) => ({
            id: line.id,
            line,
            remaining_hours: prev.get(line.id) ?? "0",
          })),
        );
        setLatest(latestRow);
        setHistory(hist.items);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, [gmModelId, opportunityId]);

  useEffect(() => {
    load();
  }, [load]);

  const usTone = toneForGm(latest?.forecast_gm_us ?? null, US_FLOOR);
  const indiaTone = toneForGm(latest?.forecast_gm_india ?? null, INDIA_FLOOR);
  const blendedGm = useMemo(() => {
    if (!latest) return null;
    const rev = Number.parseFloat(latest.forecast_revenue);
    const costTotal =
      Number.parseFloat(latest.forecast_cost_us) +
      Number.parseFloat(latest.forecast_cost_india);
    if (!Number.isFinite(rev) || rev <= 0) return null;
    // Display-only aggregate — mirrors the pure library's blended GM.
    // Not a policy decision (blueprint §2: components are what gate CEO).
    return (rev - costTotal) / rev;
  }, [latest]);

  const sparklineValues = useMemo(() => {
    return history
      .map((row) => {
        const rev =
          Number.parseFloat(row.forecast_revenue || "0") || 0;
        if (rev <= 0) return NaN;
        const cost =
          Number.parseFloat(row.forecast_cost_us || "0") +
          Number.parseFloat(row.forecast_cost_india || "0");
        return (rev - cost) / rev;
      })
      .filter((v) => Number.isFinite(v));
  }, [history]);

  async function save() {
    setSaving(true);
    setError(null);
    setToast(null);
    setRecoveryToast(null);
    try {
      const lines: ForecastLineInput[] = rows.map((row) => ({
        resource_line_id: row.line.id,
        remaining_hours: row.remaining_hours || "0",
      }));
      const updated = await postForecast(gmModelId, lines);
      setLatest(updated);
      setHistory((prev) => [...prev, updated]);
      setToast(`Saved forecast for week ending ${updated.week_ending}`);
      const usFails =
        updated.forecast_gm_us !== null &&
        Number.parseFloat(updated.forecast_gm_us) < US_FLOOR;
      const indiaFails =
        updated.forecast_gm_india !== null &&
        Number.parseFloat(updated.forecast_gm_india) < INDIA_FLOOR;
      if (usFails || indiaFails) {
        setRecoveryToast(
          "Forecast GM below floor — recovery task filed with the Delivery lead.",
        );
      }
      window.setTimeout(() => setToast(null), 2500);
      window.setTimeout(() => setRecoveryToast(null), 5000);
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <EmptyState title="Loading" hint="Fetching resource lines." />;
  }
  if (error && rows.length === 0) {
    return <ErrorState error={error} retry={load} />;
  }
  if (rows.length === 0) {
    return (
      <EmptyState
        title="No resource lines"
        hint="Add resource lines to the GM model before forecasting."
      />
    );
  }

  const columns: Column<RowState>[] = [
    {
      key: "role",
      header: "Role",
      render: (r) => `${r.line.role} / ${r.line.seniority}`,
    },
    { key: "location", header: "Location", render: (r) => r.line.location },
    {
      key: "person",
      header: "Person",
      render: (r) => r.line.person_name ?? "(to hire)",
    },
    {
      key: "remaining",
      header: "Remaining hours",
      render: (r) => (
        <input
          type="number"
          min={0}
          step="1"
          value={r.remaining_hours}
          data-testid={`remaining-${r.line.id}`}
          aria-label={`Remaining hours ${r.line.role} ${r.line.seniority}`}
          onChange={(e) =>
            setRows((prev) =>
              prev.map((row) =>
                row.line.id === r.line.id
                  ? { ...row, remaining_hours: e.target.value }
                  : row,
              ),
            )
          }
          style={{ width: 100, padding: 4 }}
        />
      ),
    },
  ];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16 }}>
      <div>
        <Table ariaLabel="Weekly forecast resource lines" columns={columns} rows={rows} />
        <div style={{ marginTop: 12, display: "flex", gap: 12, alignItems: "center" }}>
          <button
            type="button"
            onClick={save}
            disabled={saving}
            data-testid="save-forecast-btn"
            style={{
              background: "#111827",
              color: "white",
              border: "none",
              padding: "8px 16px",
              borderRadius: 6,
              cursor: saving ? "wait" : "pointer",
            }}
          >
            {saving ? "Saving…" : "Save weekly forecast"}
          </button>
          {toast ? (
            <span role="status" style={{ color: "#065f46", fontSize: 13 }}>
              {toast}
            </span>
          ) : null}
          {recoveryToast ? (
            <span
              role="alert"
              data-testid="recovery-toast"
              style={{ color: "#991b1b", fontSize: 13 }}
            >
              {recoveryToast}
            </span>
          ) : null}
        </div>
        {error ? <ErrorState error={error} retry={load} /> : null}
      </div>

      <aside
        style={{
          border: "1px solid #e5e7eb",
          borderRadius: 8,
          padding: 16,
          background: "#f9fafb",
        }}
        data-testid="forecast-summary"
      >
        <h3 style={{ marginTop: 0, marginBottom: 12, fontSize: 14, color: "#111827" }}>
          Latest forecast
        </h3>
        {latest ? (
          <>
            <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 8 }}>
              Week ending {latest.week_ending}
            </div>
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 12, color: "#6b7280" }}>US GM</div>
              <div>
                <span data-testid="gm-us-chip">
                  <StatusChip tone={usTone}>
                    {formatGm(latest.forecast_gm_us)}
                  </StatusChip>
                </span>
              </div>
            </div>
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 12, color: "#6b7280" }}>India GM</div>
              <div>
                <span data-testid="gm-india-chip">
                  <StatusChip tone={indiaTone}>
                    {formatGm(latest.forecast_gm_india)}
                  </StatusChip>
                </span>
              </div>
            </div>
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: "#6b7280" }}>Blended GM</div>
              <div data-testid="gm-blended">
                {blendedGm === null
                  ? "—"
                  : `${(blendedGm * 100).toFixed(1)}%`}
              </div>
            </div>
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: "#6b7280" }}>Revenue / cost</div>
              <div style={{ fontSize: 13 }}>
                {formatMoney(latest.forecast_revenue)} /{" "}
                {formatMoney(
                  String(
                    Number.parseFloat(latest.forecast_cost_us) +
                      Number.parseFloat(latest.forecast_cost_india),
                  ),
                )}
              </div>
            </div>
          </>
        ) : (
          <div style={{ fontSize: 13, color: "#6b7280", marginBottom: 12 }}>
            No forecast yet — save this week to seed the trend.
          </div>
        )}
        <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>
          Last 12 weeks (blended)
        </div>
        <Sparkline values={sparklineValues} />
      </aside>
    </div>
  );
}
