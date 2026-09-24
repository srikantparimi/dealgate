/**
 * S15 · D1 — Honest banner about extraction state.
 *
 * A single sentence at the top of Confirm/Staffing when the SOW's
 * `extract_status` is not `complete`. Reads `extract_error` from the
 * confirmation payload so the reviewer sees WHY manual entry is required
 * (bedrock rejected the request, document has no readable text, etc.)
 * instead of the previous silent "Not on the SOW" x 15.
 *
 * The Retry button re-runs Bedrock on the stored S3 object via
 * `POST /sow/versions/{id}/reextract`. Idempotent — re-running against
 * a version that is already `complete` re-extracts and overwrites the
 * fields per `run_extract`'s documented semantics.
 *
 * Only two states render:
 *   1. `pending` / `manual_required` → warning banner + Retry.
 *   2. `complete` → nothing (component returns null).
 */
import { useState } from "react";
import { AlertTriangle, RefreshCcw } from "lucide-react";
import {
  ApiError,
  reextractSowVersion,
  type SowConfirmationPayload,
  type SowVersion,
  type UUID,
} from "../../../../api/client";
import { Button } from "../../../../ui-v2/primitives/button";

export interface ExtractStatusBannerProps {
  payload: SowConfirmationPayload;
  /** Called with the freshly re-extracted version so the parent refetches
   * the confirmation payload. */
  onReextracted?: (version: SowVersion) => void;
}

/** Turn a raw pipeline reason into a sentence a human can read. */
function humanise(reason: string | null): string {
  if (!reason) {
    return "The extractor could not read this document.";
  }
  const s = reason.trim();
  // "extract manual_required: bedrock rejected the request: ValidationException"
  //  -> "bedrock rejected the request: ValidationException"
  if (s.startsWith("extract manual_required:")) {
    return s.slice("extract manual_required:".length).trim();
  }
  if (s.startsWith("extract crashed:")) {
    return `extractor crashed — ${s.slice("extract crashed:".length).trim()}`;
  }
  return s;
}

export function ExtractStatusBanner({
  payload,
  onReextracted,
}: ExtractStatusBannerProps) {
  const status = payload.sow_version.extract_status;
  const reason = payload.sow_version.extract_error ?? null;
  const versionId = payload.sow_version.id as UUID;

  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  if (status === "complete") return null;

  const heading =
    status === "pending"
      ? "Extraction has not run yet"
      : "We couldn't read this document";

  async function onRetry() {
    setBusy(true);
    setFailure(null);
    try {
      const updated = await reextractSowVersion(versionId);
      onReextracted?.(updated);
    } catch (err) {
      const msg =
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : err instanceof Error
            ? err.message
            : "Retry failed. Try again in a moment.";
      setFailure(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      role="alert"
      data-testid="extract-status-banner"
      data-extract-status={status}
      className="rounded-panel border border-warning/50 bg-warning-surface p-3"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-2 min-w-0">
          <AlertTriangle
            className="mt-0.5 h-5 w-5 text-warning shrink-0"
            aria-hidden
          />
          <div className="min-w-0">
            <p className="text-body text-text font-medium">{heading}</p>
            <p className="mt-1 text-secondary text-text-secondary">
              {status === "pending"
                ? "The pipeline is still preparing this SOW. Retry the extraction, or fill the fields below manually."
                : `Reason: ${humanise(reason)}. Retry extraction, or fill the fields below manually — fields you enter carry provenance "manual".`}
            </p>
            {failure ? (
              <p className="mt-2 text-secondary text-danger" role="status">
                {failure}
              </p>
            ) : null}
          </div>
        </div>
        <Button
          variant="secondary"
          onClick={onRetry}
          disabled={busy}
          data-testid="extract-retry-button"
        >
          <RefreshCcw
            className={`h-4 w-4 mr-2 ${busy ? "animate-spin" : ""}`}
            aria-hidden
          />
          {busy ? "Retrying…" : "Retry extraction"}
        </Button>
      </div>
    </div>
  );
}
