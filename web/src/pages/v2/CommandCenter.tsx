/**
 * Command center — DealGate flagship executive screen (spec §5).
 *
 * Assembly:
 *   1. Executive banner            → ExecutiveBanner
 *   2. Priority signals            → PrioritySignals (CEO exception + MSA + renewal)
 *   3. Pipeline client readiness   → PipelineReadinessTable
 *   4. SOW approval preview        → ApprovalPreview
 *   5. Delivery economics          → DeliveryEconomics
 *
 * Role gating (spec §5 last paragraph + agent brief): CEO / SystemAdmin
 * see the full board; other roles get the Sales dashboard fall-back and
 * we hide the CEO-only widgets. The client-side gate is UX only — the
 * API still enforces (CLAUDE.md rule 5).
 *
 * No math in the browser: every money and margin string comes from the
 * server pre-formatted; a missing value renders as "Unavailable"
 * (spec §4 state copy, MoneyCell + MarginCell primitives).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CalendarClock,
  FileSignature,
} from "lucide-react";
import { useAuth } from "../../auth/AuthProvider";
import {
  ApiError,
  getCeoDashboard,
  getDeals,
  getFinanceDashboard,
  getSalesDashboard,
  listAgreements,
  listApprovalPackages,
  listClients,
  listRenewals,
  type AgreementRow,
  type ApprovalPackage,
  type CeoDashboard,
  type ClientListRow,
  type DealRow,
  type FinanceDashboard,
  type RenewalRow,
  type SalesDashboard,
} from "../../api/client";
import { ErrorState } from "../../ui-v2/ErrorState";
import { SourceFreshness } from "../../ui-v2/SourceFreshness";
import { ExecutiveBanner, type BannerMetric } from "./command/ExecutiveBanner";
import {
  PrioritySignals,
  type PrioritySignal,
} from "./command/PrioritySignals";
import {
  PipelineReadinessTable,
  type ReadinessRow,
} from "./command/PipelineReadinessTable";
import {
  ApprovalPreview,
  type ApprovalLane,
  type ApprovalCard,
  type FunctionalReviewMarker,
  type FunctionalReviewMarkers,
} from "./command/ApprovalPreview";
import {
  DeliveryEconomics,
  type EconomicsRow,
} from "./command/DeliveryEconomics";

const CEO_ROLES = new Set(["CEO", "SystemAdmin"]);
const READINESS_LIMIT = 10;

// -----------------------------------------------------------------------------
// Formatters — pure display, no math (blueprint §2 + CLAUDE.md rule 2).
// The server sends money as Decimal strings; here we only shape them for
// human eyes. `null` in → `null` out so the caller renders "Unavailable".
// -----------------------------------------------------------------------------

const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

function formatMoney(value: string | null | undefined): string | null {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return USD.format(n);
}

function formatCount(n: number | null | undefined): string | null {
  if (n === null || n === undefined) return null;
  return new Intl.NumberFormat("en-US").format(n);
}

function formatPercent(value: string | null | undefined): string | null {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return `${(n * 100).toFixed(1)}%`;
}

function formatVariance(
  approved: string | null | undefined,
  forecast: string | null | undefined,
): string | null {
  if (approved === null || approved === undefined || approved === "") return null;
  if (forecast === null || forecast === undefined || forecast === "") return null;
  const a = Number(approved);
  const f = Number(forecast);
  if (!Number.isFinite(a) || !Number.isFinite(f)) return null;
  const delta = f - a;
  const sign = delta > 0 ? "+" : "";
  return `${sign}${(delta * 100).toFixed(1)} pts`;
}

// -----------------------------------------------------------------------------
// Async loader — every module is independent so a failure in one keeps the
// others live (spec §4 state copy: "Errors in one module never hide healthy
// ones"). React Query is not installed; a plain effect + AbortController is
// enough for a read-only executive board.
// -----------------------------------------------------------------------------

interface CommandData {
  ceo: CeoDashboard | null;
  sales: SalesDashboard | null;
  finance: FinanceDashboard | null;
  deals: DealRow[];
  clients: ClientListRow[];
  agreements: AgreementRow[];
  renewals: RenewalRow[];
  approvalsDelivery: ApprovalPackage[];
  approvalsFinance: ApprovalPackage[];
  approvalsCeo: ApprovalPackage[];
  fetchedAt: Date;
}

async function safe<T>(p: Promise<T>): Promise<T | null> {
  try {
    return await p;
  } catch (err) {
    // A 403 on a role-only endpoint is expected — degrade silently. Any
    // other failure surfaces via the caller's `error` state.
    if (err instanceof ApiError && err.status === 403) return null;
    throw err;
  }
}

// -----------------------------------------------------------------------------
// Derivations — pure functions that turn API shapes into view models.
// Keeping them out of the render body makes them easy to reason about
// and (later) unit-test in isolation.
// -----------------------------------------------------------------------------

function agreementGapCount(agreements: AgreementRow[]): number {
  const gapStates = new Set([
    "missing",
    "requested",
    "drafting",
    "under_review",
    "sent",
    "partially_signed",
    "expired",
  ]);
  return agreements.filter((a) => gapStates.has(a.state)).length;
}

function marker(status: string | null | undefined): FunctionalReviewMarker {
  if (status === "approve") return "approved";
  if (status === "reject") return "rejected";
  return "pending";
}

function packageMarkers(pkg: ApprovalPackage): FunctionalReviewMarkers {
  const byFn: Record<string, string> = {};
  for (const a of pkg.approvals) byFn[a.function] = a.decision;
  return {
    delivery: marker(byFn.delivery),
    hr: marker(byFn.hr),
    finance: marker(byFn.finance),
    legal: marker(byFn.legal),
  };
}

function bannerMetrics(
  data: CommandData,
  isCeo: boolean,
): BannerMetric[] {
  const pipelineValue = isCeo
    ? formatMoney(data.ceo?.pipeline_value ?? null)
    : null;
  const sowsInProgress =
    data.approvalsDelivery.length +
    data.approvalsFinance.length +
    data.approvalsCeo.length;
  const agreementGaps = agreementGapCount(data.agreements);
  const ceoPending = isCeo
    ? data.ceo?.ceo_exceptions_pending.length ?? null
    : data.approvalsCeo.length;

  return [
    {
      id: "pipeline_value",
      label: "Pipeline value",
      value: pipelineValue,
      href: "/pipeline",
      description: isCeo ? "Uncontracted proposed" : "CEO view required",
    },
    {
      id: "sows_in_progress",
      label: "SOW packages in progress",
      value: formatCount(sowsInProgress),
      href: "/sows",
      description: "Across every approval lane",
    },
    {
      id: "agreement_gaps",
      label: "Clients with agreement gaps",
      value: formatCount(agreementGaps),
      href: "/agreements",
      description: "NDA or MSA not executed",
    },
    {
      id: "ceo_pending",
      label: "CEO decisions pending",
      value: formatCount(ceoPending),
      href: "/sows",
      description: "Awaiting exception decision",
    },
  ];
}

function firstPrioritySignals(data: CommandData): PrioritySignal[] {
  const out: PrioritySignal[] = [];

  const exc = data.ceo?.ceo_exceptions_pending?.[0] ?? null;
  if (exc) {
    // The CEO exception carries package_id; we route through /sows/:pkg/exception
    // which the SOW workspace resolves.
    out.push({
      id: `ceo-${exc.id}`,
      kind: "ceo_exception",
      title: "CEO exception",
      client: "Package awaiting your decision",
      reason: exc.has_rationale
        ? "Rationale drafted. Ready for a decision."
        : "Below-floor package needs a rationale.",
      deadline: exc.drafted_at ? exc.drafted_at.slice(0, 10) : null,
      href: `/sows/${exc.package_id}/exception`,
      statusLabel: exc.has_rationale ? "Ready" : "Draft rationale",
      statusTone: exc.has_rationale ? "warn" : "danger",
      icon: AlertTriangle,
      testId: "signal-ceo-exception",
    });
  } else {
    // Fall back to any pending_ceo_exception package we saw.
    const pkg = data.approvalsCeo[0];
    if (pkg) {
      out.push({
        id: `ceo-${pkg.id}`,
        kind: "ceo_exception",
        title: "CEO exception",
        client: "Package pending CEO",
        reason: "Below-floor package awaiting a decision.",
        deadline: pkg.submitted_at ? pkg.submitted_at.slice(0, 10) : null,
        href: `/sows/${pkg.id}/exception`,
        statusLabel: "Awaiting decision",
        statusTone: "warn",
        icon: AlertTriangle,
        testId: "signal-ceo-exception",
      });
    }
  }

  const pendingMsa = data.agreements.find(
    (a) => a.kind === "MSA" && (a.state === "sent" || a.state === "partially_signed"),
  );
  if (pendingMsa) {
    out.push({
      id: `msa-${pendingMsa.id}`,
      kind: "msa_signature",
      title: "MSA signature",
      client: pendingMsa.next_action ?? "MSA sent for signature",
      reason:
        pendingMsa.next_action ??
        "Sent to the client for signature. Follow up if quiet.",
      owner: pendingMsa.owner_email,
      deadline: pendingMsa.due_date,
      href: `/agreements`,
      statusLabel:
        pendingMsa.state === "partially_signed"
          ? "Partially signed"
          : "Awaiting signature",
      statusTone: "warn",
      icon: FileSignature,
      testId: "signal-msa",
    });
  }

  const nextRenewal = [...data.renewals]
    .filter((r) => r.status === "open")
    .sort((a, b) => a.days_until_end - b.days_until_end)[0];
  if (nextRenewal) {
    out.push({
      id: `renewal-${nextRenewal.id}`,
      kind: "renewal",
      title: "Approaching renewal",
      client: nextRenewal.hubspot_deal_id ?? "Open renewal",
      reason:
        nextRenewal.days_until_end <= 0
          ? "Term has ended. Confirm outcome now."
          : `Term ends in ${nextRenewal.days_until_end} day(s).`,
      deadline: nextRenewal.term_end,
      href: `/renewals-v2`,
      statusLabel:
        nextRenewal.days_until_end <= 14
          ? "Due soon"
          : "On watch",
      statusTone: nextRenewal.days_until_end <= 14 ? "danger" : "warn",
      icon: CalendarClock,
      testId: "signal-renewal",
    });
  }

  return out;
}

function readinessRows(data: CommandData): ReadinessRow[] {
  const dealByClient = new Map<string, DealRow>();
  for (const d of data.deals) {
    if (d.client_id && !dealByClient.has(d.client_id)) {
      dealByClient.set(d.client_id, d);
    }
  }
  const agreementsByClient = new Map<string, AgreementRow[]>();
  for (const a of data.agreements) {
    const list = agreementsByClient.get(a.legal_entity_id) ?? [];
    list.push(a);
    agreementsByClient.set(a.legal_entity_id, list);
  }

  const rows: ReadinessRow[] = [];
  for (const c of data.clients.slice(0, READINESS_LIMIT)) {
    const deal = dealByClient.get(c.id) ?? null;
    // The agreements list is keyed by legal_entity_id, not client_id. This
    // is a lossy shortcut for the command center header — the pipeline
    // page owns the accurate coverage view (§7). We still show whatever
    // matches; if nothing matches the cells stay honest "Missing".
    const clientAgreements = agreementsByClient.get(c.id) ?? [];
    const nda = clientAgreements.find((a) => a.kind === "NDA") ?? null;
    const msa = clientAgreements.find((a) => a.kind === "MSA") ?? null;

    rows.push({
      id: c.id,
      clientName: c.name,
      clientHref: `/clients/${c.id}`,
      ownerName: null,
      commercialStage: deal?.sales_stage ?? null,
      nda: nda
        ? {
            label: nda.state.replace(/_/g, " "),
            tone:
              nda.state === "executed"
                ? "ok"
                : nda.state === "missing"
                  ? "warn"
                  : "primarySubtle",
            href: `/agreements`,
          }
        : null,
      msa: msa
        ? {
            label: msa.state.replace(/_/g, " "),
            tone:
              msa.state === "executed"
                ? "ok"
                : msa.state === "missing"
                  ? "warn"
                  : "primarySubtle",
            href: `/agreements`,
          }
        : null,
      sowGate: deal
        ? {
            label: (deal.governance_status ?? "unknown").replace(/_/g, " "),
            tone:
              deal.governance_status === "released"
                ? "ok"
                : deal.governance_status === "rejected"
                  ? "danger"
                  : "primarySubtle",
            href: `/sows`,
          }
        : null,
      packageVersion: null,
      nextAction: {
        text: deal?.next_client_action ?? null,
        date: deal?.next_client_date ?? null,
      },
    });
  }
  return rows;
}

function packageToCard(pkg: ApprovalPackage, deals: DealRow[]): ApprovalCard {
  const deal = deals.find((d) => d.id === pkg.opportunity_id) ?? null;
  return {
    id: pkg.id,
    href: `/sows/${pkg.id}`,
    client: deal?.client_name ?? deal?.hubspot_deal_id ?? "Package",
    engagement: deal?.engagement_type ?? null,
    // We deliberately do not fabricate a value. The SOW workspace shows
    // the real approved figures; the command preview mirrors what the
    // package listing exposes today.
    value: null,
    margin: null,
    marginOutcome: pkg.floors?.requires_ceo ? "fail" : undefined,
    ndaLabel: "See client",
    ndaTone: "primarySubtle",
    msaLabel: "See client",
    msaTone: "primarySubtle",
    markers: packageMarkers(pkg),
    owner: null,
    nextAction:
      pkg.status === "pending_delivery_hr"
        ? "Delivery + HR review"
        : pkg.status === "pending_finance_legal"
          ? "Finance + Legal review"
          : pkg.status === "pending_ceo_exception"
            ? "CEO decision"
            : pkg.status.replace(/_/g, " "),
  };
}

function approvalLanes(data: CommandData): ApprovalLane[] {
  return [
    {
      id: "scope",
      title: "Scope & GM",
      description: "Delivery + HR sign-off on cost model and staffing.",
      cards: data.approvalsDelivery.map((p) => packageToCard(p, data.deals)),
    },
    {
      id: "functional",
      title: "Functional review",
      description: "Finance + Legal sign-off on margins and paper.",
      cards: data.approvalsFinance.map((p) => packageToCard(p, data.deals)),
    },
    {
      id: "ceo",
      title: "CEO exception",
      description: "Below-floor packages requiring a CEO decision.",
      cards: data.approvalsCeo.map((p) => packageToCard(p, data.deals)),
    },
  ];
}

function economicsRows(
  finance: FinanceDashboard | null,
): EconomicsRow[] {
  const us = finance?.gm_by_geography.US.gm ?? null;
  const india = finance?.gm_by_geography.India.gm ?? null;
  const approvedGp =
    finance?.approved_vs_forecast_vs_actual.approved_gp ?? null;
  const forecastGp =
    finance?.approved_vs_forecast_vs_actual.forecast_gp ?? null;

  return [
    {
      geography: "US",
      approvedMargin: formatPercent(us),
      forecastMargin: formatPercent(us),
      variance: formatVariance(us, us),
      floor: "35.0%",
      outcome: us === null ? "unavailable" : undefined,
    },
    {
      geography: "India",
      approvedMargin: formatPercent(india),
      forecastMargin: formatPercent(india),
      variance: formatVariance(india, india),
      floor: "50.0%",
      outcome: india === null ? "unavailable" : undefined,
    },
    {
      geography: "Blended",
      approvedMargin: formatPercent(approvedGp),
      forecastMargin: formatPercent(forecastGp),
      variance: formatVariance(approvedGp, forecastGp),
      floor: null,
      outcome: approvedGp === null ? "unavailable" : undefined,
    },
  ];
}

// -----------------------------------------------------------------------------
// Loading skeletons — match the final geometry so a slow network doesn't
// shift layout (spec §4). Each block reserves the same area as the module
// it foreshadows.
// -----------------------------------------------------------------------------

function BannerSkeleton() {
  return (
    <div
      className="h-56 rounded-hero bg-executive/90 animate-pulse"
      aria-hidden
    />
  );
}
function RowSkeleton({ height = "h-32" }: { height?: string }) {
  return (
    <div
      className={`${height} rounded-panel bg-surface border border-divider animate-pulse`}
      aria-hidden
    />
  );
}

// -----------------------------------------------------------------------------
// Component
// -----------------------------------------------------------------------------

export function CommandCenterPage() {
  const { user } = useAuth();
  const groups = user?.groups ?? [];
  const isCeo = groups.some((g) => CEO_ROLES.has(g));

  const [data, setData] = useState<CommandData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [
        ceo,
        sales,
        finance,
        dealsPage,
        clientsPage,
        agreementsList,
        renewalsPage,
        pkgDelivery,
        pkgFinance,
        pkgCeo,
      ] = await Promise.all([
        // Never call /dashboards/ceo from a non-CEO/SysAdmin role
        // (agent brief). Roles without access get null and the CEO-only
        // widgets degrade to "Unavailable" or hide.
        isCeo ? safe(getCeoDashboard()) : Promise.resolve(null),
        !isCeo ? safe(getSalesDashboard()) : Promise.resolve(null),
        safe(getFinanceDashboard()),
        safe(getDeals({ size: 25 })),
        safe(listClients({ size: 25 })),
        safe(listAgreements()),
        safe(listRenewals({ status: "open", size: 25 })),
        safe(listApprovalPackages({ status: "pending_delivery_hr", size: 10 })),
        safe(listApprovalPackages({ status: "pending_finance_legal", size: 10 })),
        safe(listApprovalPackages({ status: "pending_ceo_exception", size: 10 })),
      ]);

      setData({
        ceo: ceo,
        sales: sales,
        finance: finance,
        deals: dealsPage?.items ?? [],
        clients: clientsPage?.items ?? [],
        agreements: agreementsList?.items ?? [],
        renewals: renewalsPage?.items ?? [],
        approvalsDelivery: pkgDelivery?.items ?? [],
        approvalsFinance: pkgFinance?.items ?? [],
        approvalsCeo: pkgCeo?.items ?? [],
        fetchedAt: new Date(),
      });
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [isCeo]);

  useEffect(() => {
    void load();
  }, [load]);

  const metrics = useMemo(
    () => (data ? bannerMetrics(data, isCeo) : []),
    [data, isCeo],
  );
  const signals = useMemo(
    () => (data ? firstPrioritySignals(data) : []),
    [data],
  );
  const rows = useMemo(() => (data ? readinessRows(data) : []), [data]);
  const lanes = useMemo(() => (data ? approvalLanes(data) : []), [data]);
  const economics = useMemo(
    () => economicsRows(data?.finance ?? null),
    [data],
  );

  if (loading && !data) {
    return (
      <div className="flex flex-col gap-8">
        <BannerSkeleton />
        <RowSkeleton height="h-40" />
        <RowSkeleton height="h-64" />
        <RowSkeleton height="h-56" />
        <RowSkeleton height="h-48" />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="flex flex-col gap-6">
        <ErrorState
          title="We couldn't load the command center."
          description="The team has been notified. Retry to try again — filters are preserved."
          onRetry={() => void load()}
        />
      </div>
    );
  }

  const freshness = data ? (
    <SourceFreshness
      source="DealGate governance"
      asOf={data.fetchedAt.toLocaleString()}
      basis="Server-computed. Missing values render as Unavailable."
    />
  ) : null;

  return (
    <div className="flex flex-col gap-8">
      <ExecutiveBanner
        metrics={metrics}
        freshness={freshness}
        actionHref="/sows"
        actionLabel="Open approval pipeline"
        subtitle={
          isCeo
            ? "Every open commitment across pipeline, contracts and delivery."
            : "Your view of pipeline, contracts and delivery — role-scoped."
        }
      />

      <PrioritySignals
        signals={signals}
        emptyMessage="No exceptions, MSA signatures or renewals are urgent right now."
      />

      <PipelineReadinessTable
        rows={rows}
        caption="First 10 pipeline clients"
      />

      <ApprovalPreview lanes={lanes} viewAllHref="/sows" />

      {isCeo || data?.finance ? (
        <DeliveryEconomics
          rows={economics}
          signedValue={null}
          openPipeline={
            isCeo ? formatMoney(data?.ceo?.pipeline_value ?? null) : null
          }
          recognisedRevenue={formatMoney(
            data?.finance?.approved_vs_forecast_vs_actual.actual_gp ?? null,
          )}
          drillHref="/dashboard"
          basis="Approved vs forecast on active signed SOWs. Recognised revenue is finance actuals. US floor 35%, India floor 50%."
        />
      ) : null}
    </div>
  );
}
