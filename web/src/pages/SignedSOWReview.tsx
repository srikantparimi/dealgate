/**
 * SignedSOWReview — dropzone + verify + side-by-side diff + release
 * (S5 E8, build-guide §6.7).
 *
 * Mounted inline on ``DealDetail`` when the latest package is
 * ``ready_to_sign``. Flow:
 *
 *   1. Owner drops the executed pdf → we pre-sign a PUT to S3 and
 *      register the upload row.
 *   2. Owner clicks "Verify" → the API re-extracts fields on the pdf
 *      and returns a diff. The diff table lights up red on any
 *      mismatch (price / dates exact; scope ≥ 0.9 similarity).
 *   3. Once ``verify_status === "verified"`` the Release button
 *      un-disables. Clicking it distributes the pdf via SES, files
 *      kickoff + billing-setup tasks, opens a renewal record and
 *      moves the package to ``released``.
 *
 * No math lives in the browser (CLAUDE.md rule 2) — the diff numbers
 * come straight from the API's ``diff_json`` payload. This page is a
 * viewer + button strip; the server does the work.
 */

import { useCallback, useEffect, useState } from "react";
import type {
  SignedSowDiff,
  SignedSowDiffField,
  SignedSowUpload,
} from "../api/client";
import {
  ApiError,
  createSignedSowUpload,
  getSignedSowUpload,
  getSignedSowUploadUrl,
  releaseSignedSow,
  verifySignedSow,
} from "../api/client";
import { FileDropzone } from "../ui/FileDropzone";
import { StatusChip } from "../ui/StatusChip";

const CONTENT_TYPES = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
} as const;

const MAX_BYTES = 25 * 1024 * 1024;

const FIELD_LABELS: Record<SignedSowDiffField["field"], string> = {
  price: "Price",
  term_start: "Term start",
  term_end: "Term end",
  scope_summary: "Scope summary",
};

async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function statusTone(
  s: SignedSowUpload["verify_status"],
): "ok" | "warn" | "block" | "neutral" {
  if (s === "verified") return "ok";
  if (s === "blocked") return "block";
  if (s === "pending") return "warn";
  return "neutral";
}

export interface SignedSOWReviewProps {
  packageId: string;
  /** Owner + SystemAdmin see the write buttons; everyone else read-only. */
  canWrite?: boolean;
}

export function SignedSOWReview({
  packageId,
  canWrite = true,
}: SignedSOWReviewProps) {
  const [upload, setUpload] = useState<SignedSowUpload | null | undefined>(
    undefined,
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const row = await getSignedSowUpload(packageId);
      setUpload(row);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
      setUpload(null);
    }
  }, [packageId]);

  useEffect(() => {
    void load();
  }, [load]);

  const onFile = useCallback(
    async (file: File) => {
      setError(null);
      setBusy("Preparing upload…");
      try {
        if (file.size > MAX_BYTES) {
          throw new Error(
            `File is ${(file.size / 1024 / 1024).toFixed(1)} MB — the limit is 25 MB.`,
          );
        }
        const contentType =
          file.type === CONTENT_TYPES.pdf || file.type === CONTENT_TYPES.docx
            ? file.type
            : file.name.toLowerCase().endsWith(".pdf")
              ? CONTENT_TYPES.pdf
              : CONTENT_TYPES.docx;

        setBusy("Requesting upload URL…");
        const signed = await getSignedSowUploadUrl(packageId, {
          filename: file.name,
          content_type: contentType,
        });

        setBusy("Uploading to S3…");
        const bytes = await file.arrayBuffer();
        const put = await fetch(signed.url, {
          method: "PUT",
          headers: signed.required_headers ?? undefined,
          body: bytes,
        });
        if (!put.ok) throw new Error(`S3 upload failed (${put.status})`);

        setBusy("Registering upload…");
        const hash = await sha256Hex(bytes);
        const row = await createSignedSowUpload(packageId, {
          file_s3_key: signed.s3_key,
          file_hash: `sha256:${hash}`,
        });
        setUpload(row);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : (e as Error).message);
      } finally {
        setBusy(null);
      }
    },
    [packageId],
  );

  async function onVerify() {
    setError(null);
    setBusy("Verifying…");
    try {
      const row = await verifySignedSow(packageId);
      setUpload(row);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function onRelease() {
    setError(null);
    setBusy("Releasing…");
    try {
      const row = await releaseSignedSow(packageId);
      setUpload(row);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (upload === undefined) {
    return (
      <div data-testid="signed-sow-loading" style={{ color: "#6b7280" }}>
        Loading signed SOW…
      </div>
    );
  }

  return (
    <div data-testid="signed-sow-review">
      {upload === null ? (
        canWrite ? (
          <>
            <p style={{ color: "#374151", fontSize: 14, marginTop: 0 }}>
              Drop the executed SOW (PDF or DOCX, up to 25&nbsp;MB). Verification
              re-extracts price, dates and scope; the release button unlocks
              once every material term matches the approved package.
            </p>
            <FileDropzone
              accept={[CONTENT_TYPES.pdf, CONTENT_TYPES.docx]}
              disabled={busy !== null}
              onFile={onFile}
              label={busy ?? "Drop the signed SOW here, or click to choose"}
            />
          </>
        ) : (
          <p style={{ color: "#6b7280", fontSize: 13 }}>
            Waiting for the account owner to upload the executed SOW.
          </p>
        )
      ) : (
        <UploadPanel
          upload={upload}
          busy={busy}
          canWrite={canWrite}
          onReupload={onFile}
          onVerify={onVerify}
          onRelease={onRelease}
        />
      )}
      {error ? (
        <div
          role="alert"
          style={{
            marginTop: 8,
            background: "#fef2f2",
            color: "#991b1b",
            border: "1px solid #fecaca",
            padding: 8,
            borderRadius: 4,
            fontSize: 13,
          }}
        >
          {error}
        </div>
      ) : null}
    </div>
  );
}

function UploadPanel({
  upload,
  busy,
  canWrite,
  onReupload,
  onVerify,
  onRelease,
}: {
  upload: SignedSowUpload;
  busy: string | null;
  canWrite: boolean;
  onReupload: (file: File) => void;
  onVerify: () => void;
  onRelease: () => void;
}) {
  const canRelease = upload.verify_status === "verified" && !upload.released_at;
  const released = upload.released_at !== null;

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <StatusChip tone={statusTone(upload.verify_status)}>
            {upload.verify_status}
          </StatusChip>
          {released ? (
            <StatusChip tone="ok">released</StatusChip>
          ) : null}
          <span style={{ color: "#6b7280", fontSize: 12 }}>
            {upload.file_s3_key}
          </span>
        </div>
        {canWrite && !released ? (
          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="button"
              onClick={onVerify}
              disabled={busy !== null}
              data-testid="signed-sow-verify-btn"
              style={{
                padding: "6px 12px",
                background: "#111827",
                color: "white",
                border: "none",
                borderRadius: 6,
                cursor: busy !== null ? "wait" : "pointer",
                fontSize: 13,
              }}
            >
              {busy === "Verifying…" ? "Verifying…" : "Verify"}
            </button>
            <button
              type="button"
              onClick={onRelease}
              disabled={!canRelease || busy !== null}
              data-testid="signed-sow-release-btn"
              style={{
                padding: "6px 12px",
                background: canRelease ? "#065f46" : "#9ca3af",
                color: "white",
                border: "none",
                borderRadius: 6,
                cursor: canRelease && busy === null ? "pointer" : "not-allowed",
                fontSize: 13,
              }}
            >
              {busy === "Releasing…" ? "Releasing…" : "Release"}
            </button>
          </div>
        ) : null}
      </div>

      {upload.diff_json ? <DiffViewer diff={upload.diff_json} /> : null}

      {canWrite && !released ? (
        <div style={{ marginTop: 16 }}>
          <p style={{ color: "#6b7280", fontSize: 12, margin: "8px 0" }}>
            Uploaded the wrong pdf? Drop a fresh file — the previous
            verification is voided automatically.
          </p>
          <FileDropzone
            accept={[CONTENT_TYPES.pdf, CONTENT_TYPES.docx]}
            disabled={busy !== null}
            onFile={onReupload}
            label={busy ?? "Re-upload the signed SOW"}
          />
        </div>
      ) : null}
    </div>
  );
}

function DiffViewer({ diff }: { diff: SignedSowDiff }) {
  if (!diff.fields || diff.fields.length === 0) {
    return (
      <div
        role="status"
        style={{ color: "#6b7280", fontSize: 13, marginTop: 8 }}
      >
        {diff.reason ?? "No diff available."}
      </div>
    );
  }
  return (
    <table
      data-testid="signed-sow-diff-table"
      style={{
        width: "100%",
        borderCollapse: "collapse",
        marginTop: 8,
        fontSize: 13,
      }}
    >
      <thead>
        <tr>
          <th style={cellStyle}>Field</th>
          <th style={cellStyle}>Approved</th>
          <th style={cellStyle}>Extracted</th>
          <th style={cellStyle}>Match</th>
        </tr>
      </thead>
      <tbody>
        {diff.fields.map((f) => {
          const bg = f.match ? undefined : "#fef2f2";
          return (
            <tr
              key={f.field}
              data-testid={`diff-row-${f.field}`}
              data-match={f.match ? "yes" : "no"}
              style={{ background: bg }}
            >
              <td style={cellStyle}>{FIELD_LABELS[f.field] ?? f.field}</td>
              <td style={cellStyle}>{f.approved ?? "—"}</td>
              <td style={cellStyle}>{f.extracted ?? "—"}</td>
              <td style={cellStyle}>
                {f.match ? (
                  <StatusChip tone="ok">match</StatusChip>
                ) : (
                  <StatusChip tone="block">mismatch</StatusChip>
                )}
                {typeof f.similarity === "number" ? (
                  <span style={{ color: "#6b7280", marginLeft: 6, fontSize: 12 }}>
                    ({(f.similarity * 100).toFixed(1)}%)
                  </span>
                ) : null}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

const cellStyle: React.CSSProperties = {
  border: "1px solid #e5e7eb",
  padding: "6px 8px",
  textAlign: "left",
  verticalAlign: "top",
};
