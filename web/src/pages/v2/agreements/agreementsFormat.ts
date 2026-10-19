// S24-AG1 F1/F8/F9 · display formatting for the NDA & MSA page. Formatting
// only: every state, count and date arrives computed by the API; nothing here
// classifies a client or adds anything up.
import type { ISODateTime } from "../../../api/client";
import { PIPELINE_TIMEZONE } from "../pipeline/format";

/** "Oct 15, 2026": the calendar date of an instant in America/Los_Angeles. */
export function pacificDate(value: ISODateTime | null | undefined, missing = "Date not recorded"): string {
  if (!value) return missing;
  const t = new Date(value);
  if (Number.isNaN(t.getTime())) return missing;
  return t.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: PIPELINE_TIMEZONE,
  });
}

/**
 * The prototype's file sizes ("under 1 KB", "214 KB"). A file of a megabyte or
 * more reads "3.4 MB" instead of "3400 KB". Null when the size is unknown.
 */
export function fileSizeText(bytes: number | null | undefined): string | null {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes) || bytes < 0) return null;
  if (bytes < 1000) return "under 1 KB";
  if (bytes < 1_000_000) return `${Math.round(bytes / 1000)} KB`;
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}

/** A batch is shown by its label (AG-0001). Anything else (a raw id) is never rendered. */
export function isBatchLabel(value: string | null | undefined): value is string {
  return typeof value === "string" && /^[A-Z]{2,}-\d+$/.test(value);
}

/** An error's message for a toast or an alert line. */
export function errorText(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback;
}
