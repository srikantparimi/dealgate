import { useCallback, useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";

/**
 * Minimal file picker + drag-drop target.
 *
 * Not a full uploader — this primitive only surfaces the selected `File` and
 * a click / drop event. The calling page is responsible for asking the API
 * for a pre-signed URL and PUT-ing the file (see `AgreementsPanel`).
 *
 * `accept` is a MIME whitelist; anything else surfaces an inline error and
 * `onFile` is not called. Keep the list short so users see one line, not a
 * novella.
 */
export function FileDropzone({
  accept,
  onFile,
  label,
  disabled,
}: {
  accept: string[];
  onFile: (file: File) => void;
  label?: string;
  disabled?: boolean;
}) {
  const [hover, setHover] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    (file: File | null | undefined) => {
      if (!file) return;
      if (accept.length > 0 && !accept.includes(file.type)) {
        setError(`Unsupported file type: ${file.type || "unknown"}`);
        return;
      }
      setError(null);
      onFile(file);
    },
    [accept, onFile],
  );

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setHover(false);
    if (disabled) return;
    const file = e.dataTransfer?.files?.[0];
    handleFile(file);
  }

  function onInputChange(e: ChangeEvent<HTMLInputElement>) {
    handleFile(e.target.files?.[0] ?? null);
    // Reset so re-uploading the same file re-fires the change event.
    e.target.value = "";
  }

  return (
    <div>
      <div
        role="button"
        aria-label={label ?? "Upload file"}
        aria-disabled={disabled}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setHover(true);
        }}
        onDragLeave={() => setHover(false)}
        onDrop={onDrop}
        onClick={() => !disabled && inputRef.current?.click()}
        style={{
          border: `2px dashed ${hover ? "#111827" : "#d1d5db"}`,
          borderRadius: 8,
          padding: 16,
          textAlign: "center",
          background: hover ? "#f3f4f6" : "#fafafa",
          color: "#374151",
          cursor: disabled ? "not-allowed" : "pointer",
          opacity: disabled ? 0.6 : 1,
        }}
      >
        {label ?? "Drop a PDF or DOCX here, or click to choose"}
      </div>
      <input
        ref={inputRef}
        type="file"
        aria-label="Evidence file"
        accept={accept.join(",")}
        onChange={onInputChange}
        style={{ display: "none" }}
      />
      {error ? (
        <div
          role="alert"
          style={{
            marginTop: 8,
            color: "#991b1b",
            fontSize: 13,
          }}
        >
          {error}
        </div>
      ) : null}
    </div>
  );
}
