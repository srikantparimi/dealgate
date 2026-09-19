/**
 * S9 — one staffing row.
 *
 * Rendered pre-populated from the auto-staffing output. Clicking Edit
 * opens the same row inline as a mini form; on Save the row's
 * provenance flips to `manual` (bill_rate_source preserved) — never a
 * silent overwrite (CLAUDE.md rule 10, sow-first-principles §5).
 *
 * Every money / percent is a Decimal string coming from the server. The
 * row never computes revenue or GM itself — display arithmetic only.
 */
import { Pencil, X, Check } from "lucide-react";
import { useState } from "react";
import type {
  DeliveryLineProvenance,
  DeliveryResourceLineRow,
} from "../../../../api/client";
import { MarginCell } from "../../../../ui-v2/MarginCell";
import { MoneyCell } from "../../../../ui-v2/MoneyCell";
import { Button } from "../../../../ui-v2/primitives/button";
import { Input } from "../../../../ui-v2/primitives/input";
import { formatUsd } from "../format";
import { ProvenanceChip, ProvenanceWarning } from "./ProvenanceChip";

type ViewerRole = "restricted" | "full";

export interface ResourceLineRowProps {
  row: DeliveryResourceLineRow;
  viewer: ViewerRole;
  onSave?: (
    id: string,
    patch: Partial<DeliveryResourceLineRow>,
  ) => void | Promise<void>;
}

export function ResourceLineRow({ row, viewer, onSave }: ResourceLineRowProps) {
  const [editing, setEditing] = useState(false);
  const [role, setRole] = useState(row.role);
  const [seniority, setSeniority] = useState(row.seniority);
  const [hours, setHours] = useState(row.hours_billable);
  const [bill, setBill] = useState(row.hourly_bill_rate);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const meta = row.provenance_meta ?? null;
  const hoursNum = Number(row.hours_billable);
  const billNum = Number(row.hourly_bill_rate);
  const costNum = row.hourly_cost != null ? Number(row.hourly_cost) : null;
  const alloc = Number(row.allocation_pct);
  const revenue = Number.isFinite(hoursNum * billNum) ? hoursNum * billNum : null;
  const costTotal =
    costNum != null && Number.isFinite(hoursNum * costNum)
      ? hoursNum * costNum
      : null;
  const gmValue =
    revenue != null && costTotal != null && revenue > 0
      ? (revenue - costTotal) / revenue
      : null;
  const belowFloor = gmValue != null && gmValue < 0.35;

  async function submit() {
    if (!onSave) return;
    setSaving(true);
    setSaveError(null);
    try {
      // Provenance flips to "manual"; bill_rate_source preserved so
      // Finance can still see which card the rate originated from.
      const nextMeta: DeliveryLineProvenance = {
        provenance: "manual",
        bill_rate_source: meta?.bill_rate_source ?? null,
        source_label: null,
        page_ref: null,
        confidence: null,
        warning: meta?.warning ?? null,
        source_id: null,
      };
      await onSave(row.id, {
        role,
        seniority,
        hours_billable: hours,
        hourly_bill_rate: bill,
        provenance_meta: nextMeta,
      });
      setEditing(false);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  function cancel() {
    setRole(row.role);
    setSeniority(row.seniority);
    setHours(row.hours_billable);
    setBill(row.hourly_bill_rate);
    setEditing(false);
    setSaveError(null);
  }

  return (
    <tr
      data-testid={`staffing-row-${row.id}`}
      data-below-floor={belowFloor ? "true" : "false"}
      className="border-t border-divider align-top"
    >
      <td className="py-2 pr-3 text-text">
        {editing ? (
          <Input
            aria-label={`Role for row ${row.id}`}
            value={role}
            onChange={(e) => setRole(e.target.value)}
          />
        ) : (
          row.role
        )}
      </td>
      <td className="py-2 pr-3 text-text">
        {editing ? (
          <Input
            aria-label={`Seniority for row ${row.id}`}
            value={seniority}
            onChange={(e) => setSeniority(e.target.value)}
          />
        ) : (
          row.seniority
        )}
      </td>
      <td className="py-2 pr-3 text-text">{row.location}</td>
      <td className="py-2 pr-3">
        {editing ? (
          <Input
            aria-label={`Bill rate for row ${row.id}`}
            value={bill}
            onChange={(e) => setBill(e.target.value)}
          />
        ) : (
          <MoneyCell value={formatUsd(String(billNum)) ?? undefined} />
        )}
      </td>
      <td className="py-2 pr-3">
        {editing ? (
          <Input
            aria-label={`Hours for row ${row.id}`}
            value={hours}
            onChange={(e) => setHours(e.target.value)}
          />
        ) : (
          <MoneyCell value={String(hoursNum.toFixed(1))} />
        )}
      </td>
      <td className="py-2 pr-3">
        <MoneyCell
          value={
            costTotal != null
              ? (formatUsd(String(costTotal)) ?? undefined)
              : undefined
          }
          unavailableLabel={viewer === "restricted" ? "Restricted" : "Unavailable"}
        />
      </td>
      <td className="py-2 pr-3">
        <MoneyCell
          value={revenue != null ? (formatUsd(String(revenue)) ?? undefined) : undefined}
        />
      </td>
      <td className="py-2 pr-3">
        <MarginCell
          value={gmValue != null ? `${(gmValue * 100).toFixed(1)}%` : undefined}
          outcome={
            gmValue == null ? "unavailable" : belowFloor ? "fail" : "pass"
          }
        />
      </td>
      <td className="py-2 pr-3">
        <div className="flex flex-col gap-1 items-start">
          <ProvenanceChip meta={meta} />
          <ProvenanceWarning message={meta?.warning ?? null} />
          {!Number.isFinite(alloc) ? null : (
            <span className="text-secondary text-text-secondary tnum">
              alloc {(alloc * 100).toFixed(0)}%
            </span>
          )}
        </div>
      </td>
      <td className="py-2 pr-3 text-right">
        {onSave ? (
          editing ? (
            <div className="flex gap-1 items-center justify-end">
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={cancel}
                aria-label="Cancel edit"
                disabled={saving}
              >
                <X className="h-3 w-3" aria-hidden /> Cancel
              </Button>
              <Button
                type="button"
                size="sm"
                onClick={submit}
                aria-label="Save row"
                disabled={saving}
                data-testid={`staffing-row-save-${row.id}`}
              >
                <Check className="h-3 w-3" aria-hidden /> Save
              </Button>
              {saveError ? (
                <span className="text-danger text-secondary">{saveError}</span>
              ) : null}
            </div>
          ) : (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => setEditing(true)}
              aria-label={`Edit row ${row.id}`}
              data-testid={`staffing-row-edit-${row.id}`}
            >
              <Pencil className="h-3 w-3" aria-hidden /> Edit
            </Button>
          )
        ) : null}
      </td>
    </tr>
  );
}
