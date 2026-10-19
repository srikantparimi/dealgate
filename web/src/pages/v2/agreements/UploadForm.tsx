// S24-AG1 F2 · the one upload form: the page's "Upload document" dialog, a client panel's upload, the
// standard panels and the attach wizard's step 1 all use it. It checks the file in the browser exactly
// as the server will (fileRules.ts), says what the file will be stored as and what the upload will do
// (replace a standard copy for one client, add a version, add a standard version), sends it with real
// byte progress (XMLHttpRequest upload events), then shows an honest indeterminate "Saving…" until the
// server answers. Every dynamic value is a React text node.
//
// Also home to the small helpers the FE-B dialogs share (Pacific dates, error text, notes, toasts).
import { useCallback, useEffect, useId, useState, type KeyboardEvent, type ReactNode } from "react";

import {
  AGREEMENT_KINDS,
  getAgreementsWorkspace,
  getClientAgreements,
  getStandardDocuments,
  uploadClientCopy,
  uploadStandard,
  type AgreementKind,
  type ClientAgreements,
  type ClientRow,
  type StandardDocuments,
} from "../../../api/agreements";
import { ApiError, type UUID } from "../../../api/client";
import { cn } from "../../../lib/cn";
import { FileDropzone } from "../../../ui/FileDropzone";
import { LOCK_TOAST } from "../../../ui-v2/LockedButton";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";
import { useToast } from "../../../ui-v2/primitives/toaster";
import { ACCEPTED_EXTENSIONS, MSG_TYPE, checkFile, displayName, sizeText, storedName, extensionOf } from "./fileRules";
import type { UploadResult, UploadTarget } from "./UploadDialog";

// --- shared helpers -----------------------------------------------------------------------------

export const PACIFIC_TIMEZONE = "America/Los_Angeles";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "Oct 15, 2026" for an instant, in America/Los_Angeles (the business calendar). */
export function pacificDate(value: string | null | undefined, missing = "date not recorded"): string {
  if (!value) return missing;
  const t = new Date(value);
  if (Number.isNaN(t.getTime())) return missing;
  return t.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: PACIFIC_TIMEZONE });
}

/** "Oct 15, 2026" for a calendar date (YYYY-MM-DD); no time-zone shift. */
export function calendarText(value: string | null | undefined, missing = "date not recorded"): string {
  if (!value) return missing;
  const [y, m, d] = value.split("-").map(Number);
  if (!y || !m || !d || m < 1 || m > 12) return missing;
  return `${MONTHS[m - 1]} ${d}, ${y}`;
}

/** Today's calendar date in America/Los_Angeles, YYYY-MM-DD (the server's business_today). */
export function pacificToday(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: PACIFIC_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const part = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

/** The server's message for a failed call, or `fallback` when it sent none. */
export function errorText(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    return /^API error \d+$/.test(err.message) ? `${fallback} (error ${err.status})` : err.message;
  }
  return err instanceof Error && err.message ? err.message : fallback;
}

export function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}

/** "NDA and MSA", "NDA". */
export function kindsText(kinds: readonly string[]): string {
  return kinds.length ? kinds.join(" and ") : "no document";
}

/**
 * The app's toast, or nothing when rendered outside a <Toaster> (a page test that mounts a strip on
 * its own). The hook order never changes: useToast always calls useContext before it throws.
 */
export function useSafeToast(): (title: string) => void {
  let ctx: ReturnType<typeof useToast> | null;
  try {
    ctx = useToast();
  } catch {
    ctx = null;
  }
  return useCallback((title: string) => ctx?.toast({ title }), [ctx]);
}

export const FIELD_LABEL = "text-secondary font-medium text-text-secondary";
export const SELECT_CLASS =
  "h-10 w-full rounded-control border border-input-border bg-surface px-3 text-body text-text focus-visible:outline-focus disabled:cursor-not-allowed disabled:opacity-60";

/** The prototype's two note styles: an info box (violet) and a warning callout (amber). */
export function AgreementNote({ tone, children }: { tone: "info" | "warning"; children: ReactNode }) {
  return (
    <div
      className={cn(
        "rounded-control border px-3 py-2 text-secondary",
        tone === "info"
          ? "border-primary/20 bg-primary-subtle text-text"
          : "border-l-4 border-warning bg-warning-surface text-warning",
      )}
    >
      {children}
    </div>
  );
}

/** Bar for a progress value 0-100; `null` draws an indeterminate bar. */
export function ProgressBar({ label, value, valueText }: { label: string; value: number | null; valueText: string }) {
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={value === null ? undefined : 0}
      aria-valuemax={value === null ? undefined : 100}
      aria-valuenow={value === null ? undefined : value}
      aria-valuetext={valueText}
      className="h-2 w-full overflow-hidden rounded-avatar bg-surface-sunken"
    >
      {value === null ? (
        <div className="h-full w-1/3 animate-pulse rounded-avatar bg-primary" />
      ) : (
        <div className="h-full rounded-avatar bg-primary transition-motion" style={{ width: `${value}%` }} />
      )}
    </div>
  );
}

// --- client picker ------------------------------------------------------------------------------

interface PickedClient {
  id: UUID;
  name: string;
}

/** "IT Avalon · US · 2 deals": enough to tell two clients with the same name apart, never an id. */
function clientSubline(row: ClientRow): string {
  const units =
    row.business_units.map((b) => `${b.name} · ${b.region}`).join(", ") ||
    row.business_unit_note?.trim() ||
    "No business unit recorded";
  const flags = row.flags.includes("possible_duplicate") ? " · Possible duplicate" : "";
  return `${units} · ${row.deal_count} ${plural(row.deal_count, "deal", "deals")}${flags}`;
}

/**
 * The client field: a combobox over the Agreements population (the same clients the page lists),
 * keyed by id, because names repeat (D10).
 */
function ClientPicker({
  inputId,
  value,
  onChange,
  disabled,
}: {
  inputId: string;
  value: PickedClient | null;
  onChange: (client: PickedClient | null) => void;
  disabled: boolean;
}) {
  const [text, setText] = useState(value?.name ?? "");
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<ClientRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(-1);
  const listId = useId();

  useEffect(() => {
    if (!open) return;
    const ctl = new AbortController();
    const timer = setTimeout(() => {
      getAgreementsWorkspace({ q: text.trim().slice(0, 120), sort: "name", page: 1, page_size: 25 }, ctl.signal)
        .then((ws) => {
          if (ctl.signal.aborted) return;
          setItems(ws.items);
          setError(null);
          setActive(ws.items.length ? 0 : -1);
        })
        .catch((err: unknown) => {
          if (ctl.signal.aborted) return;
          setItems([]);
          setError(errorText(err, "The client list could not load."));
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      ctl.abort();
    };
  }, [text, open]);

  const choose = (row: ClientRow) => {
    setText(row.name);
    setOpen(false);
    onChange({ id: row.client_id, name: row.name });
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    const count = items?.length ?? 0;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      if (count) setActive((i) => (i + 1) % count);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (count) setActive((i) => (i <= 0 ? count - 1 : i - 1));
    } else if (event.key === "Enter") {
      if (open && items && active >= 0 && items[active]) {
        event.preventDefault();
        choose(items[active]);
      }
    } else if (event.key === "Escape") {
      // The drawer leaves an open list's Escape to the list (AgreementsDrawer).
      if (open) setOpen(false);
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  };

  return (
    <div className="flex flex-col gap-1">
      <Input
        id={inputId}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && active >= 0 && items?.[active] ? `${listId}-${active}` : undefined}
        placeholder="Start typing a client name"
        autoComplete="off"
        value={text}
        disabled={disabled}
        onChange={(event) => {
          setText(event.target.value);
          setOpen(true);
          if (value) onChange(null);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      />
      {open ? (
        <ul
          id={listId}
          role="listbox"
          aria-label="Clients"
          className="max-h-64 overflow-y-auto rounded-control border border-border bg-surface shadow-menu"
        >
          {items === null ? (
            <li role="presentation" className="px-3 py-2 text-secondary text-text-secondary">
              Searching clients…
            </li>
          ) : error ? (
            <li role="presentation" className="px-3 py-2 text-secondary text-danger">
              {error}
            </li>
          ) : items.length === 0 ? (
            <li role="presentation" className="px-3 py-2 text-secondary text-text-secondary">
              {`No client matches “${text.trim()}”.`}
            </li>
          ) : (
            items.map((row, i) => (
              <li
                key={row.client_id}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                // Keep focus in the field so the list stays open until the click lands.
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose(row)}
                className={cn(
                  "cursor-pointer border-b border-border px-3 py-2 last:border-b-0",
                  i === active ? "bg-primary-subtle" : "hover:bg-primary-subtle",
                )}
              >
                <span className="block break-words text-body text-text [overflow-wrap:anywhere]">{row.name}</span>
                <span className="block text-secondary text-text-secondary">{clientSubline(row)}</span>
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}

// --- the form ---------------------------------------------------------------------------------

type Phase = { kind: "idle" } | { kind: "sending"; loaded: number; total: number } | { kind: "saving" };

export interface UploadFormProps {
  target: UploadTarget;
  canWrite: boolean;
  /** "Cancel", or "Back to attach" from the attach wizard. */
  cancelLabel: string;
  onCancel: () => void;
  /** The server accepted the file; `message` is the confirmation already shown as a toast. */
  onUploaded: (result: UploadResult, message: string) => void;
  /** True from the first byte to the server's answer: the container must not close meanwhile. */
  onBusyChange?: (busy: boolean) => void;
  /** The document type and "What is this?" as currently chosen (the dialog title follows them). */
  onSelectionChange?: (mode: "client" | "standard", kind: AgreementKind) => void;
}

const validateFile = async (file: File): Promise<string | null> => {
  const result = await checkFile(file);
  return result.ok ? null : result.message;
};

const describeFile = (file: File) => `${displayName(file.name)} · ${sizeText(file.size)}`;

export function UploadForm({
  target,
  canWrite,
  cancelLabel,
  onCancel,
  onUploaded,
  onBusyChange,
  onSelectionChange,
}: UploadFormProps) {
  const toast = useSafeToast();
  const ids = useId();
  // The client and "What is this?" are fixed when the form opens on a client or from the wizard.
  const targetFixed = Boolean(target.lockTarget || target.clientId);
  const [kind, setKind] = useState<AgreementKind>(target.kind ?? "NDA");
  const [mode, setMode] = useState<"client" | "standard">(target.mode);
  const [client, setClient] = useState<PickedClient | null>(
    target.clientId ? { id: target.clientId, name: target.clientName ?? "" } : null,
  );
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [error, setError] = useState<string | null>(null);
  const [holdings, setHoldings] = useState<ClientAgreements | null>(null);
  const [standard, setStandard] = useState<StandardDocuments | null>(null);
  const busy = phase.kind !== "idle";

  useEffect(() => {
    onSelectionChange?.(mode, kind);
  }, [mode, kind, onSelectionChange]);

  // What the chosen client holds now, for the replace / new-version notices.
  const clientId = mode === "client" ? (client?.id ?? null) : null;
  useEffect(() => {
    setHoldings(null);
    if (!clientId) return;
    const ctl = new AbortController();
    getClientAgreements(clientId, ctl.signal)
      .then((data) => {
        if (!ctl.signal.aborted) setHoldings(data);
      })
      .catch(() => {
        // The notice is a courtesy; the upload itself still works and the server decides.
      });
    return () => ctl.abort();
  }, [clientId]);

  // The current standard versions, for "This adds version N".
  useEffect(() => {
    if (mode !== "standard" || standard) return;
    let live = true;
    getStandardDocuments()
      .then((docs) => {
        if (live) setStandard(docs);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [mode, standard]);

  const onFile = useCallback((next: File | null) => {
    setFile(next);
    setError(null);
  }, []);

  const clientName = client?.name || holdings?.name || "";

  let notice: { tone: "info" | "warning"; text: string } | null = null;
  if (mode === "standard") {
    const current = standard?.[kind];
    if (standard) {
      notice = current
        ? {
            tone: "info",
            text: `This adds version ${current.version + 1} of the standard ${kind}. Copies already attached to clients stay as they are.`,
          }
        : {
            tone: "info",
            text: `This becomes the standard ${kind}. You attach it to existing clients in one step afterwards.`,
          };
    }
  } else if (holdings) {
    const card = kind === "NDA" ? holdings.nda : holdings.msa;
    if (card.state === "standard") {
      notice = {
        tone: "warning",
        text: `This client holds the standard ${kind}. Your upload replaces it for this client only. The standard copy stays for everyone else.`,
      };
    } else if (card.state === "client") {
      notice = {
        tone: "warning",
        text: `This adds a new version of this client's ${kind}. The earlier version stays in history.`,
      };
    }
  }

  async function submit() {
    if (!file || busy) return;
    if (!canWrite) {
      setError(LOCK_TOAST.writer);
      return;
    }
    if (mode === "client" && !client) {
      setError("Choose a client from the list.");
      return;
    }
    setError(null);
    setPhase({ kind: "sending", loaded: 0, total: file.size });
    onBusyChange?.(true);
    const onProgress = (loaded: number, total: number) =>
      setPhase(total > 0 && loaded >= total ? { kind: "saving" } : { kind: "sending", loaded, total });
    try {
      let result: UploadResult;
      let message: string;
      if (mode === "standard") {
        const version = await uploadStandard(kind, file, onProgress);
        result = { mode, kind, clientId: null };
        message = `Standard ${kind} v${version.version} uploaded.`;
      } else {
        await uploadClientCopy(client!.id, kind, file, note, onProgress);
        result = { mode, kind, clientId: client!.id };
        message = `Client ${kind} saved for ${clientName || "this client"}.`;
      }
      setPhase({ kind: "idle" });
      onBusyChange?.(false);
      toast(message);
      onUploaded(result, message);
    } catch (err) {
      setPhase({ kind: "idle" });
      onBusyChange?.(false);
      setError(errorText(err, "The upload failed. Try again."));
    }
  }

  if (!canWrite) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-body text-text">{LOCK_TOAST.writer}</p>
        <div>
          <Button variant="secondary" onClick={onCancel}>
            {cancelLabel}
          </Button>
        </div>
      </div>
    );
  }

  const kindId = `${ids}-kind`;
  const modeId = `${ids}-mode`;
  const clientInputId = `${ids}-client`;
  const noteId = `${ids}-note`;
  const ext = file ? extensionOf(file.name) : "";
  const pct = phase.kind === "sending" && phase.total > 0 ? Math.min(100, Math.round((phase.loaded / phase.total) * 100)) : 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label htmlFor={kindId} className={FIELD_LABEL}>
            Document type
          </label>
          <select
            id={kindId}
            className={SELECT_CLASS}
            value={kind}
            disabled={busy}
            onChange={(event) => setKind(event.target.value as AgreementKind)}
          >
            {AGREEMENT_KINDS.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor={modeId} className={FIELD_LABEL}>
            What is this?
          </label>
          <select
            id={modeId}
            className={SELECT_CLASS}
            value={mode}
            disabled={targetFixed || busy}
            onChange={(event) => setMode(event.target.value as "client" | "standard")}
          >
            <option value="client">Client copy (for one client)</option>
            <option value="standard">Standard copy (for many clients)</option>
          </select>
        </div>
      </div>

      {mode === "client" ? (
        <>
          <div className="flex flex-col gap-1">
            <label htmlFor={clientInputId} className={FIELD_LABEL}>
              Client
            </label>
            {target.clientId ? (
              <Input id={clientInputId} value={clientName} readOnly />
            ) : (
              <ClientPicker inputId={clientInputId} value={client} onChange={setClient} disabled={busy} />
            )}
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor={noteId} className={FIELD_LABEL}>
              Note about this version (optional)
            </label>
            <Input
              id={noteId}
              maxLength={200}
              placeholder="For example: updated payment terms"
              value={note}
              disabled={busy}
              onChange={(event) => setNote(event.target.value)}
            />
          </div>
        </>
      ) : null}

      {notice ? <AgreementNote tone={notice.tone}>{notice.text}</AgreementNote> : null}

      <FileDropzone
        accept={[...ACCEPTED_EXTENSIONS]}
        label="PDF or Word (.docx), up to 25 MB"
        inputLabel="Choose a file"
        typeMessage={MSG_TYPE}
        validate={validateFile}
        describe={describeFile}
        onFile={onFile}
        disabled={busy}
      />

      {file && (ext === "pdf" || ext === "docx") ? (
        <p className="text-secondary text-text-secondary">
          Will be stored as{" "}
          <code className="break-words font-mono text-text [overflow-wrap:anywhere]">{storedName(file.name, ext)}</code>
        </p>
      ) : null}

      {phase.kind === "sending" ? (
        <div className="flex flex-col gap-1">
          {phase.total > 0 ? (
            <ProgressBar label="Upload progress" value={pct} valueText={`${pct}% sent`} />
          ) : (
            <ProgressBar label="Upload progress" value={null} valueText="Sending" />
          )}
          <p className="text-secondary text-text-secondary">{phase.total > 0 ? `Uploading… ${pct}%` : "Uploading…"}</p>
        </div>
      ) : phase.kind === "saving" ? (
        <div className="flex flex-col gap-1">
          <ProgressBar label="Upload progress" value={null} valueText="Saving" />
          <p role="status" className="text-secondary text-text-secondary">
            Saving…
          </p>
        </div>
      ) : null}

      {error ? (
        <p role="alert" className="text-secondary text-danger">
          {error}
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {/* Not disabled while sending: that would drop keyboard focus; submit() ignores a second press. */}
        <Button onClick={() => void submit()} disabled={!file} aria-busy={busy || undefined}>
          Upload
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={busy}>
          {cancelLabel}
        </Button>
      </div>
    </div>
  );
}
