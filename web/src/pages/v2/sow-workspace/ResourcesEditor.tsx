/**
 * Resources on a SOW — editable at any point in its life (S10-08).
 *
 * Staffing used to be editable only at the gate, on the way to the
 * confirmation screen. That is the moment it is least likely to be final:
 * the plan firms up during negotiation and changes again once delivery
 * starts. So it lives here too, on the record, for as long as the SOW does.
 *
 * The signature decides what an edit costs, not the screen:
 *
 *   - Unsigned: a plan is a proposal. Edit as often as you like; nobody is
 *     notified because nobody has committed to anything.
 *   - Signed: the margin was part of a decision. The edit is still allowed —
 *     people roll off, scope moves, and refusing would just push the change
 *     off-system — but it carries an effective date and a reason, and every
 *     approver is told with the old and new margin.
 *
 * Utilization is a percentage here and a 0..1 fraction in the GM library,
 * where it scales revenue *and* cost. A consultant at 50% bills half and
 * costs half for the same calendar hours.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getSowResources,
  putSowResources,
  type SowResourcesState,
  type UUID,
} from "../../../api/client";
import {
  emptyRow,
  isFixedFee,
  rowIsComplete,
  toResourceLines,
  formatPct,
  type GridRow,
} from "../sow-staffing/StaffingGate";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";
import { StatusBadge } from "../../../ui-v2/StatusBadge";

export function stateToRows(state: SowResourcesState): GridRow[] {
  if (!state.resources.length) return [emptyRow()];
  return state.resources.map((r) => ({
    role: r.role,
    seniority: r.seniority,
    location: r.location,
    allocation_pct: r.utilization_pct,
    hours_billable: r.hours_billable,
    hourly_bill_rate: r.hourly_bill_rate,
    hourly_cost: r.hourly_cost ?? "",
    start_date: r.start_date ?? "",
    end_date: r.end_date ?? "",
    origin: "manual" as const,
  }));
}

export interface ResourcesEditorProps {
  opportunityId: UUID;
  load?: typeof getSowResources;
}

export function ResourcesEditor({
  opportunityId,
  load = getSowResources,
}: ResourcesEditorProps) {
  const [state, setState] = useState<SowResourcesState | null>(null);
  const [rows, setRows] = useState<GridRow[]>([emptyRow()]);
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await load(opportunityId);
      setState(res);
      setRows(stateToRows(res));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not load resources");
    }
  }, [opportunityId, load]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const engagementType = state?.engagement_type ?? undefined;
  const fixedFee = isFixedFee(engagementType);
  const signed = state?.requires_notice_on_change ?? false;

  const complete = useMemo(
    () => rows.filter((r) => rowIsComplete(r, engagementType)),
    [rows, engagementType],
  );

  // After signature the extra fields are not optional — the approvers are
  // about to be told, and "the staffing changed" with no date or reason is
  // not a notice anyone can act on.
  const canSave =
    complete.length > 0 &&
    !busy &&
    (!signed || (effectiveFrom !== "" && reason.trim() !== ""));

  function update(idx: number, patch: Partial<GridRow>) {
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  }

  async function save() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await putSowResources(opportunityId, {
        engagement_type: engagementType ?? "fixed_price",
        resource_lines: toResourceLines(rows, engagementType),
        cost_lines: [],
        ...(signed ? { effective_from: effectiveFrom, reason: reason.trim() } : {}),
      });
      setNotice(
        res.requires_notice
          ? `Saved. ${res.notified.length} approver function(s) notified — margin ${formatPct(
              res.margin_before.gm_blended,
            )} → ${formatPct(res.margin_after.gm_blended)}.`
          : `Saved. Margin is now ${formatPct(res.margin_after.gm_blended)}.`,
      );
      setEffectiveFrom("");
      setReason("");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not save the plan");
    } finally {
      setBusy(false);
    }
  }

  const columns = [
    { label: "Role", required: true },
    { label: "Seniority", required: true },
    { label: "Location", required: true },
    { label: "Utilization %", required: false },
    { label: "Hours", required: true },
    { label: "Bill rate", required: !fixedFee },
    { label: "Cost / hour", required: fixedFee },
    { label: "Start", required: true },
    { label: "End", required: true },
    { label: "", required: false },
  ];

  return (
    <section data-testid="resources-editor">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-heading-4">Resources</h3>
          <p className="text-secondary text-text-secondary">
            {signed
              ? "This SOW is signed. A change here is dated and every approver is told, with the old and new margin."
              : "Not signed yet — edit as often as you need. Nobody is notified."}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {state?.margin?.gm_blended != null ? (
            <StatusBadge
              tone={state.margin.us_pass && state.margin.india_pass ? "ok" : "warn"}
              label={`Blended ${formatPct(state.margin.gm_blended)}`}
            />
          ) : null}
          {signed ? <StatusBadge tone="warn" label="signed" /> : null}
          <Button onClick={() => void save()} disabled={!canSave} data-testid="save-resources">
            {busy ? "Saving…" : signed ? "Save & notify" : "Save"}
          </Button>
        </div>
      </div>

      {signed ? (
        <div className="mb-4 flex flex-wrap gap-4 rounded-lg border border-warning/40 bg-warning/5 p-3">
          <label className="text-secondary">
            Effective from
            <span className="text-danger" aria-hidden="true">
              {" *"}
            </span>
            <Input
              type="date"
              value={effectiveFrom}
              aria-label="effective-from"
              onChange={(e) => setEffectiveFrom(e.target.value)}
            />
          </label>
          <label className="flex-1 text-secondary">
            Reason
            <span className="text-danger" aria-hidden="true">
              {" *"}
            </span>
            <Input
              value={reason}
              placeholder="Why the staffing changed — the approvers will read this"
              aria-label="change-reason"
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
        </div>
      ) : null}

      {error ? (
        <p className="mb-3 text-secondary text-danger" data-testid="resources-error">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="mb-3 text-secondary text-text-secondary" data-testid="resources-notice">
          {notice}
        </p>
      ) : null}

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[60rem] text-secondary">
          <thead className="bg-surface-2 text-text-secondary">
            <tr>
              {columns.map((c) => (
                <th key={c.label} className="px-3 py-2 text-left font-medium">
                  {c.label}
                  {c.required ? (
                    <span className="text-danger" aria-hidden="true">
                      {" *"}
                    </span>
                  ) : null}
                </th>
              ))}
            </tr>
          </thead>
          <tbody data-testid="resource-rows">
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-border">
                <td className="px-2 py-1">
                  <Input value={r.role} aria-label={`res-role-${i}`} onChange={(e) => update(i, { role: e.target.value })} />
                </td>
                <td className="px-2 py-1">
                  <Input value={r.seniority} aria-label={`res-seniority-${i}`} onChange={(e) => update(i, { seniority: e.target.value })} />
                </td>
                <td className="px-2 py-1">
                  <select
                    value={r.location}
                    aria-label={`res-location-${i}`}
                    className="h-9 rounded-md border border-border bg-surface px-2"
                    onChange={(e) => update(i, { location: e.target.value })}
                  >
                    {["US", "India"].map((l) => (
                      <option key={l} value={l}>{l}</option>
                    ))}
                  </select>
                </td>
                <td className="px-2 py-1">
                  <Input
                    value={r.allocation_pct}
                    placeholder="100"
                    title="Percent of this person's time. 50 = half time, billed and costed at half."
                    aria-label={`res-utilization-${i}`}
                    onChange={(e) => update(i, { allocation_pct: e.target.value })}
                  />
                </td>
                <td className="px-2 py-1">
                  <Input value={r.hours_billable} aria-label={`res-hours-${i}`} onChange={(e) => update(i, { hours_billable: e.target.value })} />
                </td>
                <td className="px-2 py-1">
                  <Input value={r.hourly_bill_rate} aria-label={`res-rate-${i}`} onChange={(e) => update(i, { hourly_bill_rate: e.target.value })} />
                </td>
                <td className="px-2 py-1">
                  <Input value={r.hourly_cost} aria-label={`res-cost-${i}`} onChange={(e) => update(i, { hourly_cost: e.target.value })} />
                </td>
                <td className="px-2 py-1">
                  <Input type="date" value={r.start_date} aria-label={`res-start-${i}`} onChange={(e) => update(i, { start_date: e.target.value })} />
                </td>
                <td className="px-2 py-1">
                  <Input type="date" value={r.end_date} aria-label={`res-end-${i}`} onChange={(e) => update(i, { end_date: e.target.value })} />
                </td>
                <td className="px-2 py-1 text-right">
                  <button
                    type="button"
                    aria-label={`res-remove-${i}`}
                    className="text-text-secondary hover:text-danger"
                    onClick={() =>
                      setRows((prev) => (prev.length === 1 ? [emptyRow()] : prev.filter((_, j) => j !== i)))
                    }
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex items-center justify-between">
        <Button variant="secondary" data-testid="res-add-row" onClick={() => setRows((p) => [...p, emptyRow()])}>
          Add role
        </Button>
        <p className="text-secondary text-text-secondary">
          {complete.length === 0
            ? fixedFee
              ? "No complete rows — on a fixed fee a row needs hours, a cost rate and dates."
              : "No complete rows — a row needs hours, a bill rate and dates."
            : `${complete.length} role(s) costed.`}
        </p>
      </div>
    </section>
  );
}
