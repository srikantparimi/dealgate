import { useMemo, useState } from "react";
import type { PublishRateCardBody, RateCardLocation } from "../api/client";
import { ApiError, publishRateCard } from "../api/client";
import { Modal } from "../ui/Modal";

/**
 * "Publish new version" modal for rate cards. Renders an editable grid the
 * Finance user can add/remove rows in. Money strings are validated before
 * submit and any cost band < $5/hr surfaces a warning + `Confirm anyway`
 * toggle so an obvious keystroke slip cannot land in a published version.
 */

const LOCATIONS: readonly RateCardLocation[] = ["US", "India"] as const;
const SANITY_FLOOR = 5;

interface DraftRow {
  role: string;
  seniority: string;
  location: RateCardLocation;
  cost_low: string;
  cost_base: string;
  cost_high: string;
}

function emptyRow(): DraftRow {
  return {
    role: "",
    seniority: "",
    location: "US",
    cost_low: "",
    cost_base: "",
    cost_high: "",
  };
}

function moneyBelowFloor(value: string): boolean {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 && n < SANITY_FLOOR;
}

export function PublishRateCardModal({
  open,
  onClose,
  onPublished,
}: {
  open: boolean;
  onClose: () => void;
  onPublished: () => void;
}) {
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [notes, setNotes] = useState("");
  const [rows, setRows] = useState<DraftRow[]>([emptyRow()]);
  const [confirmLow, setConfirmLow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const hasSanityIssue = useMemo(
    () =>
      rows.some(
        (r) =>
          moneyBelowFloor(r.cost_low) ||
          moneyBelowFloor(r.cost_base) ||
          moneyBelowFloor(r.cost_high),
      ),
    [rows],
  );

  const canSubmit = useMemo(
    () =>
      effectiveFrom.trim() !== "" &&
      rows.length > 0 &&
      rows.every(
        (r) =>
          r.role.trim() !== "" &&
          r.seniority.trim() !== "" &&
          r.cost_low.trim() !== "" &&
          r.cost_base.trim() !== "" &&
          r.cost_high.trim() !== "",
      ) &&
      (!hasSanityIssue || confirmLow),
    [effectiveFrom, rows, hasSanityIssue, confirmLow],
  );

  function reset() {
    setEffectiveFrom("");
    setNotes("");
    setRows([emptyRow()]);
    setConfirmLow(false);
    setError(null);
    setWarnings([]);
    setSubmitting(false);
  }

  function handleClose() {
    reset();
    onClose();
  }

  function updateRow(idx: number, patch: Partial<DraftRow>) {
    setRows((current) =>
      current.map((r, i) => (i === idx ? { ...r, ...patch } : r)),
    );
  }

  function addRow() {
    setRows((current) => [...current, emptyRow()]);
  }

  function removeRow(idx: number) {
    setRows((current) =>
      current.length === 1 ? current : current.filter((_, i) => i !== idx),
    );
  }

  async function submit() {
    setError(null);
    setWarnings([]);
    setSubmitting(true);
    try {
      const body: PublishRateCardBody = {
        effective_from: effectiveFrom,
        notes: notes.trim() || null,
        rows: rows.map((r) => ({
          role: r.role.trim(),
          seniority: r.seniority.trim(),
          location: r.location,
          cost_low: r.cost_low,
          cost_base: r.cost_base,
          cost_high: r.cost_high,
        })),
        confirm: confirmLow,
      };
      const res = await publishRateCard(body);
      if (res.warnings.length > 0) {
        setWarnings(res.warnings);
      }
      onPublished();
      reset();
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        if (
          err.status === 400 &&
          err.detail &&
          typeof err.detail === "object" &&
          "warnings" in err.detail
        ) {
          const w = (err.detail as { warnings?: unknown }).warnings;
          if (Array.isArray(w)) setWarnings(w.map(String));
        }
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to publish rate card");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title="Publish new rate card"
      onClose={handleClose}
      footer={
        <>
          <button
            type="button"
            onClick={handleClose}
            disabled={submitting}
            style={{
              background: "white",
              color: "#374151",
              border: "1px solid #e5e7eb",
              padding: "8px 16px",
              borderRadius: 6,
              cursor: submitting ? "wait" : "pointer",
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!canSubmit || submitting}
            style={{
              background: "#111827",
              color: "white",
              border: "none",
              padding: "8px 16px",
              borderRadius: 6,
              cursor: submitting ? "wait" : "pointer",
              opacity: !canSubmit || submitting ? 0.6 : 1,
            }}
          >
            {submitting ? "Publishing…" : "Publish"}
          </button>
        </>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>Effective from</span>
          <input
            aria-label="Effective from"
            type="date"
            value={effectiveFrom}
            onChange={(e) => setEffectiveFrom(e.target.value)}
            style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>Notes</span>
          <input
            aria-label="Notes"
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
          />
        </label>

        <table
          aria-label="Rate card rows"
          style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}
        >
          <thead>
            <tr style={{ background: "#f9fafb" }}>
              <th style={cellHeader}>Role</th>
              <th style={cellHeader}>Seniority</th>
              <th style={cellHeader}>Location</th>
              <th style={cellHeader}>Low</th>
              <th style={cellHeader}>Base</th>
              <th style={cellHeader}>High</th>
              <th style={cellHeader} />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr key={idx}>
                <td style={cell}>
                  <input
                    aria-label={`Row ${idx + 1} role`}
                    value={row.role}
                    onChange={(e) => updateRow(idx, { role: e.target.value })}
                    style={inputStyle}
                  />
                </td>
                <td style={cell}>
                  <input
                    aria-label={`Row ${idx + 1} seniority`}
                    value={row.seniority}
                    onChange={(e) => updateRow(idx, { seniority: e.target.value })}
                    style={inputStyle}
                  />
                </td>
                <td style={cell}>
                  <select
                    aria-label={`Row ${idx + 1} location`}
                    value={row.location}
                    onChange={(e) =>
                      updateRow(idx, { location: e.target.value as RateCardLocation })
                    }
                    style={inputStyle}
                  >
                    {LOCATIONS.map((loc) => (
                      <option key={loc} value={loc}>
                        {loc}
                      </option>
                    ))}
                  </select>
                </td>
                <td style={cell}>
                  <input
                    aria-label={`Row ${idx + 1} cost_low`}
                    type="number"
                    step="0.01"
                    min="0"
                    value={row.cost_low}
                    onChange={(e) => updateRow(idx, { cost_low: e.target.value })}
                    style={{
                      ...inputStyle,
                      borderColor: moneyBelowFloor(row.cost_low) ? "#f59e0b" : "#e5e7eb",
                    }}
                  />
                </td>
                <td style={cell}>
                  <input
                    aria-label={`Row ${idx + 1} cost_base`}
                    type="number"
                    step="0.01"
                    min="0"
                    value={row.cost_base}
                    onChange={(e) => updateRow(idx, { cost_base: e.target.value })}
                    style={{
                      ...inputStyle,
                      borderColor: moneyBelowFloor(row.cost_base) ? "#f59e0b" : "#e5e7eb",
                    }}
                  />
                </td>
                <td style={cell}>
                  <input
                    aria-label={`Row ${idx + 1} cost_high`}
                    type="number"
                    step="0.01"
                    min="0"
                    value={row.cost_high}
                    onChange={(e) => updateRow(idx, { cost_high: e.target.value })}
                    style={{
                      ...inputStyle,
                      borderColor: moneyBelowFloor(row.cost_high) ? "#f59e0b" : "#e5e7eb",
                    }}
                  />
                </td>
                <td style={cell}>
                  <button
                    type="button"
                    aria-label={`Remove row ${idx + 1}`}
                    disabled={rows.length === 1}
                    onClick={() => removeRow(idx)}
                    style={{
                      background: "none",
                      border: "none",
                      color: rows.length === 1 ? "#9ca3af" : "#991b1b",
                      cursor: rows.length === 1 ? "not-allowed" : "pointer",
                    }}
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <button
          type="button"
          onClick={addRow}
          style={{
            alignSelf: "flex-start",
            background: "white",
            color: "#374151",
            border: "1px dashed #d1d5db",
            padding: "6px 12px",
            borderRadius: 6,
            cursor: "pointer",
            fontSize: 13,
          }}
        >
          + Add row
        </button>

        {hasSanityIssue ? (
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              background: "#fffbeb",
              border: "1px solid #fde68a",
              padding: 8,
              borderRadius: 4,
              fontSize: 13,
              color: "#92400e",
            }}
          >
            <input
              type="checkbox"
              aria-label="Confirm anyway"
              checked={confirmLow}
              onChange={(e) => setConfirmLow(e.target.checked)}
            />
            One or more bands are under ${SANITY_FLOOR}/hr — confirm anyway
          </label>
        ) : null}

        {warnings.length > 0 ? (
          <div
            role="status"
            style={{
              background: "#fffbeb",
              color: "#92400e",
              border: "1px solid #fde68a",
              padding: 8,
              borderRadius: 4,
              fontSize: 13,
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Warnings</div>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {error ? (
          <div
            role="alert"
            style={{
              background: "#fef2f2",
              color: "#991b1b",
              border: "1px solid #fecaca",
              padding: 8,
              borderRadius: 4,
              fontSize: 14,
            }}
          >
            {error}
          </div>
        ) : null}
      </div>
    </Modal>
  );
}

const cellHeader: React.CSSProperties = {
  padding: "6px 8px",
  textAlign: "left",
  borderBottom: "1px solid #e5e7eb",
  fontWeight: 600,
  color: "#374151",
};

const cell: React.CSSProperties = { padding: "4px 4px", verticalAlign: "middle" };

const inputStyle: React.CSSProperties = {
  padding: 4,
  border: "1px solid #e5e7eb",
  borderRadius: 4,
  width: "100%",
  boxSizing: "border-box",
};
