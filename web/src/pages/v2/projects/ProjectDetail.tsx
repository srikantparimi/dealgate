/**
 * Project detail (`/projects/:id/:tab?`) — spec §15.
 *
 * Tabs: Overview / Financials / Staffing / Risks & changes / Activity.
 * The financial view reports the original approved baseline, approved
 * amendments and current forecast SEPARATELY — a forecast that falls
 * below the floor opens a recovery decision but never retroactively
 * overwrites the approved GM.
 *
 * Forecast updates (`postForecast`) are gated to Delivery / SystemAdmin
 * on the client — the server independently enforces the role check
 * (CLAUDE.md rule 5). Non-Delivery viewers see the numbers, not the
 * primary "Update forecast" action.
 */

import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../../../auth/AuthProvider";
import {
  getLatestForecast,
  getLatestDeliveryModel,
  ApiError,
  type DeliveryLatestResponse,
  type ForecastPeriod,
} from "../../../api/client";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { ErrorState } from "../../../ui-v2/ErrorState";
import { RecordHeader } from "../../../ui-v2/RecordHeader";
import { RecordTabs, type RecordTabItem } from "../../../ui-v2/RecordTabs";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import { Button } from "../../../ui-v2/primitives/button";
import { StaffingTab, toStaffingRow } from "./StaffingTab";
import { fmtMoney, fmtPercent } from "./format";

const DELIVERY_ROLES = new Set(["Delivery", "SystemAdmin"]);

const TAB_ORDER = [
  "overview",
  "financials",
  "staffing",
  "risks",
  "activity",
] as const;
type TabKey = (typeof TAB_ORDER)[number];

const TAB_LABELS: Record<TabKey, string> = {
  overview: "Overview",
  financials: "Financials",
  staffing: "Staffing",
  risks: "Risks & changes",
  activity: "Activity",
};

function isTabKey(v: unknown): v is TabKey {
  return typeof v === "string" && (TAB_ORDER as readonly string[]).includes(v);
}

export function ProjectDetailPage() {
  const { id, tab } = useParams<{ id: string; tab?: string }>();
  const nav = useNavigate();
  const { user } = useAuth();
  const isDelivery = (user?.groups ?? []).some((g) => DELIVERY_ROLES.has(g));

  const activeTab: TabKey = isTabKey(tab) ? tab : "overview";

  const [model, setModel] = useState<DeliveryLatestResponse | null>(null);
  const [forecast, setForecast] = useState<ForecastPeriod | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const modelRes = await getLatestDeliveryModel(id!);
        if (cancelled) return;
        setModel(modelRes);
        const gmId = modelRes.gm_model?.id;
        if (gmId) {
          try {
            const f = await getLatestForecast(gmId);
            if (!cancelled) setForecast(f);
          } catch (err) {
            // A missing forecast is not a page error — render "no forecast yet".
            if (!(err instanceof ApiError) || err.status !== 404) throw err;
          }
        }
      } catch (err) {
        if (!cancelled) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const items: RecordTabItem[] = useMemo(() => {
    const gm = model?.gm_model ?? null;
    return TAB_ORDER.map((key) => ({
      value: key,
      label: TAB_LABELS[key],
      href: `/projects/${id}/${key}`,
      content:
        key === "overview" ? (
          <OverviewPane model={model} />
        ) : key === "financials" ? (
          <FinancialsPane
            model={model}
            forecast={forecast}
            isDelivery={isDelivery}
            onUpdateForecast={() =>
              nav(`/projects/${id}/financials?forecast=new`)
            }
          />
        ) : key === "staffing" ? (
          <StaffingTab
            rows={(gm?.resource_lines ?? []).map((line) => toStaffingRow(line))}
            showCost={false}
          />
        ) : key === "risks" ? (
          <RisksPane />
        ) : (
          <ActivityPane />
        ),
    }));
  }, [model, forecast, isDelivery, id, nav]);

  if (!id) {
    return (
      <EmptyState
        title="No project selected"
        description="Return to the portfolio and choose a project."
      />
    );
  }
  if (loading) {
    return (
      <div role="status" className="text-body text-text-secondary">
        Loading project…
      </div>
    );
  }
  if (error) {
    return (
      <ErrorState
        title="We couldn't load this project"
        description={
          error instanceof ApiError ? error.message : "Unexpected error."
        }
      />
    );
  }
  return (
    <div>
      <RecordHeader
        eyebrow="Delivery & actuals"
        title={`Project ${id.slice(0, 8)}`}
        identity={
          <>
            <span>Engagement: {model?.gm_model?.engagement_type ?? "Unknown"}</span>
            <span>
              Model:{" "}
              {model?.gm_model?.id
                ? model.gm_model.id.slice(0, 8)
                : "None"}
            </span>
          </>
        }
      />
      <div className="mt-4">
        <RecordTabs items={items} value={activeTab} />
      </div>
    </div>
  );
}

function OverviewPane({ model }: { model: DeliveryLatestResponse | null }) {
  const gm = model?.gm_model ?? null;
  if (!gm) {
    return (
      <EmptyState
        title="No signed scope yet"
        description="Open the SOW workspace to define scope, owners and milestones."
      />
    );
  }
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <SummaryCard label="Delivery pattern" value={gm.delivery_pattern ?? "—"} />
      <SummaryCard
        label="Contingency"
        value={gm.contingency_pct ? `${gm.contingency_pct}%` : "—"}
      />
      <SummaryCard
        label="Warranty days"
        value={gm.warranty_days != null ? String(gm.warranty_days) : "—"}
      />
      <SummaryCard
        label="Resource lines"
        value={String(gm.resource_lines.length)}
      />
    </div>
  );
}

function FinancialsPane({
  model,
  forecast,
  isDelivery,
  onUpdateForecast,
}: {
  model: DeliveryLatestResponse | null;
  forecast: ForecastPeriod | null;
  isDelivery: boolean;
  onUpdateForecast: () => void;
}) {
  const gm = model?.gm_model ?? null;
  const computed = gm?.computed ?? null;
  return (
    <section className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <FinancialRow
          label="Approved baseline"
          basis="Approved final GM — never overwritten"
          revenue={fmtMoney(gm?.revenue_us) ?? "Unavailable"}
          gm={fmtPercent(computed?.gm_us) ?? "Unavailable"}
        />
        <FinancialRow
          label="Current forecast"
          basis="Cost incurred + cost to complete"
          revenue={fmtMoney(forecast?.forecast_revenue) ?? "Unavailable"}
          gm={fmtPercent(forecast?.forecast_gm_us) ?? "Unavailable"}
        />
        <FinancialRow
          label="Period actuals"
          basis="Reconciled per source keys"
          revenue="Unavailable"
          gm="Unavailable"
        />
      </div>

      <div className="rounded-panel border border-divider bg-surface p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-section text-text">Forecast update</h3>
            <p className="mt-1 text-secondary text-text-secondary">
              A new forecast requires a rationale and creates a new version.
              A forecast below the floor opens a recovery decision but does
              not retroactively overwrite the approved GM.
            </p>
          </div>
          {isDelivery ? (
            <Button
              type="button"
              onClick={onUpdateForecast}
              data-testid="forecast-update"
            >
              Update forecast
            </Button>
          ) : (
            <StatusBadge
              tone="neutral"
              label="Delivery only"
              data-testid="forecast-update-gated"
            />
          )}
        </div>
      </div>
    </section>
  );
}

function FinancialRow({
  label,
  basis,
  revenue,
  gm,
}: {
  label: string;
  basis: string;
  revenue: string;
  gm: string;
}) {
  return (
    <div className="rounded-panel border border-divider bg-surface p-4">
      <div className="text-secondary text-text-secondary uppercase tracking-wide">
        {label}
      </div>
      <p className="mt-1 text-secondary text-text-secondary">{basis}</p>
      <dl className="mt-3 grid grid-cols-2 gap-y-1 text-body">
        <dt className="text-text-secondary">Revenue</dt>
        <dd className="tnum text-text text-right">{revenue}</dd>
        <dt className="text-text-secondary">GM %</dt>
        <dd className="tnum text-text text-right">{gm}</dd>
      </dl>
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-panel border border-divider bg-surface p-4">
      <div className="text-secondary text-text-secondary uppercase tracking-wide">
        {label}
      </div>
      <div className="mt-1 text-body text-text">{value}</div>
    </div>
  );
}

function RisksPane() {
  return (
    <EmptyState
      title="No verified source for risks yet"
      description="Change requests capture scope, price, margin and schedule impact when raised from the SOW workspace."
    />
  );
}

function ActivityPane() {
  return (
    <EmptyState
      title="No activity to show"
      description="Forecasts, reconciliations and staffing changes appear here as they occur."
    />
  );
}
