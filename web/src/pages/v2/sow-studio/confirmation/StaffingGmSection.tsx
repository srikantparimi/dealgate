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

  return (
    <Section
      id="section-staffing"
      title="Staffing & GM"
      description='Editing this grid is the review — the auto-plan opens pre-populated.'
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div>
          {lines.length ? (
            <div
              role="table"
              aria-label="Staffing grid"
              className="overflow-hidden rounded-panel border border-divider bg-surface"
            >
              <div
                role="row"
                className="grid grid-cols-[minmax(0,2fr)_100px_120px_100px_140px_auto] gap-2 border-b border-divider bg-surface-sunken px-3 py-2 text-[11px] uppercase tracking-wide text-text-secondary"
              >
                <div role="columnheader">Role · seniority</div>
                <div role="columnheader">Location</div>
                <div role="columnheader" className="text-right">
                  Rate
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
                  <StaffingRow key={i} line={line} />
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
          className="rounded-panel border border-divider bg-surface p-3"
          aria-label="GM by component"
        >
          <h3 className="text-secondary font-medium text-text-secondary">
            Component GM
          </h3>
          <div className="mt-3 flex flex-col gap-4">
            <ComponentBar
              label="US"
              value={floors.gm_us ?? null}
              floor={"0.35"}
              pass={usPass}
            />
            <ComponentBar
              label="India"
              value={floors.gm_india ?? null}
              floor={"0.55"}
              pass={indiaPass}
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
            <MoneyCell value={gm?.revenue_us ?? gm?.revenue_india ?? null} />
          </div>
          <div className="mt-3">
            <StatusBadge
              tone={allPass ? "success" : "danger"}
              label={
                allPass
                  ? "Passes both floors"
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

function StaffingRow({ line }: { line: SowConfirmationStaffingLine }) {
  const provEntry = {
    value: line.role,
    provenance: line.provenance as SowProvenance,
    source_id: line.source_id ?? undefined,
    warning: line.warning ?? undefined,
  };
  return (
    <li
      role="row"
      className="grid grid-cols-[minmax(0,2fr)_100px_120px_100px_140px_auto] items-center gap-2 px-3 py-2"
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
        {line.hourly_bill_rate}
      </div>
      <div role="cell" className="text-right tnum text-body text-text">
        {line.hours_billable}
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
}: {
  label: string;
  value: string | null;
  floor: string;
  pass: boolean;
  hideBar?: boolean;
}) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <span className="text-secondary text-text-secondary">{label}</span>
        <span
          className={pass ? "text-body text-success" : "text-body text-danger"}
        >
          {value == null || value === "" ? "Unavailable" : `${value}`}
        </span>
      </div>
      {!hideBar && value != null && value !== "" ? (
        <div className="mt-2">
          <FloorBar value={value} floor={floor} label={label} showChip />
        </div>
      ) : null}
    </div>
  );
}
