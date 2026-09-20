/**
 * Compact upload panel — the only thing the screen shows before an
 * opportunity id is resolved.
 *
 * S10-01: the client field is gone; the SOW is the input. The moment
 * the file is attached the enclosing ``UploadFlow`` calls
 * ``POST /sows/upload`` and hands the job off to ``PipelineProgress``.
 * There is nothing else for the reviewer to type here — that is the
 * point (docs/directives/sow-first.md).
 */
import { useState } from "react";
import { Upload } from "lucide-react";
import { Button } from "../../../../ui-v2/primitives/button";
import { Label } from "../../../../ui-v2/primitives/label";
import { Section } from "./Section";

export interface UploadPanelProps {
  /** Called when the reviewer submits the file. */
  onSubmit: (input: { file: File }) => Promise<void>;
  submitting: boolean;
  error: string | null;
}

export function UploadPanel({ onSubmit, submitting, error }: UploadPanelProps) {
  const [file, setFile] = useState<File | null>(null);

  const ready = Boolean(file);

  return (
    <Section
      id="section-upload"
      title="Upload a SOW to start"
      description="Drop the SOW file. The system extracts every commercial field, matches or creates the client, classifies the engagement, builds the staffing plan and computes the GM. You confirm on the next screen."
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!ready) return;
          void onSubmit({ file: file! });
        }}
      >
        <div>
          <Label htmlFor="upload-file">SOW file</Label>
          <input
            id="upload-file"
            type="file"
            accept="application/pdf,.pdf,.docx"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="mt-1 block w-full text-secondary text-text-secondary"
            data-testid="upload-file-input"
          />
          {file ? (
            <p
              className="mt-1 text-secondary text-text-secondary"
              data-testid="upload-file-staged"
            >
              Staged: {file.name} · {Math.max(1, Math.round(file.size / 1024))} kB
            </p>
          ) : null}
          <p
            className="mt-2 text-secondary text-text-secondary"
            data-testid="upload-client-note"
          >
            Client is read from the SOW.
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-secondary text-text-secondary">
            No fields to fill here — that is the point. Everything else is
            derived.
          </p>
          <Button
            type="submit"
            variant="primary"
            disabled={!ready || submitting}
            data-testid="upload-submit"
          >
            <Upload className="h-4 w-4" aria-hidden />
            {submitting ? "Uploading…" : "Upload & derive"}
          </Button>
        </div>
        {error ? (
          <p role="alert" className="text-danger" data-testid="upload-error">
            {error}
          </p>
        ) : null}
      </form>
    </Section>
  );
}
