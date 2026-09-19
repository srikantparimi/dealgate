/**
 * Margin Lab display helpers — spec §9.
 *
 * The Lab NEVER computes a margin, revenue or eligible-cost figure in
 * the browser (spec §21, CLAUDE.md rule 2). Everything numeric comes
 * from `POST /gm/sandbox`. These helpers only translate what the
 * server returned into copy the panels can render.
 */
import type { SandboxResponse } from "../../../api/client";
import type { StatusTone } from "../../../ui-v2/StatusBadge";

export type MarginMode = "baseline" | "draft" | "scenarios";

export interface ModeDef {
  id: MarginMode;
  label: string;
  helper: string;
}

export const MARGIN_MODES: ModeDef[] = [
  {
    id: "baseline",
    label: "Approved baseline",
    helper: "Read-only. The last version Finance approved.",
  },
  {
    id: "draft",
    label: "Current draft",
    helper: "Editable. Not approved for commitment.",
  },
  {
    id: "scenarios",
    label: "Scenarios",
    helper: "What-ifs on price / mix / effort. Never replaces baseline.",
  },
];

/**
 * Two-tone summary for a US or India floor test. Server owns the pass
 * boolean; the UI only picks a tone + label + word.
 */
export function floorOutcome(
  pass: boolean | undefined,
  hasRevenue: boolean,
): { tone: StatusTone; label: string } {
  if (!hasRevenue) return { tone: "neutral", label: "Not applicable" };
  if (pass) return { tone: "ok", label: "Pass" };
  return { tone: "danger", label: "Fail" };
}

/** Format a Decimal-string percentage the server sent. The API sends
 * values like "0.2777" — we render them as e.g. "27.77%". Never do
 * math, only string manipulation. */
export function formatMarginPct(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const match = value.match(/^-?\d+(?:\.\d+)?$/);
  if (!match) return value;
  // Convert to percent by moving the decimal two places — this is
  // presentational only; policy uses the full-precision Decimal.
  const negative = value.startsWith("-");
  const raw = negative ? value.slice(1) : value;
  const [intPart, fracPart = ""] = raw.split(".");
  const padded = intPart + fracPart.padEnd(4, "0");
  const intPortion = padded.slice(0, padded.length - 2) || "0";
  const fracPortion = padded.slice(padded.length - 2);
  const withoutLeading = intPortion.replace(/^0+(?=\d)/, "");
  const withSign = (negative ? "-" : "") + (withoutLeading || "0");
  return `${withSign}.${fracPortion}%`;
}

/** Copy for the "Draft · Not approved for commitment" chip — required
 * whenever the current mode is editable (spec §9). */
export function draftChipLabel(): string {
  return "Draft · Not approved for commitment";
}

export function overallMarginTone(sandbox: SandboxResponse): StatusTone {
  if (!sandbox.complete) return "warn";
  if (sandbox.policy.requires_ceo) return "danger";
  return "ok";
}
