/**
 * SOWUpload — dropzone + progress panel rendered inside `DealDetail`.
 *
 * Flow:
 *   1. User drops a PDF/DOCX into the dropzone.
 *   2. We request a pre-signed PUT URL from the API.
 *   3. The browser PUTs the file directly to S3 (bytes never touch the API).
 *   4. We POST /sow/{opp}/versions with the returned s3_key + a SHA-256 of
 *      the file bytes. That kicks the Bedrock extract job.
 *   5. Parent `DealDetail` re-fetches the current version and swaps to the
 *      confirm screen.
 *
 * File-hash is done via `crypto.subtle.digest("SHA-256", ...)` — no
 * business math, just an integrity token the API stores next to the row.
 */

import { useCallback, useState } from "react";
import type { SowVersion } from "../api/client";
import { ApiError, createSowVersion, getSowUploadUrl } from "../api/client";
import { FileDropzone } from "../ui/FileDropzone";

const CONTENT_TYPES = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
} as const;

// Client-side gate that matches the API's 25 MB limit; keeps a truly
// oversized upload from wasting time on the S3 PUT before the API rejects.
const MAX_BYTES = 25 * 1024 * 1024;

async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export interface SOWUploadProps {
  opportunityId: string;
  onUploaded: (version: SowVersion) => void;
}

export function SOWUpload({ opportunityId, onUploaded }: SOWUploadProps) {
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onFile = useCallback(
    async (file: File) => {
      setError(null);
      setProgress("Preparing upload…");
      setBusy(true);
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

        setProgress("Requesting upload URL…");
        const signed = await getSowUploadUrl(opportunityId, {
          filename: file.name,
          content_type: contentType,
        });

        setProgress("Uploading to S3…");
        const bytes = await file.arrayBuffer();
        const put = await fetch(signed.url, {
          method: "PUT",
          headers: signed.required_headers ?? undefined,
          body: bytes,
        });
        if (!put.ok) {
          throw new Error(`S3 upload failed (${put.status})`);
        }

        setProgress("Hashing + registering version…");
        const hash = await sha256Hex(bytes);
        const version = await createSowVersion(opportunityId, {
          file_s3_key: signed.s3_key,
          file_hash: `sha256:${hash}`,
          file_size: file.size,
        });
        setProgress("Extract running… showing confirm screen.");
        onUploaded(version);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : (err as Error).message);
        setProgress(null);
      } finally {
        setBusy(false);
      }
    },
    [opportunityId, onUploaded],
  );

  return (
    <div>
      <p style={{ color: "#374151", fontSize: 14, marginTop: 0 }}>
        Drop the signed SOW (PDF or DOCX, up to 25&nbsp;MB). Extraction runs
        automatically; you'll confirm each field on the next screen.
      </p>
      <FileDropzone
        accept={[CONTENT_TYPES.pdf, CONTENT_TYPES.docx]}
        disabled={busy}
        onFile={onFile}
        label={busy ? "Working…" : "Drop the SOW here, or click to choose"}
      />
      {progress ? (
        <div
          role="status"
          style={{ marginTop: 8, color: "#065f46", fontSize: 13 }}
        >
          {progress}
        </div>
      ) : null}
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
