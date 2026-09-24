/**
 * S15 · D2 — Blocker → editor registry.
 *
 * Every "What's still needed" row renders its input INLINE in the row.
 * The registry maps a `needs_you.field` key to (a) a display label,
 * (b) an inline editor component, (c) an optional fall-through target
 * for "Jump to field" when the row's editor is not applicable (e.g. a
 * missing GM prerequisite that owns its own section).
 *
 * The signatories fix in S12 was a one-off; S15 makes it the pattern.
 * A blocker key with no editor is itself a bug — the completeness test
 * in `blockerRegistry.test.tsx` fails the build if a canonical field
 * lands without an entry.
 *
 * Adding a new blocker: define the field key on the server side (a
 * `needs_you` row), then add an entry here. The `assertRegistered`
 * helper below is what the test calls with the canonical list.
 */
import { useState } from "react";
import type { ReactNode } from "react";
import {
  ApiError,
  confirmSowField,
  type PickedSignatory,
  type SowConfirmationPayload,
  type SowFieldName,
  type UUID,
} from "../../../../api/client";
import { Button } from "../../../../ui-v2/primitives/button";
import { SignatoriesPicker } from "./SignatoriesPicker";
import { readField } from "./helpers";

/** Editor props are the same for every blocker so the registry can be
 * mapped and tested uniformly. */
export interface BlockerEditorProps {
  payload: SowConfirmationPayload;
  onChanged: () => void;
  /** Optional signatories change hook — the parent's optimistic update
   * for the one blocker where the picker owns its own network write. */
  onSignatoriesChange?: (next: PickedSignatory[]) => void;
}

export interface BlockerRegistryEntry {
  /** Human label rendered in bold at the top of the row. */
  label: string;
  /** Inline editor. Every blocker must have one — Rule 13 (CLAUDE.md). */
  Editor: (props: BlockerEditorProps) => ReactNode;
  /** Optional fallback DOM id if the editor decides to defer. */
  jumpTo?: string;
}

// ---------------------------------------------------------------------------
// Inline editors — each one lives inside the "What's still needed" row and
// writes directly to the /sow/versions/{id}/fields/{name} endpoint.
// ---------------------------------------------------------------------------

/** Single-line text field. */
function InlineTextEditor({
  fieldName,
  placeholder,
}: {
  fieldName: SowFieldName;
  placeholder: string;
}): (props: BlockerEditorProps) => ReactNode {
  function Editor({ payload, onChanged }: BlockerEditorProps) {
    const initial =
      String(readField(payload.sow_version.extracted_fields, fieldName)?.value ?? "") ||
      "";
    const [value, setValue] = useState(initial);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const versionId = payload.sow_version.id as UUID;
    async function save() {
      if (!value.trim()) {
        setError("Please enter a value before saving.");
        return;
      }
      setBusy(true);
      setError(null);
      try {
        await confirmSowField(versionId, fieldName, value.trim());
        onChanged();
      } catch (err) {
        setError(
          err instanceof ApiError && typeof err.detail === "string"
            ? err.detail
            : err instanceof Error
              ? err.message
              : "Save failed. Try again.",
        );
      } finally {
        setBusy(false);
      }
    }
    return (
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          type="text"
          data-testid={`blocker-editor-${fieldName}`}
          aria-label={`${fieldName} value`}
          className="flex-1 min-w-0 rounded-control border border-divider bg-surface p-2 text-body"
          value={value}
          placeholder={placeholder}
          onChange={(e) => setValue(e.target.value)}
        />
        <Button onClick={save} disabled={busy || !value.trim()}>
          {busy ? "Saving…" : "Save"}
        </Button>
        {error ? (
          <p role="alert" className="text-secondary text-danger sm:col-span-2">
            {error}
          </p>
        ) : null}
      </div>
    );
  }
  return Editor;
}

/** Multi-line textarea for `scope_summary`. */
function ScopeSummaryEditor({ payload, onChanged }: BlockerEditorProps) {
  const initial =
    String(readField(payload.sow_version.extracted_fields, "scope_summary")?.value ?? "") ||
    "";
  const [value, setValue] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const versionId = payload.sow_version.id as UUID;
  async function save() {
    if (!value.trim()) {
      setError("Please enter a scope summary before saving.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await confirmSowField(versionId, "scope_summary", value.trim());
      onChanged();
    } catch (err) {
      setError(
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : err instanceof Error
            ? err.message
            : "Save failed. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-2">
      <textarea
        data-testid="blocker-editor-scope_summary"
        aria-label="Scope summary"
        className="min-h-[96px] rounded-control border border-divider bg-surface p-2 text-body"
        value={value}
        placeholder="One or two sentences that describe what SmarTek21 is delivering."
        onChange={(e) => setValue(e.target.value)}
      />
      <div className="flex items-center justify-end gap-2">
        <Button onClick={save} disabled={busy || !value.trim()}>
          {busy ? "Saving…" : "Save"}
        </Button>
      </div>
      {error ? (
        <p role="alert" className="text-secondary text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** Money field for `price` — formatted display, plain-decimal write. */
function PriceEditor({ payload, onChanged }: BlockerEditorProps) {
  const initial =
    String(readField(payload.sow_version.extracted_fields, "price")?.value ?? "") || "";
  const [value, setValue] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const versionId = payload.sow_version.id as UUID;
  async function save() {
    // Strip currency + thousands separators before saving; the server
    // parses `Decimal(...)` and rejects a bare "$50,000.00".
    const cleaned = value.replace(/[$,\s]/g, "");
    if (!cleaned) {
      setError("Enter a price before saving.");
      return;
    }
    if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) {
      setError("Price must be a number like 50000 or 50000.00.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await confirmSowField(versionId, "price", cleaned);
      onChanged();
    } catch (err) {
      setError(
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : err instanceof Error
            ? err.message
            : "Save failed. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
      <div className="flex-1 min-w-0 flex items-center rounded-control border border-divider bg-surface">
        <span className="pl-2 text-text-secondary">$</span>
        <input
          type="text"
          inputMode="decimal"
          data-testid="blocker-editor-price"
          aria-label="Contract price in USD"
          className="w-full min-w-0 bg-transparent p-2 text-body focus:outline-none"
          value={value}
          placeholder="50000"
          onChange={(e) => setValue(e.target.value)}
        />
      </div>
      <Button onClick={save} disabled={busy || !value.trim()}>
        {busy ? "Saving…" : "Save"}
      </Button>
      {error ? (
        <p role="alert" className="text-secondary text-danger sm:col-span-3">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function DateEditor({
  fieldName,
}: {
  fieldName: SowFieldName;
}): (props: BlockerEditorProps) => ReactNode {
  function Editor({ payload, onChanged }: BlockerEditorProps) {
    const raw = String(
      readField(payload.sow_version.extracted_fields, fieldName)?.value ?? "",
    );
    // The extractor sometimes returns literal placeholders like
    // "[SOW Effective Date]" — those are not real ISO dates; start empty.
    const initial = /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : "";
    const [value, setValue] = useState(initial);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const versionId = payload.sow_version.id as UUID;
    async function save() {
      if (!value) {
        setError("Pick a date before saving.");
        return;
      }
      setBusy(true);
      setError(null);
      try {
        await confirmSowField(versionId, fieldName, value);
        onChanged();
      } catch (err) {
        setError(
          err instanceof ApiError && typeof err.detail === "string"
            ? err.detail
            : err instanceof Error
              ? err.message
              : "Save failed. Try again.",
        );
      } finally {
        setBusy(false);
      }
    }
    return (
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          type="date"
          data-testid={`blocker-editor-${fieldName}`}
          aria-label={`${fieldName} date`}
          className="rounded-control border border-divider bg-surface p-2 text-body"
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <Button onClick={save} disabled={busy || !value}>
          {busy ? "Saving…" : "Save"}
        </Button>
        {error ? (
          <p role="alert" className="text-secondary text-danger">
            {error}
          </p>
        ) : null}
      </div>
    );
  }
  return Editor;
}

/** Two-button chooser for the engagement type. The suggested value lives in
 *  `engagement_type_suggested` in the extracted_fields; confirmation flips
 *  the sibling `engagement_type_suggested` on the version and lets the
 *  ScopeSection / auto-classify propagate the confirmation downstream. */
function EngagementTypeEditor({ payload, onChanged }: BlockerEditorProps) {
  const [busy, setBusy] = useState<null | "fixed_price" | "tm">(null);
  const [error, setError] = useState<string | null>(null);
  const versionId = payload.sow_version.id as UUID;
  async function pick(kind: "fixed_price" | "tm") {
    setBusy(kind);
    setError(null);
    try {
      // The confirm endpoint only whitelists `engagement_type_suggested`
      // — writing the suggested value with `provenance=manual` is the
      // documented path for a human override (see confirm_field in
      // sow_extract.py).
      await confirmSowField(versionId, "engagement_type_suggested", kind);
      onChanged();
    } catch (err) {
      setError(
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : err instanceof Error
            ? err.message
            : "Save failed. Try again.",
      );
    } finally {
      setBusy(null);
    }
  }
  return (
    <div className="flex flex-col gap-2">
      <div id="engagement-chooser" className="flex flex-wrap gap-2">
        <Button
          data-testid="blocker-editor-engagement_type-fixed_price"
          disabled={busy !== null}
          onClick={() => pick("fixed_price")}
        >
          {busy === "fixed_price" ? "Saving…" : "Fixed price"}
        </Button>
        <Button
          variant="secondary"
          data-testid="blocker-editor-engagement_type-tm"
          disabled={busy !== null}
          onClick={() => pick("tm")}
        >
          {busy === "tm" ? "Saving…" : "Time & materials"}
        </Button>
      </div>
      {error ? (
        <p role="alert" className="text-secondary text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** List editor for `deliverables` — one line per bullet, save writes an array. */
function DeliverablesEditor({ payload, onChanged }: BlockerEditorProps) {
  const initialValue = readField(payload.sow_version.extracted_fields, "deliverables")?.value;
  const initialList = Array.isArray(initialValue)
    ? initialValue.map((x) => String(x))
    : [];
  const [items, setItems] = useState<string[]>(
    initialList.length > 0 ? initialList : [""],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const versionId = payload.sow_version.id as UUID;
  function setAt(i: number, val: string) {
    setItems((prev) => prev.map((x, j) => (i === j ? val : x)));
  }
  function addRow() {
    setItems((prev) => [...prev, ""]);
  }
  function removeRow(i: number) {
    setItems((prev) => (prev.length <= 1 ? prev : prev.filter((_, j) => j !== i)));
  }
  async function save() {
    const cleaned = items.map((x) => x.trim()).filter(Boolean);
    if (cleaned.length === 0) {
      setError("Add at least one deliverable before saving.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await confirmSowField(versionId, "deliverables", cleaned);
      onChanged();
    } catch (err) {
      setError(
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : err instanceof Error
            ? err.message
            : "Save failed. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div
      className="flex flex-col gap-2"
      data-testid="blocker-editor-deliverables"
    >
      {items.map((row, i) => (
        <div key={i} className="flex items-center gap-2">
          <input
            type="text"
            aria-label={`Deliverable ${i + 1}`}
            className="flex-1 min-w-0 rounded-control border border-divider bg-surface p-2 text-body"
            value={row}
            placeholder="Executive briefing"
            onChange={(e) => setAt(i, e.target.value)}
          />
          <Button
            variant="secondary"
            onClick={() => removeRow(i)}
            disabled={items.length <= 1}
          >
            Remove
          </Button>
        </div>
      ))}
      <div className="flex items-center justify-between gap-2">
        <Button variant="secondary" onClick={addRow}>
          Add deliverable
        </Button>
        <Button onClick={save} disabled={busy}>
          {busy ? "Saving…" : "Save"}
        </Button>
      </div>
      {error ? (
        <p role="alert" className="text-secondary text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** Signatories keep their existing picker — same shape as everything else. */
function SignatoriesEditor({
  payload,
  onChanged,
  onSignatoriesChange,
}: BlockerEditorProps) {
  const versionId = payload.sow_version.id as UUID;
  const clientId = (payload.source?.client_id ?? null) as UUID | null;
  const value = readField(payload.sow_version.extracted_fields, "signatories")?.value;
  return (
    <SignatoriesPicker
      id={`blocker-editor-signatories`}
      sowVersionId={versionId}
      clientId={clientId}
      value={value}
      onChange={(next) => {
        onSignatoriesChange?.(next);
        onChanged();
      }}
    />
  );
}

/** Staffing / GM fields do not resolve on this row — they own their own
 * section. We forward the reviewer to it via jumpTo. */
function StaffingRedirectEditor() {
  return (
    <p className="text-secondary text-text-secondary">
      This blocker resolves on the Staffing &amp; GM section — jump there
      to fix it.
    </p>
  );
}

// ---------------------------------------------------------------------------
// The registry.
// ---------------------------------------------------------------------------

export const BLOCKER_REGISTRY: Record<string, BlockerRegistryEntry> = {
  scope_summary: {
    label: "Scope summary",
    Editor: ScopeSummaryEditor,
  },
  price: {
    label: "Contract price",
    Editor: PriceEditor,
  },
  currency: {
    label: "Currency",
    Editor: InlineTextEditor({
      fieldName: "currency",
      placeholder: "USD",
    }),
  },
  term_start: {
    label: "Term start",
    Editor: DateEditor({ fieldName: "term_start" }),
  },
  term_end: {
    label: "Term end",
    Editor: DateEditor({ fieldName: "term_end" }),
  },
  engagement_type: {
    label: "Engagement type",
    Editor: EngagementTypeEditor,
    jumpTo: "engagement-chooser",
  },
  deliverables: {
    label: "Deliverables",
    Editor: DeliverablesEditor,
  },
  signatories: {
    label: "Signatories",
    Editor: SignatoriesEditor,
  },
  billing_basis: {
    label: "Billing basis",
    Editor: InlineTextEditor({
      fieldName: "billing_basis",
      placeholder: "Fixed fee of $50,000.00, excluding taxes and travel",
    }),
  },
  notice_date: {
    label: "Notice date",
    Editor: DateEditor({ fieldName: "notice_date" }),
  },
  // Client / legal-entity fields aren't confirm-endpoint targets; the
  // Source section owns them (client resolver + agreements). Redirect.
  client_legal_name: {
    label: "Client legal name",
    Editor: StaffingRedirectEditor,
    jumpTo: "section-source",
  },
  client_domain: {
    label: "Client domain",
    Editor: StaffingRedirectEditor,
    jumpTo: "section-source",
  },
  // Server-side blockers that live in another section entirely — the row
  // still gets an editor component, but the editor tells the reviewer to
  // jump. Rule 13 says every blocker must have an editor; that is exactly
  // what a redirect-editor is. Do NOT delete these entries — the test
  // catches the miss.
  gm_model: {
    label: "Staffing & GM",
    Editor: StaffingRedirectEditor,
    jumpTo: "section-staffing",
  },
  rate_card: {
    label: "Rate card",
    Editor: StaffingRedirectEditor,
    jumpTo: "section-ratecard",
  },
};

/**
 * Look up an entry. Handles the `signatories[i].email` / `staffing[0].*`
 * subscripted-key shapes the server sometimes emits by folding to the base.
 */
export function lookupBlocker(fieldKey: string): BlockerRegistryEntry | null {
  if (BLOCKER_REGISTRY[fieldKey]) return BLOCKER_REGISTRY[fieldKey];
  const base = fieldKey.split(/[\[.]/, 1)[0];
  if (base && BLOCKER_REGISTRY[base]) return BLOCKER_REGISTRY[base];
  return null;
}

/**
 * Test helper. Asserts that every canonical blocker key has an editor.
 * The unit test in `blockerRegistry.test.tsx` calls this with the full
 * list of blocker keys the server can emit — a missing entry fails the
 * build so nobody re-introduces a Rule 13 defect.
 */
export function assertRegistered(fieldKeys: readonly string[]): void {
  const missing = fieldKeys.filter((k) => lookupBlocker(k) === null);
  if (missing.length > 0) {
    throw new Error(
      `Rule 13: blocker(s) with no inline editor: ${missing.join(", ")}. ` +
        `Add entries in web/src/pages/v2/sow-studio/confirmation/blockerRegistry.tsx.`,
    );
  }
}
