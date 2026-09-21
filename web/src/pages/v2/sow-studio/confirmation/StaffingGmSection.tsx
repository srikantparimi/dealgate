/**
 * Section 5 — Staffing & GM.
 *
 * Left: the auto-staffed grid with a provenance chip per line. This is
 * the "editing is the review" surface — a Delivery lead can add / edit /
 * remove lines. The Section owns no math: every number comes from the
 * API-computed floors block (spec §21 · rule 2).
 *
 * Right: revenue · cost · GM per component with a `FloorBar` per row
 * and a bold pass/fail summary.
 */
import type {
  SowConfirmationPayload,
  SowConfirmationStaffingLine,
} from "../../../../api/client";
import { FloorBar } from "../../../../ui-v2/FloorBar";
import { MoneyCell } from "../../../../ui-v2/MoneyCell";
import { StatusBadge } from "../../../../ui-v2/StatusBadge";
import { Section } from "./Section";
import { ProvenanceChip } from "./provenance";
import type { SowProvenance } from "../../../../api/client";
import { formatPercent, formatUsd } from "../../sow-workspace/format";

export interface StaffingGmSectionProps {
  payload: SowConfirmationPayload;
}

/**
 * Allocation lives on the wire as a 0..1 fraction (Decimal, e.g. "1.0000"
 * for a full-time line). The UI shows it as a percent — one canonical unit
 * on the wire, `× 100` at render (Kanna 20-Sep directive rule 5).
 * `"1.0000"` used to render as `1.0000%`; it now renders as `100%`.
 */
export function formatAllocationPct(raw: string | number): string {
  const n = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(n)) return String(raw);
  const pct = n * 100;
  // Whole numbers render without decimals; fractions get one decimal so
  // "50%" stays "50%" and "12.5%" stays "12.5%".
  return Number.isInteger(pct) ? String(pct) : pct.toFixed(1);
}

export function StaffingGmSection({ payload }: StaffingGmSectionProps) {
  const lines = payload.staffing.lines;
  const gm = payload.gm_model;
  const floors = payload.floors;
  const usPass = floors.us_pass !== false;
  const indiaPass = floors.india_pass !== false;
  const allPass = usPass && indiaPass;
  const fixedPrice = (gm?.engagement_type ?? payload.engagement.primary.type) === "fixed_price";
  const usApplicable = lines.some((line) => line.location === "US") || floors.gm_us != null;
  const indiaApplicable = lines.some((line) => line.location === "India") || floors.gm_india != null;
  const computed = (usApplicable || indiaApplicable) &&
    (!usApplicable || floors.gm_us != null) &&
    (!indiaApplicable || floors.gm_india != null) &&
    floors.gm_blended != null && !floors.reason && !floors.error;

  return (
    <Section
      id="section-staffing"
      title="Staffing & GM"
      description='Editing this grid is the review — the auto-plan opens pre-populated.'
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="min-w-0">
          {lines.length ? (
            <div
              role="table"
              aria-label="Staffing grid"
              className="overflow-x-auto rounded-panel border border-divider bg-surface"
            >
              <div
                role="row"
                className="grid min-w-[800px] grid-cols-[minmax(120px,2fr)_70px_120px_100px_70px_90px_100px] gap-2 border-b border-divider bg-surface-sunken px-3 py-2 text-[11px] uppercase tracking-wide text-text-secondary"
              >
                <div role="columnheader">Role · seniority</div>
                <div role="columnheader">Location</div>
                <div role="columnheader" className="text-right">
                  Bill rate
                </div>
                <div role="columnheader" className="text-right">
                  Cost /hr
                </div>
                <div role="columnheader" className="text-right">
                  Hours
                </div>
                <div role="columnheader" className="text-right">
                  Allocation
                </div>
                <div role="columnheader">Provenance</div>
              </div>
              <ul className="divide-y divide-divider">
                {lines.map((line, i) => (
                  <StaffingRow key={i} line={line} fixedPrice={fixedPrice} />
                ))}
              </ul>
            </div>
          ) : (
            <p className="rounded-panel border border-warning/40 bg-warning-surface p-3 text-warning">
              No staffing lines yet — the extractor did not find a resource
              table or a coverage plan. Add lines to compute a GM.
            </p>
          )}
          {payload.staffing.warnings.length ? (
            <ul className="mt-3 space-y-1 text-secondary text-text-secondary">
              {payload.staffing.warnings.map((w, i) => (
                <li key={i} data-testid="staffing-warning">
                  · {w}
                </li>
              ))}
            </ul>
          ) : null}
        </div>

        <aside
          className="min-w-0 rounded-panel border border-divider bg-surface p-3 tnum"
          aria-label="GM by component"
        >
          <h3 className="text-secondary font-medium text-text-secondary">
            Component GM
          </h3>
          <div className="mt-3 flex flex-col gap-4">
            <ComponentBar
              label="US"
              value={floors.gm_us ?? null}
              floor={floors.us_floor ?? "0.35"}
              pass={usPass}
              applicable={usApplicable}
            />
            <ComponentBar
              label="India"
              value={floors.gm_india ?? null}
              floor={floors.india_floor ?? "0.50"}
              pass={indiaPass}
              applicable={indiaApplicable}
            />
            <ComponentBar
              label="Blended"
              value={floors.gm_blended ?? null}
              floor={"0"}
              pass={allPass}
              hideBar
            />
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-divider pt-3">
            <span className="text-secondary text-text-secondary">Revenue</span>
            <MoneyCell value={formatUsd(floors.revenue_total ?? (!indiaApplicable ? gm?.revenue_us : !usApplicable ? gm?.revenue_india : null))} />
          </div>
          <div className="mt-3">
            <StatusBadge
              tone={!computed ? "warning" : allPass ? "success" : "danger"}
              label={
                !computed ? "GM incomplete" : allPass
                  ? usApplicable && indiaApplicable ? "Passes both floors" : `Passes ${usApplicable ? "US" : "India"} floor`
                  : `Fails · ${floors.failing?.join(", ") || "check policy"}`
              }
              data-testid="staffing-floor-summary"
            />
          </div>
        </aside>
      </div>
    </Section>
  );
}

function StaffingRow({ line, fixedPrice }: { line: SowConfirmationStaffingLine; fixedPrice: boolean }) {
  const provEntry = {
    value: line.role,
    provenance: line.provenance as SowProvenance,
    source_id: line.source_id ?? undefined,
    warning: line.warning ?? undefined,
  };
  return (
    <li
      role="row"
      className="grid min-w-[800px] grid-cols-[minmax(120px,2fr)_70px_120px_100px_70px_90px_100px] items-center gap-2 px-3 py-2"
    >
      <div role="cell" className="min-w-0 truncate">
        <span className="text-body text-text font-medium">{line.role}</span>
        <span className="ml-2 text-secondary text-text-secondary">
          {line.seniority}
        </span>
      </div>
      <div role="cell" className="text-body text-text">
        {line.location}
      </div>
      <div role="cell" className="text-right tnum text-body text-text">
        {fixedPrice ? "— fixed price" : formatUsd(line.hourly_bill_rate, 2) ?? "Unavailable"}
      </div>
      <div role="cell" className="text-right tnum text-body text-text">
        {formatUsd(line.hourly_cost, 2) ?? "Unavailable"}
      </div>
      <div role="cell" className="text-right tnum text-body text-text">
        {Number(line.hours_billable).toLocaleString("en-US", { maximumFractionDigits: 2 })}
      </div>
      <div role="cell" className="text-right tnum text-body text-text">
        {formatAllocationPct(line.allocation_pct)}%
      </div>
      <div role="cell">
        <ProvenanceChip entry={provEntry} />
      </div>
    </li>
  );
}

function ComponentBar({
  label,
  value,
  floor,
  pass,
  hideBar,
  applicable = true,
}: {
  label: string;
  value: string | null;
  floor: string;
  pass: boolean;
  hideBar?: boolean;
  applicable?: boolean;
}) {
  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <span className="text-secondary text-text-secondary">{label}</span>
        <span
          className={`text-right tnum ${!applicable || value == null ? "text-secondary text-text-secondary" : pass ? "text-body text-success" : "text-body text-danger"}`}
        >
          {!applicable ? `Not applicable — no ${label} resources` : formatPercent(value) ?? "Unavailable"}
        </span>
      </div>
      {!hideBar && applicable && value != null && value !== "" ? (
        <div className="mt-2">
          <FloorBar value={value} floor={floor} label={label} showChip />
        </div>
      ) : null}
    </div>
  );
}
