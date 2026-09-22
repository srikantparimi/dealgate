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
import { useCallback, useState } from "react";
import { RefreshCw } from "lucide-react";
import type {
  DeliveryGmModel,
  DeliveryResourceLineRow,
} from "../../../api/client";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import { Button } from "../../../ui-v2/primitives/button";
import type { WorkspaceSnapshot } from "./readiness";
import { FinanceGmPanel, type FinanceGmResult } from "./staffing/FinanceGmPanel";
import { ResourceLineRow } from "./staffing/ResourceLineRow";
import { GateSteps, type GateStep } from "../../../ui-v2/GateSteps";
import { ResourcesEditor } from "./ResourcesEditor";

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
  const [preview, setPreview] = useState<FinanceGmResult | null>(null);
  const showComputed = useCallback((result: FinanceGmResult | null) => setPreview(result ?? {}), []);
  if (!gm) {
    // No GM model yet. This used to be a dead end — an empty state whose only
    // action was "Build from SOW", which cannot work when the SOW lists no
    // resources (most fixed-fee work). The editor belongs here most of all:
    // this is the state where someone has to enter the plan.
    return (
      <div className="space-y-6">
        <EmptyState
          title="No delivery model yet"
          description="Nothing was derivable from the SOW, so enter the team below. The gross margin is calculated from it as soon as the rows are costed."
          action={
            onRebuildFromSow ? (
              <Button type="button" onClick={onRebuildFromSow}>
                <RefreshCw className="h-4 w-4" aria-hidden /> Build from SOW
              </Button>
            ) : undefined
          }
        />
        {snap.deal?.id ? <ResourcesEditor opportunityId={snap.deal.id} /> : null}
      </div>
    );
  }
  const hasNewerSow =
    gm.latest_sow_version_id != null &&
    gm.latest_sow_version_id !== gm.sow_version_id;

  return (
    <div className="grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="min-w-0 space-y-6">
        <StaffingGateSteps gm={gm} />
        <StaffingHeader gm={gm} hasNewerSow={hasNewerSow} onRebuildFromSow={onRebuildFromSow} />
        <StaffingGrid gm={gm} viewer={viewer} onSaveRow={onSaveRow} />
        {/* Editable for the life of the SOW, not only at the gate on the way
         * to confirmation. Before signature it is a proposal; after, a change
         * is dated and every approver is told with both margins. */}
        {snap.deal?.id ? <ResourcesEditor opportunityId={snap.deal.id} onComputed={showComputed} /> : null}
        <PolicyFootnote gm={gm} />
      </div>
      <aside className="space-y-4">
        <FinanceGmPanel result={preview ?? { ...gm.computed, ...gm.computed?.policy, gm_version: gm.version }} locations={gm.resource_lines.map((line) => line.location)} />
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
  const belowFloor = c?.policy.requires_ceo === true;
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
                {viewer === "restricted" ? "Cost band" : "Cost /hr"}
              </th>
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
                fixedFee={gm.engagement_type === "fixed_price" || gm.engagement_type === "assessment"}
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
