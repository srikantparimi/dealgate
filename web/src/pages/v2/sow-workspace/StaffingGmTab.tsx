/**
 * S9 — Staffing & GM tab.
 *
 * Opens pre-populated from the auto-staffed `gm_model` returned by the
 * SOW-confirmation flow. Editing a resource line **is the review** —
 * there is no separate "enter delivery model" wizard. Every derived
 * value carries a provenance chip (CLAUDE.md rule 10). A `Rebuild from
 * SOW` affordance appears when a newer SOW version is available.
 *
 * All numbers are Decimal strings owned by the server. This file does
 * no business math (CLAUDE.md rule 2). Editing a row flips the row's
 * provenance to `manual` — the server records the audit event.
 */
import { useMemo } from "react";
import { RefreshCw } from "lucide-react";
import type {
  DeliveryGmModel,
  DeliveryResourceLineRow,
} from "../../../api/client";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { Metric } from "../../../ui-v2/Metric";
import { MoneyCell } from "../../../ui-v2/MoneyCell";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import { Button } from "../../../ui-v2/primitives/button";
import { formatPercent, formatUsd } from "./format";
import type { WorkspaceSnapshot } from "./readiness";
import { CommercialsPanel } from "./staffing/CommercialsPanel";
import { GeographyCards } from "./staffing/GeographyCards";
import { ResourceLineRow } from "./staffing/ResourceLineRow";
import { GateSteps, type GateStep } from "../../../ui-v2/GateSteps";

type ViewerRole = "restricted" | "full";

export interface StaffingGmTabProps {
  snap: WorkspaceSnapshot;
  viewer?: ViewerRole;
  /** Fired when the reviewer edits a row inline. When absent the row
   * renders without an Edit affordance (read-only surface). */
  onSaveRow?: (
    id: string,
    patch: Partial<DeliveryResourceLineRow>,
  ) => void | Promise<void>;
  /** Fired when the reviewer asks the server to re-run auto-staffing
   * because a newer SOW version exists. */
  onRebuildFromSow?: () => void | Promise<void>;
}

export function StaffingGmTab({
  snap,
  viewer = "full",
  onSaveRow,
  onRebuildFromSow,
}: StaffingGmTabProps) {
  const gm = snap.gmModel;
  if (!gm) {
    return (
      <EmptyState
        title="No delivery model yet"
        description="Upload the SOW and the auto-staffing pipeline will populate this tab. This page never presents a blank grid."
        action={
          onRebuildFromSow ? (
            <Button type="button" onClick={onRebuildFromSow}>
              <RefreshCw className="h-4 w-4" aria-hidden /> Build from SOW
            </Button>
          ) : undefined
        }
      />
    );
  }
  const hasNewerSow =
    gm.latest_sow_version_id != null &&
    gm.latest_sow_version_id !== gm.sow_version_id;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-6">
        <StaffingGateSteps gm={gm} />
        <StaffingHeader gm={gm} hasNewerSow={hasNewerSow} onRebuildFromSow={onRebuildFromSow} />
        <GeographyCards computed={gm.computed ?? null} />
        <SummaryMetrics gm={gm} />
        <RevenueBreakdown gm={gm} />
        <CostBreakdown gm={gm} viewer={viewer} />
        <StaffingGrid gm={gm} viewer={viewer} onSaveRow={onSaveRow} />
        <PolicyFootnote gm={gm} />
      </div>
      <aside className="space-y-4">
        <CommercialsPanel computed={gm.computed ?? null} />
      </aside>
    </div>
  );
}

/**
 * Approval-progress GateSteps mirroring the prototype (lines 427–434). The
 * fourth step (CEO exception) enters the `hold` state — "Will trigger" —
 * when the current draft is below floor and the reviewer has not yet
 * submitted the package.
 */
function StaffingGateSteps({ gm }: { gm: DeliveryGmModel }) {
  const c = gm.computed;
  const usGm = c?.gm_us != null ? Number(c.gm_us) : null;
  const inGm = c?.gm_india != null ? Number(c.gm_india) : null;
  // Convert 0.278 → 27.8 style for a fair floor comparison.
  const toPct = (n: number | null) => (n == null ? null : n <= 1 ? n * 100 : n);
  const usPct = toPct(usGm);
  const inPct = toPct(inGm);
  const belowFloor =
    (usPct != null && usPct < 35) || (inPct != null && inPct < 50);
  const complete = c?.complete === true;
  const steps: GateStep[] = [
    { id: "intake", label: "Intake", state: "done" },
    { id: "scope-gm", label: "Scope & GM", state: "now" },
    { id: "reviews", label: "Function reviews", state: "pending" },
    {
      id: "ceo",
      label: "CEO exception",
      state: belowFloor && complete ? "hold" : "pending",
    },
    { id: "signature", label: "Signature", state: "pending" },
    { id: "handoff", label: "Handoff", state: "pending" },
  ];
  return <GateSteps steps={steps} ariaLabel="Approval progress" />;
}

function StaffingHeader({
  gm,
  hasNewerSow,
  onRebuildFromSow,
}: {
  gm: DeliveryGmModel;
  hasNewerSow: boolean;
  onRebuildFromSow?: () => void | Promise<void>;
}) {
  return (
    <section
      aria-label="Staffing header"
      className="flex flex-wrap items-center gap-3 rounded-panel border border-divider bg-surface p-4"
    >
      <div>
        <p className="text-secondary uppercase tracking-wide text-text-secondary">
          Auto-derived staffing plan
        </p>
        <p className="text-body text-text">
          GM version <span className="tnum">{gm.id.slice(-8)}</span> ·
          {gm.resource_lines.length} resource line
          {gm.resource_lines.length === 1 ? "" : "s"}
        </p>
      </div>
      <div className="ml-auto flex items-center gap-2">
        {hasNewerSow ? (
          <StatusBadge tone="warning" label="Newer SOW extraction available" />
        ) : null}
        {onRebuildFromSow ? (
          <Button
            type="button"
            variant={hasNewerSow ? "primary" : "secondary"}
            onClick={onRebuildFromSow}
            data-testid="staffing-rebuild-from-sow"
          >
            <RefreshCw className="h-4 w-4" aria-hidden /> Rebuild from SOW
          </Button>
        ) : null}
      </div>
    </section>
  );
}

function SummaryMetrics({ gm }: { gm: DeliveryGmModel }) {
  const c = gm.computed;
  const revenue = c
    ? formatUsd(String(Number(c.revenue_us || 0) + Number(c.revenue_india || 0)))
    : null;
  const cost = c
    ? formatUsd(String(Number(c.cost_us || 0) + Number(c.cost_india || 0)))
    : null;
  const profit =
    c && revenue && cost
      ? formatUsd(
          String(
            Number(c.revenue_us || 0) +
              Number(c.revenue_india || 0) -
              (Number(c.cost_us || 0) + Number(c.cost_india || 0)),
          ),
        )
      : null;
  const gmBlended = formatPercent(c?.gm_blended ?? null);

  return (
    <section aria-label="Commercial totals" className="grid gap-3 sm:grid-cols-4">
      <Metric label="Revenue" value={revenue ?? "Unavailable"} />
      <Metric label="Delivery cost" value={cost ?? "Unavailable"} />
      <Metric label="Gross profit" value={profit ?? "Unavailable"} />
      <Metric label="Combined GM" value={gmBlended ?? "Unavailable"} />
    </section>
  );
}

function RevenueBreakdown({ gm }: { gm: DeliveryGmModel }) {
  const sections = useMemo(
    () => [
      {
        key: "fixed_fee",
        label: "Fixed fee",
        value: gm.revenue_us ?? null,
      },
      { key: "milestones", label: "Milestones", value: null as string | null },
      { key: "tandm", label: "Time & materials", value: null as string | null },
      { key: "recurring", label: "Recurring", value: null as string | null },
      { key: "one_time", label: "One-time", value: null as string | null },
      { key: "discounts", label: "Discounts", value: null as string | null },
    ],
    [gm.revenue_us],
  );
  return (
    <section
      aria-label="Revenue breakdown"
      className="rounded-panel border border-divider bg-surface p-4"
    >
      <h2 className="text-section text-text mb-3">Revenue breakdown</h2>
      <p className="text-secondary text-text-secondary mb-3">
        Approved cost definition, rate-card version and FX source govern
        these figures; only the pricing model varies by category.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {sections.map((s) => (
          <div
            key={s.key}
            className="flex items-center justify-between rounded-control border border-divider p-3"
          >
            <span className="text-body text-text">{s.label}</span>
            <MoneyCell value={formatUsd(s.value) ?? undefined} />
          </div>
        ))}
      </div>
    </section>
  );
}

function CostBreakdown({
  gm,
  viewer,
}: {
  gm: DeliveryGmModel;
  viewer: ViewerRole;
}) {
  const categoryTotals: Record<string, number> = {};
  for (const line of gm.cost_lines) {
    const amount = Number(line.amount);
    if (!Number.isFinite(amount)) continue;
    categoryTotals[line.category] = (categoryTotals[line.category] ?? 0) + amount;
  }
  const sections = [
    { key: "staffing", label: "Staffing", value: null as number | null },
    { key: "subcontractor", label: "Contractors", value: categoryTotals["subcontractor"] ?? null },
    { key: "burden", label: "Benefits & burden", value: null as number | null },
    { key: "recruiting", label: "Recruiting & setup", value: null as number | null },
    { key: "delivery_mgmt", label: "Delivery management", value: null as number | null },
    { key: "tools", label: "Licences & tools", value: categoryTotals["tools"] ?? null },
    { key: "travel", label: "Travel", value: categoryTotals["travel"] ?? null },
    { key: "contingency", label: "Contingency", value: null as number | null },
  ];

  return (
    <section
      aria-label="Cost breakdown"
      className="rounded-panel border border-divider bg-surface p-4"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-section text-text">Cost breakdown</h2>
        {viewer === "restricted" ? (
          <StatusBadge tone="neutral" label="Aggregated view" />
        ) : null}
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        {sections.map((s) => (
          <div
            key={s.key}
            className="flex items-center justify-between rounded-control border border-divider p-3"
          >
            <span className="text-body text-text">{s.label}</span>
            <MoneyCell
              value={s.value != null ? (formatUsd(String(s.value)) ?? undefined) : undefined}
            />
          </div>
        ))}
      </div>
    </section>
  );
}

function StaffingGrid({
  gm,
  viewer,
  onSaveRow,
}: {
  gm: DeliveryGmModel;
  viewer: ViewerRole;
  onSaveRow?: StaffingGmTabProps["onSaveRow"];
}) {
  const rows = gm.resource_lines;
  if (rows.length === 0) {
    return (
      <EmptyState
        title="Auto-staffing produced no resource lines"
        description="This is rare — usually the SOW is silent on staffing. Use Rebuild from SOW after uploading a corrected extraction, or add lines manually with a written justification."
      />
    );
  }
  const toHire = rows.filter((r) => r.person_name == null).length;
  return (
    <section
      aria-label="Staffing grid"
      className="rounded-panel border border-divider bg-surface p-4"
    >
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-section text-text">Staffing grid</h2>
          <p className="text-secondary text-text-secondary">
            {rows.length} resource lines · {toHire} to hire ·{" "}
            {viewer === "restricted"
              ? "employee compensation hidden"
              : "loaded cost visible"}
          </p>
        </div>
      </div>
      <div
        role="region"
        aria-label="Staffing grid scroll region"
        className="overflow-x-auto"
      >
        <table className="min-w-full text-body">
          <thead>
            <tr className="text-left text-text-secondary text-secondary uppercase">
              <th className="py-2 pr-3">Role</th>
              <th className="py-2 pr-3">Seniority</th>
              <th className="py-2 pr-3">Location</th>
              <th className="py-2 pr-3 text-right">Bill rate</th>
              <th className="py-2 pr-3 text-right">Hours</th>
              <th className="py-2 pr-3 text-right">
                {viewer === "restricted" ? "Cost band" : "Cost"}
              </th>
              <th className="py-2 pr-3 text-right">Revenue</th>
              <th className="py-2 pr-3 text-right">GM</th>
              <th className="py-2 pr-3">Provenance</th>
              <th className="py-2 pr-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <ResourceLineRow
                key={row.id}
                row={row}
                viewer={viewer}
                onSave={onSaveRow}
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PolicyFootnote({ gm }: { gm: DeliveryGmModel }) {
  return (
    <section
      aria-label="Policy footnote"
      className="rounded-panel border border-divider bg-surface p-4 text-secondary text-text-secondary"
    >
      <p>
        Approved cost definition: fully loaded (staffing + burden +
        overhead). Rate-card version and FX source (fixed at SOW date) are
        stamped on the saved GM version {gm.id.slice(-8)}.
      </p>
    </section>
  );
}
