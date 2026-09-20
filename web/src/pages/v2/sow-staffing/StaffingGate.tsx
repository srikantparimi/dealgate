/**
 * Staffing & rates — the gate between upload and confirmation (S10-05).
 *
 * Why this screen exists
 * ----------------------
 * A gross margin is only as good as the staffing plan under it. Most SOWs do
 * not carry one: a fixed-fee assessment states a price and a scope and leaves
 * the staffing to Delivery. The system used to fill that gap by inventing a
 * roster — three default roles, a default hours figure, a zero bill rate,
 * today+90d dates — and computing a GM from it with no warning. Finance would
 * have been approving a margin derived entirely from guesses.
 *
 * That is refused now, which means a person has to supply the plan. Two ways
 * in, because both are how this work really gets done:
 *
 *   - type it into the grid, or
 *   - upload the staffing sheet (the same columns, for people who already
 *     size engagements in Excel).
 *
 * The gross margin recomputes as you edit, so the number is never a surprise
 * at the end. Saving writes an immutable GM version through the existing
 * delivery-model endpoint, then hands off to the confirmation screen.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ApiError,
  getSowConfirmation,
  importStaffingSheet,
  previewDeliveryModel,
  saveDeliveryModelVersion,
  staffingTemplateUrl,
  type DeliveryLocation,
  type DeliveryPreviewRequestInputs,
  type DeliveryPreviewResponse,
  type DeliveryResourceLineInput,
  type EngagementType,
  type StaffingSheetRowError,
  type UUID,
} from "../../../api/client";
import { PageHeader } from "../../../ui-v2/PageHeader";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { cn } from "../../../lib/cn";

const LOCATIONS = ["US", "India"] as const;

export interface GridRow {
  role: string;
  seniority: string;
  location: string;
  allocation_pct: string;
  hours_billable: string;
  hourly_bill_rate: string;
  start_date: string;
  end_date: string;
  /** Where this row came from, so a proposal is never mistaken for a decision. */
  origin: "manual" | "sheet" | "proposed";
  source_id?: string | null;
}

export function emptyRow(): GridRow {
  return {
    role: "",
    seniority: "",
    location: "US",
    allocation_pct: "1",
    hours_billable: "",
    hourly_bill_rate: "",
    start_date: "",
    end_date: "",
    origin: "manual",
  };
}

/**
 * A row only counts toward the GM once it is actually costable.
 *
 * Dates are required, not optional. A line with no dates cannot be checked
 * against anyone's capacity or against HR lead times, and for this SOW the
 * term dates are exactly what the document does not say — so someone has to
 * decide them. Better to ask here than to let the margin be computed over an
 * invented window, which is what the old auto-staffing did.
 */
export function rowIsComplete(r: GridRow): boolean {
  return (
    r.role.trim() !== "" &&
    r.seniority.trim() !== "" &&
    Number(r.hours_billable) > 0 &&
    Number(r.hourly_bill_rate) > 0 &&
    r.start_date !== "" &&
    r.end_date !== ""
  );
}

export function toResourceLines(rows: GridRow[]): DeliveryResourceLineInput[] {
  return rows.filter(rowIsComplete).map((r) => ({
    role: r.role.trim(),
    seniority: r.seniority.trim(),
    location: r.location as DeliveryLocation,
    person_name: null,
    allocation_pct: r.allocation_pct || "1",
    start_date: r.start_date,
    end_date: r.end_date,
    hours_billable: r.hours_billable,
    hourly_bill_rate: r.hourly_bill_rate,
    // Left null on purpose: loaded cost comes from the HR cost bands
    // server-side. Client rate cards set what we bill; cost bands set what it
    // costs us. CLAUDE.md keeps those three tables separate for a reason.
    hourly_cost: null,
    validated_by: null,
  }));
}

export interface StaffingGateProps {
  opportunityId?: UUID;
  engagementType?: EngagementType;
}

export function StaffingGatePage(props: StaffingGateProps) {
  const params = useParams();
  const navigate = useNavigate();
  const opportunityId = (props.opportunityId ?? params.id ?? "") as UUID;

  // Engagement type and price come from the SOW, not from this screen. A
  // fixed-fee margin is (fee - cost) / fee, so the fee has to travel with the
  // preview or the number means nothing.
  const [engagementType, setEngagementType] = useState<EngagementType>(
    props.engagementType ?? "fixed_price",
  );
  const [totalPrice, setTotalPrice] = useState<string | null>(null);

  useEffect(() => {
    if (!opportunityId) return;
    let cancelled = false;
    getSowConfirmation(opportunityId)
      .then((payload) => {
        if (cancelled) return;
        setEngagementType(payload.engagement.primary.type);
        const fields = payload.sow_version.extracted_fields as
          | Record<string, { value?: unknown }>
          | null;
        const raw = fields?.price?.value;
        if (typeof raw === "string" || typeof raw === "number") {
          const cleaned = String(raw).replace(/[^0-9.]/g, "");
          if (cleaned) setTotalPrice(cleaned);
        }
      })
      .catch(() => {
        /* the grid still works; the preview will say what is missing */
      });
    return () => {
      cancelled = true;
    };
  }, [opportunityId]);

  const [rows, setRows] = useState<GridRow[]>([emptyRow()]);
  const [preview, setPreview] = useState<DeliveryPreviewResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [sheetErrors, setSheetErrors] = useState<StaffingSheetRowError[]>([]);
  const [banner, setBanner] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const completeRows = useMemo(() => rows.filter(rowIsComplete), [rows]);
  const canSave = completeRows.length > 0 && !saving;

  const update = useCallback(
    (idx: number, patch: Partial<GridRow>) => {
      setRows((prev) =>
        prev.map((r, i) => (i === idx ? { ...r, ...patch, origin: "manual" } : r)),
      );
    },
    [],
  );

  // Live gross margin. Debounced so typing a rate does not fire a request per
  // keystroke, and stale responses are dropped so the number on screen always
  // belongs to the rows on screen.
  useEffect(() => {
    if (completeRows.length === 0) {
      setPreview(null);
      setPreviewError(null);
      return;
    }
    let cancelled = false;
    const t = setTimeout(() => {
      const inputs: DeliveryPreviewRequestInputs = {
        resource_lines: toResourceLines(rows),
        cost_lines: [],
        ...(totalPrice ? { total_price: totalPrice } : {}),
      };
      previewDeliveryModel({ engagement_type: engagementType, inputs })
        .then((res) => {
          if (!cancelled) {
            setPreview(res);
            setPreviewError(null);
          }
        })
        .catch((e: unknown) => {
          if (!cancelled) {
            setPreview(null);
            setPreviewError(e instanceof Error ? e.message : "preview failed");
          }
        });
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [rows, completeRows.length, engagementType, totalPrice]);

  async function handleUpload(file: File) {
    setSheetErrors([]);
    setBanner(null);
    try {
      const res = await importStaffingSheet(opportunityId, file);
      setRows(
        res.resource_lines.map((l) => ({
          role: l.role,
          seniority: l.seniority,
          location: l.location,
          allocation_pct: l.allocation_pct,
          hours_billable: l.hours_billable,
          hourly_bill_rate: l.hourly_bill_rate,
          start_date: l.start_date ?? "",
          end_date: l.end_date ?? "",
          origin: "sheet" as const,
        })),
      );
      setBanner(`${res.row_count} row(s) loaded from the sheet — review, then save.`);
    } catch (e) {
      if (e instanceof ApiError) {
        const detail = e.detail as { errors?: StaffingSheetRowError[] } | null;
        const body = (detail as { detail?: { errors?: StaffingSheetRowError[] } })
          ?.detail;
        setSheetErrors(body?.errors ?? detail?.errors ?? []);
      }
      setBanner(e instanceof Error ? e.message : "could not read the sheet");
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handleSave() {
    setSaving(true);
    setBanner(null);
    try {
      await saveDeliveryModelVersion(opportunityId, {
        engagement_type: engagementType,
        resource_lines: toResourceLines(rows),
        cost_lines: [],
        ...(totalPrice ? { total_price: totalPrice } : {}),
      });
      navigate(`/sows/new?opportunityId=${opportunityId}`);
    } catch (e) {
      setBanner(e instanceof Error ? e.message : "could not save the staffing plan");
    } finally {
      setSaving(false);
    }
  }

  const gm = preview?.computed as Record<string, unknown> | undefined;

  return (
    <div data-testid="staffing-gate">
      <PageHeader
        title="Staffing & rates"
        subtitle="A gross margin is only as good as the plan under it — enter the team or upload the sheet."
        actions={
          <div className="flex items-center gap-2">
            <a href={staffingTemplateUrl()} data-testid="download-template">
              <Button variant="secondary">Download template</Button>
            </a>
            <Button
              variant="secondary"
              onClick={() => fileRef.current?.click()}
              data-testid="upload-sheet"
            >
              Upload sheet
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx"
              className="hidden"
              data-testid="sheet-input"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void handleUpload(f);
              }}
            />
            <Button
              onClick={() => void handleSave()}
              disabled={!canSave}
              data-testid="save-staffing"
            >
              {saving ? "Saving…" : "Save & continue"}
            </Button>
          </div>
        }
      />

      {banner ? (
        <p className="mb-3 text-secondary text-text-secondary" data-testid="staffing-banner">
          {banner}
        </p>
      ) : null}

      {sheetErrors.length > 0 ? (
        <ul
          className="mb-4 rounded-md border border-danger/40 bg-danger/5 p-3 text-secondary"
          data-testid="sheet-errors"
        >
          {sheetErrors.map((err, i) => (
            <li key={i}>
              Row {err.row}
              {err.field ? ` · ${err.field}` : ""}: {err.message}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full min-w-[56rem] text-secondary">
          <thead className="bg-surface-2 text-text-secondary">
            <tr>
              {[
                "Role",
                "Seniority",
                "Location",
                "Allocation",
                "Hours",
                "Bill rate",
                "Start",
                "End",
                "",
              ].map((h) => (
                <th key={h} className="px-3 py-2 text-left font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody data-testid="staffing-rows">
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-border">
                <td className="px-2 py-1">
                  <Input
                    value={r.role}
                    placeholder="Consultant"
                    aria-label={`role-${i}`}
                    onChange={(e) => update(i, { role: e.target.value })}
                  />
                </td>
                <td className="px-2 py-1">
                  <Input
                    value={r.seniority}
                    placeholder="Senior"
                    aria-label={`seniority-${i}`}
                    onChange={(e) => update(i, { seniority: e.target.value })}
                  />
                </td>
                <td className="px-2 py-1">
                  <select
                    value={r.location}
                    aria-label={`location-${i}`}
                    className="h-9 rounded-md border border-border bg-surface px-2"
                    onChange={(e) => update(i, { location: e.target.value })}
                  >
                    {LOCATIONS.map((l) => (
                      <option key={l} value={l}>
                        {l}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-2 py-1">
                  <Input
                    value={r.allocation_pct}
                    aria-label={`allocation-${i}`}
                    onChange={(e) => update(i, { allocation_pct: e.target.value })}
                  />
                </td>
                <td className="px-2 py-1">
                  <Input
                    value={r.hours_billable}
                    placeholder="160"
                    aria-label={`hours-${i}`}
                    onChange={(e) => update(i, { hours_billable: e.target.value })}
                  />
                </td>
                <td className="px-2 py-1">
                  <Input
                    value={r.hourly_bill_rate}
                    placeholder="225"
                    aria-label={`rate-${i}`}
                    onChange={(e) => update(i, { hourly_bill_rate: e.target.value })}
                  />
                </td>
                <td className="px-2 py-1">
                  <Input
                    type="date"
                    value={r.start_date}
                    aria-label={`start-${i}`}
                    onChange={(e) => update(i, { start_date: e.target.value })}
                  />
                </td>
                <td className="px-2 py-1">
                  <Input
                    type="date"
                    value={r.end_date}
                    aria-label={`end-${i}`}
                    onChange={(e) => update(i, { end_date: e.target.value })}
                  />
                </td>
                <td className="px-2 py-1 text-right">
                  <button
                    type="button"
                    aria-label={`remove-${i}`}
                    className="text-text-secondary hover:text-danger"
                    onClick={() =>
                      setRows((prev) =>
                        prev.length === 1
                          ? [emptyRow()]
                          : prev.filter((_, j) => j !== i),
                      )
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
        <Button
          variant="secondary"
          data-testid="add-row"
          onClick={() => setRows((prev) => [...prev, emptyRow()])}
        >
          Add role
        </Button>
        <p className="text-secondary text-text-secondary">
          {completeRows.length === 0
            ? "No complete rows yet — a row needs a role, seniority, hours, a bill rate and dates."
            : `${completeRows.length} role(s) costed.`}
        </p>
      </div>

      {/* Live gross margin. Shown only once there is something real to compute
          from — a margin derived from half a row would mislead. */}
      <div className="mt-6" data-testid="gm-preview">
        {completeRows.length === 0 ? (
          <EmptyState
            title="Gross margin will appear here"
            description="The SOW did not list resources and no approved past SOW matched this scope, so nothing was proposed. Enter the team above or upload the sheet, and the margin calculates as you go."
          />
        ) : previewError ? (
          <p className="text-secondary text-danger" data-testid="gm-error">
            {previewError}
          </p>
        ) : gm ? (
          <div className="flex flex-wrap gap-6 rounded-lg border border-border p-4">
            {(
              [
                ["Blended GM", gm.gm_blended],
                ["US GM", gm.gm_us],
                ["India GM", gm.gm_india],
              ] as const
            ).map(([label, value]) => (
              <div key={label}>
                <p className="text-text-secondary">{label}</p>
                <p className={cn("text-heading-3")}>
                  {value == null ? "—" : formatPct(value)}
                </p>
              </div>
            ))}
            {preview?.warnings?.capacity?.length ? (
              <StatusBadge
                tone="warning"
                label={`${preview.warnings.capacity.length} capacity warning(s)`}
              />
            ) : null}
            {preview?.warnings?.hr?.length ? (
              <StatusBadge
                tone="warning"
                label={`${preview.warnings.hr.length} HR lead-time warning(s)`}
              />
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function formatPct(value: unknown): string {
  // Guard the empty cases explicitly: Number(null) and Number("") are both 0,
  // so without this an absent margin rendered as a confident "0.0%" — a
  // missing number displayed as a real one, which is the whole failure mode
  // this screen exists to stop.
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
}
