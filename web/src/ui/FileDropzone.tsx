import { useCallback, useId, useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";

import { cn } from "../lib/cn";

/**
 * Click, keyboard or drag-and-drop file picker (S24-AG1 F2 adopts it; D12).
 *
 * - Keyboard: the file input stays in the tab order, visually hidden inside the
 *   zone's label, so Tab reaches it and Enter or Space opens the browser's
 *   picker; the zone shows the focus ring while the input has focus.
 * - `accept` is a list of extensions (".pdf", ".docx"). The browser's MIME type
 *   is not trusted, so the name's extension is checked here, then `validate`
 *   runs the caller's own checks (size, empty, first bytes) and returns a
 *   message, or null when the file passes.
 * - States: idle (the prompt), ok ("name · size"), bad (the name, and the
 *   message in a role=alert line the input points at).
 * - Tokens only (no hex), so it follows the light and dark themes.
 *
 * Not an uploader: it hands the chosen `File` to `onFile` (null when a choice
 * is rejected) and the caller sends it.
 */
export interface FileDropzoneProps {
  /** Allowed extensions, with the dot: [".pdf", ".docx"]. Also the input's accept attribute. */
  accept: string[];
  /** A file that passed every check, or null when the latest choice was rejected. */
  onFile: (file: File | null) => void;
  /** The caller's checks after the extension; resolves to an error message, or null when the file is fine. */
  validate?: (file: File) => Promise<string | null> | string | null;
  /** The prompt shown in the zone before a file is chosen. */
  label?: string;
  /** Accessible name of the file input. */
  inputLabel?: string;
  /** Message for a name whose extension is not in `accept`. */
  typeMessage?: string;
  /** Text for an accepted file (default: its name). */
  describe?: (file: File) => string;
  disabled?: boolean;
}

type ZoneState =
  | { kind: "idle" }
  | { kind: "checking"; text: string }
  | { kind: "ok"; text: string }
  | { kind: "bad"; text: string; message: string };

/** ".pdf" for "Contract.PDF"; the same extension rule as the server (agreement_files._EXT). */
function extensionOf(name: string): string {
  const match = /\.([A-Za-z0-9]+)(?=\n?$)/.exec(name.split(/[\\/]/).pop() ?? "");
  return match ? `.${match[1]!.toLowerCase()}` : "";
}

export function FileDropzone({
  accept,
  onFile,
  validate,
  label = "Drop a file here, or choose one",
  inputLabel = "Choose a file",
  typeMessage = "This type of file cannot be uploaded.",
  describe,
  disabled = false,
}: FileDropzoneProps) {
  const [hover, setHover] = useState(false);
  const [zone, setZone] = useState<ZoneState>({ kind: "idle" });
  const latest = useRef(0);
  const inputId = useId();
  const hintId = useId();
  const errorId = useId();

  const handleFile = useCallback(
    async (file: File | null | undefined) => {
      if (!file) return;
      const run = ++latest.current;
      const allowed = accept.map((a) => a.toLowerCase());
      if (!allowed.includes(extensionOf(file.name))) {
        setZone({ kind: "bad", text: file.name, message: typeMessage });
        onFile(null);
        return;
      }
      setZone({ kind: "checking", text: file.name });
      onFile(null);
      let message: string | null = null;
      try {
        message = validate ? await validate(file) : null;
      } catch (err) {
        message = err instanceof Error && err.message ? err.message : "This file could not be read.";
      }
      // A newer choice replaced this one while it was being checked.
      if (run !== latest.current) return;
      if (message) {
        setZone({ kind: "bad", text: file.name, message });
        onFile(null);
        return;
      }
      setZone({ kind: "ok", text: describe ? describe(file) : file.name });
      onFile(file);
    },
    [accept, describe, onFile, typeMessage, validate],
  );

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setHover(false);
    if (disabled) return;
    void handleFile(event.dataTransfer?.files?.[0]);
  }

  function onInputChange(event: ChangeEvent<HTMLInputElement>) {
    void handleFile(event.target.files?.[0] ?? null);
    // Reset so choosing the same file again fires the change event again.
    event.target.value = "";
  }

  const text = zone.kind === "idle" ? label : zone.text;
  return (
    <div className="flex flex-col gap-2">
      <label
        htmlFor={inputId}
        data-state={zone.kind}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setHover(true);
        }}
        onDragLeave={() => setHover(false)}
        onDrop={onDrop}
        className={cn(
          "relative flex flex-col items-center gap-2 rounded-card border-2 border-dashed px-4 py-5 text-center transition-motion",
          "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus",
          zone.kind === "ok"
            ? "border-success bg-success-surface"
            : zone.kind === "bad"
              ? "border-danger bg-danger-surface"
              : hover
                ? "border-primary bg-primary-subtle"
                : "border-input-border bg-surface-sunken",
          disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer",
        )}
      >
        <span
          id={hintId}
          className={cn(
            "max-w-full break-words text-body [overflow-wrap:anywhere]",
            zone.kind === "bad" ? "text-danger" : "text-text",
          )}
        >
          {text}
        </span>
        <span
          aria-hidden="true"
          className="inline-flex h-8 items-center rounded-control border border-input-border bg-surface px-3 text-secondary font-medium text-text"
        >
          {inputLabel}
        </span>
        <input
          id={inputId}
          type="file"
          className="sr-only"
          accept={accept.join(",")}
          aria-label={inputLabel}
          aria-describedby={zone.kind === "bad" ? `${hintId} ${errorId}` : hintId}
          aria-invalid={zone.kind === "bad" ? true : undefined}
          disabled={disabled}
          onChange={onInputChange}
        />
      </label>
      {zone.kind === "bad" ? (
        <p id={errorId} role="alert" className="text-secondary text-danger">
          {zone.message}
        </p>
      ) : null}
    </div>
  );
}
