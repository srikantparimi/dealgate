import { useMemo, useState } from "react";
import type { FxConvention, PublishPolicyBody } from "../api/client";
import { ApiError, publishPolicy } from "../api/client";
import { Modal } from "../ui/Modal";

/**
 * "Publish new policy" modal — US/India floors + FX convention. Client-side
 * validation mirrors the API rules so Finance sees the constraint before a
 * round-trip; the server is still the source of truth (422 on mismatch).
 */
export function PublishPolicyModal({
  open,
  onClose,
  onPublished,
  allowedFxConventions,
}: {
  open: boolean;
  onClose: () => void;
  onPublished: () => void;
  allowedFxConventions: FxConvention[];
}) {
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [usFloor, setUsFloor] = useState("0.35");
  const [indiaFloor, setIndiaFloor] = useState("0.50");
  const [fxConvention, setFxConvention] = useState<FxConvention>("fixed_at_sow_date");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const validationHint = useMemo(() => {
    const us = Number(usFloor);
    const india = Number(indiaFloor);
    if (!Number.isFinite(us) || !Number.isFinite(india)) return null;
    if (!(us > 0 && us < 1)) return "US floor must be between 0 and 1";
    if (!(india > 0 && india < 1)) return "India floor must be between 0 and 1";
    if (!(us < india)) return "India floor must be strictly greater than US floor";
    return null;
  }, [usFloor, indiaFloor]);

  const canSubmit = effectiveFrom.trim() !== "" && validationHint === null;

  function reset() {
    setEffectiveFrom("");
    setUsFloor("0.35");
    setIndiaFloor("0.50");
    setFxConvention("fixed_at_sow_date");
    setNotes("");
    setError(null);
    setSubmitting(false);
  }

  function handleClose() {
    reset();
    onClose();
  }

  async function submit() {
    setError(null);
    setSubmitting(true);
    try {
      const body: PublishPolicyBody = {
        effective_from: effectiveFrom,
        us_floor: usFloor,
        india_floor: indiaFloor,
        fx_convention: fxConvention,
        notes: notes.trim() || null,
      };
      await publishPolicy(body);
      onPublished();
      reset();
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to publish policy");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title="Publish new policy"
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
          <span style={{ fontSize: 12, color: "#6b7280" }}>US floor (0-1)</span>
          <input
            aria-label="US floor"
            type="number"
            step="0.0001"
            min="0"
            max="1"
            value={usFloor}
            onChange={(e) => setUsFloor(e.target.value)}
            style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>India floor (0-1)</span>
          <input
            aria-label="India floor"
            type="number"
            step="0.0001"
            min="0"
            max="1"
            value={indiaFloor}
            onChange={(e) => setIndiaFloor(e.target.value)}
            style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>FX convention</span>
          <select
            aria-label="FX convention"
            value={fxConvention}
            onChange={(e) => setFxConvention(e.target.value as FxConvention)}
            style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
          >
            {allowedFxConventions.map((fx) => (
              <option key={fx} value={fx}>
                {fx}
              </option>
            ))}
          </select>
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

        {validationHint ? (
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
            {validationHint}
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
