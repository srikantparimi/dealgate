// S24-AG1 F3 · the shared client panel: a right drawer on the Agreements page, a section in the Pipeline
// client preview. One request (GET /clients/{id}/agreements) gives the relationship, the deals, the
// warning and both document cards, including whether a standard copy exists to attach (when an older
// server leaves that out, GET /agreements/standard answers it). Every write is the server's (it answers
// 403 to a non-writer); the panel locks those controls with a reason instead of hiding them. The panel
// never computes a state: it renders what the API says.
//
// Sub-views (upload, mark covered, remove, change relationship) replace the drawer body in place, as
// in the prototype, and Cancel returns to the client. In the Pipeline section they open in a drawer
// over the client preview, so Escape and focus behave as in any other dialog there.
import { useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import {
  AGREEMENT_KINDS,
  attachStandardToClient,
  detachAgreement,
  getClientAgreements,
  getClientDownloadLink,
  getHubspotValues,
  getStandardDocuments,
  markCovered,
  removeMark,
  setRelationship,
  type AgreementKind,
  type ClientAgreements,
  type DocCard,
  type DocState,
  type MarkReason,
  type Relationship,
} from "../../../api/agreements";
import type { UUID } from "../../../api/client";
import { DEFAULT_WORKSPACE_QUERY, workspaceParams } from "../../../api/pipelineWorkspace";
import { cn } from "../../../lib/cn";
import { AgreementStateTag, AgreementTag, RelationshipTag } from "../../../ui-v2/AgreementStateTag";
import { LockedButton } from "../../../ui-v2/LockedButton";
import { Button } from "../../../ui-v2/primitives/button";
import { Input } from "../../../ui-v2/primitives/input";
import { sizeText } from "./fileRules";
import { AgreementsDrawer, useOpenSession } from "./UploadDialog";
import {
  AgreementNote,
  FIELD_LABEL,
  SELECT_CLASS,
  UploadForm,
  calendarText,
  errorText,
  pacificDate,
  pacificToday,
  useSafeToast,
} from "./UploadForm";

export interface ClientAgreementsPanelProps {
  clientId: UUID;
  variant: "drawer" | "section";
  /** Drawer variant only. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Called after any write so the opener refetches its numbers. */
  onChanged?: () => void;
}

type View =
  | { name: "cards" }
  | { name: "upload"; kind: AgreementKind }
  | { name: "mark"; kind: AgreementKind }
  | { name: "remove"; kind: AgreementKind }
  | { name: "relationship" };

/** Additive fields the panel reads when the server sends them (stage words come from the stage mirror). */
type PanelData = ClientAgreements & {
  stage_text?: string | null;
  deals: ClientAgreements["deals"] & { stage_text?: string | null };
};

/** Additive on DocCard: the current standard version of the kind (null: none uploaded yet). */
type CardWithStandard = DocCard & { standard_available_version?: number | null };

type Availability = Record<AgreementKind, boolean>;

/** Whether a standard copy of each kind exists: from the cards when the server says, else one more read. */
async function standardAvailability(data: ClientAgreements): Promise<Availability> {
  const cards = AGREEMENT_KINDS.map((kind) => cardOf(data, kind) as CardWithStandard);
  if (cards.every((card) => "standard_available_version" in card)) {
    return { NDA: cards[0]!.standard_available_version != null, MSA: cards[1]!.standard_available_version != null };
  }
  try {
    const docs = await getStandardDocuments();
    return { NDA: Boolean(docs.NDA), MSA: Boolean(docs.MSA) };
  } catch {
    // Unknown: offer no attach rather than one that may fail.
    return { NDA: false, MSA: false };
  }
}

const MARK_REASONS: { value: Exclude<MarkReason, "per_hubspot">; label: string }[] = [
  { value: "signed_outside_dealgate", label: "Signed outside DealGate" },
  { value: "covered_by_earlier_work", label: "Covered by earlier work" },
  { value: "confirmed_with_client", label: "Confirmed with the client" },
  { value: "other", label: "Other" },
];

const REASON_TEXT: Record<MarkReason, string> = {
  signed_outside_dealgate: "Signed outside DealGate",
  covered_by_earlier_work: "Covered by earlier work",
  confirmed_with_client: "Confirmed with the client",
  per_hubspot: "Per HubSpot",
  other: "Other",
};

/** What a card says when the client holds nothing for the kind (prototype docCard). */
const NOTHING_HELD: Partial<Record<DocState, string>> = {
  missing: "Required: this client is net new and past stage 1.",
  due_later: "Not required until a deal reaches stage 2. You can upload it early.",
  not_needed: "No active deal, so nothing is needed now.",
  existing_none: "Existing client. No standard copy attached yet.",
};

const BU_TEXT: Record<string, string> = {
  ST21: "text-success",
  "IT Avalon": "text-primary-text",
  "Retro Rabbit": "text-warning",
};

const holdsFile = (state: DocState) => state === "client" || state === "standard";
const holdsNothing = (state: DocState) => !holdsFile(state) && state !== "covered";

function cardOf(data: ClientAgreements, kind: AgreementKind): DocCard {
  return kind === "NDA" ? data.nda : data.msa;
}

function missingKinds(data: ClientAgreements): AgreementKind[] {
  return AGREEMENT_KINDS.filter((kind) => cardOf(data, kind).state === "missing");
}

/** The relationship basis in words; the server's basis_text when it sends one. */
function basisText(data: ClientAgreements): string {
  if (data.basis_text) return data.basis_text;
  const by = data.relationship_set_by;
  if (data.relationship === "net_new") {
    if (data.relationship_basis === "manual") return by ? `Marked net new by ${by}` : "Marked net new";
    return "No earlier work found";
  }
  if (data.relationship_basis === "manual") return by ? `Marked existing by ${by}` : "Marked existing";
  if (data.relationship_basis === "closed_won_and_sow") return "Closed Won deal and SOW";
  if (data.relationship_basis === "sow_engagement") return "SOW or engagement";
  return "Closed Won deal";
}

/** "1 open (furthest: 4 · Proposal) · 1 Closed Won · 1 Closed Lost", or "No deals". */
function dealSummary(data: PanelData): string {
  const { open, won, lost, furthest_open_stage: furthest } = data.deals;
  const stage =
    data.stage_text ?? data.deals.stage_text ?? (furthest >= 1 ? `stage ${furthest}` : "stage not recorded");
  const parts: string[] = [];
  if (open) parts.push(`${open} open (furthest: ${stage})`);
  if (won) parts.push(`${won} Closed Won`);
  if (lost) parts.push(`${lost} Closed Lost`);
  return parts.join(" · ") || "No deals";
}

function BusinessUnits({ data }: { data: ClientAgreements }) {
  const units = data.business_units ?? [];
  // The server says why none is shown (e.g. "Region not mapped to a business unit: X"), as the Clients row does.
  if (!units.length) return <>{data.business_unit_note?.trim() || "No business unit recorded"}</>;
  return (
    <span className="inline-flex flex-wrap gap-x-3 gap-y-1">
      {units.map((unit) => (
        <span key={unit.name} className="inline-flex items-baseline gap-1">
          <span className={cn("font-semibold", BU_TEXT[unit.name] ?? "text-text")}>{unit.name}</span>
          <span className="text-secondary text-text-secondary">{`· ${unit.region}`}</span>
        </span>
      ))}
    </span>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-secondary text-text-secondary">{label}</dt>
      <dd className="min-w-0 break-words text-body text-text [overflow-wrap:anywhere]">{children}</dd>
    </>
  );
}

const FACTS_CLASS = "grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] items-baseline gap-x-4 gap-y-2";

// --- the panel ------------------------------------------------------------------------------------

export function ClientAgreementsPanel(props: ClientAgreementsPanelProps) {
  const session = useOpenSession(props.variant === "drawer" ? Boolean(props.open) : true);
  // A new client or a new opening starts clean: no state of the previous one can show.
  return <Panel key={`${props.clientId}:${session}`} {...props} />;
}

interface Receipt {
  kind: AgreementKind;
  jobId: string | null;
}

function Panel({ clientId, variant, open = false, onOpenChange, onChanged }: ClientAgreementsPanelProps) {
  const toast = useSafeToast();
  const active = variant === "section" || open;
  const [data, setData] = useState<PanelData | null>(null);
  const [standard, setStandard] = useState<Availability | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [view, setView] = useState<View>({ name: "cards" });
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [mappedCovered, setMappedCovered] = useState(false);
  const returnKey = useRef<string | null>(null);
  const focusAfterReload = useRef<string | null>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const headingId = useId();

  useEffect(() => {
    if (!active) return;
    const ctl = new AbortController();
    setLoadError(null);
    getClientAgreements(clientId, ctl.signal)
      .then(async (next) => {
        if (ctl.signal.aborted) return;
        const available = await standardAvailability(next);
        if (ctl.signal.aborted) return;
        setData(next as PanelData);
        setStandard(available);
      })
      .catch((err: unknown) => {
        if (!ctl.signal.aborted) setLoadError(errorText(err, "The client's agreements could not load."));
      });
    return () => ctl.abort();
  }, [clientId, active, reload]);

  // The prototype's "mapped as Covered" note under a HubSpot hint: only when the MSA is empty.
  const hint = data?.msa.hubspot_hint ?? null;
  const msaEmpty = data ? holdsNothing(data.msa.state) : false;
  useEffect(() => {
    if (!hint || !msaEmpty) return;
    let live = true;
    getHubspotValues()
      .then((values) => {
        if (live) setMappedCovered(values.items.some((item) => item.value === hint && item.action === "covered"));
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [hint, msaEmpty]);

  const announce = useCallback(
    (message: string) => {
      setStatus(message);
      toast(message);
    },
    [toast],
  );

  /**
   * After a write: focus `focusTarget` once the fresh answer is shown, reload the panel unless the write
   * already returned it, and tell the opener.
   */
  const changed = useCallback(
    (focusTarget: string, reloadPanel = true) => {
      returnKey.current = null;
      focusAfterReload.current = focusTarget;
      if (reloadPanel) setReload((n) => n + 1);
      onChanged?.();
    },
    [onChanged],
  );

  const openView = (next: View, key: string) => {
    returnKey.current = key;
    setActionError(null);
    setView(next);
  };
  const backToCards = useCallback(() => setView({ name: "cards" }), []);

  // Drawer: a sub-view takes focus at its title; Cancel brings focus back to the control that opened it.
  useEffect(() => {
    if (variant !== "drawer" || !open) return;
    if (view.name !== "cards") {
      titleRef.current?.focus();
      return;
    }
    const key = returnKey.current;
    if (!key) return;
    returnKey.current = null;
    bodyRef.current?.querySelector<HTMLElement>(`[data-focus-key="${key}"]`)?.focus();
  }, [view, variant, open]);

  // After a write the control that was used may be gone (Mark covered becomes Remove mark), so focus
  // lands on that kind's card heading, or on Change relationship, once the fresh answer is shown.
  useEffect(() => {
    const target = focusAfterReload.current;
    if (!target || !data) return;
    focusAfterReload.current = null;
    const root = bodyRef.current;
    const el =
      target === "relationship"
        ? root?.querySelector<HTMLElement>(`[data-focus-key="relationship"]`)
        : root?.querySelector<HTMLElement>(`[data-focus-card="${target}"]`);
    el?.focus();
  }, [data]);

  const lock = data?.can_write ? null : ("writer" as const);

  // A request in flight ignores a second press; the button keeps focus (disabling it would drop focus).
  async function download(kind: AgreementKind) {
    if (!data || pending) return;
    setActionError(null);
    setPending(`${kind}:download`);
    try {
      const link = await getClientDownloadLink(data.client_id, kind);
      window.open(link.url, "_blank", "noopener,noreferrer");
      announce(
        `A download link for ${data.name}'s ${kind} was created. It expires in 5 minutes and the download is recorded.`,
      );
      onChanged?.(); // the download is an Activity event: the page's count moves, as for its own downloads
    } catch (err) {
      setActionError(errorText(err, `The ${kind} could not be downloaded.`));
    } finally {
      setPending(null);
    }
  }

  async function attach(kind: AgreementKind) {
    if (!data || pending) return;
    setActionError(null);
    setPending(`${kind}:attach`);
    try {
      await attachStandardToClient(data.client_id, kind);
      announce(`Standard ${kind} attached.`);
      changed(kind);
    } catch (err) {
      setActionError(errorText(err, `The standard ${kind} could not be attached.`));
    } finally {
      setPending(null);
    }
  }

  // --- the views --------------------------------------------------------------------------------

  const cardHeading = variant === "drawer" ? "h3" : "h4";

  const cards = data ? (
    <div ref={bodyRef} className="flex flex-col gap-4">
      {data.needs_attention ? (
        <AgreementNote tone="warning">
          {`This client is net new and past stage 1 with ${missingKinds(data).join(" and ")} missing. This is a warning only. Nothing is blocked.`}
        </AgreementNote>
      ) : null}

      <dl className={FACTS_CLASS}>
        <Fact label="Relationship">
          <span className="inline-flex flex-wrap items-center gap-2">
            <RelationshipTag relationship={data.relationship} />
            <span>{basisText(data)}</span>
          </span>
        </Fact>
        {variant === "drawer" ? (
          <>
            <Fact label="Business unit">
              <BusinessUnits data={data} />
            </Fact>
            <Fact label="Deals">{dealSummary(data)}</Fact>
          </>
        ) : null}
        {data.possible_duplicates?.length ? (
          <Fact label="Possible duplicate of">{data.possible_duplicates.join(", ")}</Fact>
        ) : null}
        {data.flags?.includes("unknown_company") ? (
          <Fact label="Note">HubSpot sent a deal with no company. Give it a real client first.</Fact>
        ) : null}
        {data.flags?.includes("test_data") ? <Fact label="Note">Test data. Never attached in a backfill.</Fact> : null}
      </dl>

      <div className="flex flex-wrap gap-2">
        <LockedButton
          variant="secondary"
          lock={lock}
          data-focus-key="relationship"
          onClick={() => openView({ name: "relationship" }, "relationship")}
        >
          Change relationship
        </LockedButton>
        {variant === "drawer" ? (
          <Button variant="secondary" asChild>
            <Link to={`/pipeline?${workspaceParams({ ...DEFAULT_WORKSPACE_QUERY, status: "all", q: data.name.slice(0, 120) })}`}>
              Open deals in Pipeline
              <span aria-hidden="true">{" ↗"}</span>
            </Link>
          </Button>
        ) : null}
      </div>

      {receipt ? (
        <p className="text-secondary text-text-secondary">
          {receipt.jobId
            ? `${receipt.kind} removed. Its stored files are queued for cleanup.`
            : `${receipt.kind} removed.`}
          {receipt.jobId ? (
            <>
              {" "}
              <Link to={`/deletions/${encodeURIComponent(receipt.jobId)}`} className="text-primary-text underline">
                View cleanup status
              </Link>
            </>
          ) : null}
        </p>
      ) : null}

      {actionError ? (
        <p role="alert" className="text-secondary text-danger">
          {actionError}
        </p>
      ) : null}

      {AGREEMENT_KINDS.map((kind) => (
        <DocCardView
          key={kind}
          kind={kind}
          card={cardOf(data, kind)}
          heading={cardHeading}
          lock={lock}
          standardAvailable={Boolean(standard?.[kind])}
          pending={pending}
          mappedCovered={kind === "MSA" && mappedCovered}
          onDownload={() => void download(kind)}
          onUpload={() => openView({ name: "upload", kind }, `${kind}:upload`)}
          onAttach={() => void attach(kind)}
          onMark={() => openView({ name: "mark", kind }, `${kind}:mark`)}
          onRemove={() => openView({ name: "remove", kind }, `${kind}:remove`)}
        />
      ))}
    </div>
  ) : null;

  let subTitle = "";
  let subKicker = data?.name ?? "";
  let sub: ReactNode = null;
  if (data && view.name === "upload") {
    subKicker = "Upload";
    subTitle = "Upload a document";
    sub = (
      <UploadForm
        target={{ mode: "client", clientId: data.client_id, clientName: data.name, kind: view.kind, lockTarget: true }}
        canWrite={data.can_write}
        cancelLabel="Cancel"
        onCancel={backToCards}
        onBusyChange={setBusy}
        onUploaded={(_result, message) => {
          setStatus(message);
          setReceipt(null);
          changed(view.kind);
          backToCards();
        }}
      />
    );
  } else if (data && view.name === "mark") {
    subTitle = `Mark ${view.kind} covered`;
    sub = (
      <MarkForm
        data={data}
        kind={view.kind}
        onCancel={backToCards}
        onDone={() => {
          announce(`${view.kind} marked covered.`);
          setReceipt(null);
          changed(view.kind);
          backToCards();
        }}
      />
    );
  } else if (data && view.name === "remove") {
    const card = cardOf(data, view.kind);
    subTitle = card.state === "covered" ? `Remove ${view.kind} mark` : `Remove ${view.kind} from this client`;
    sub = (
      <RemoveConfirm
        data={data}
        kind={view.kind}
        card={card}
        onCancel={backToCards}
        onDone={(jobId) => {
          announce(`${view.kind} removed.`);
          setReceipt(card.state === "covered" ? null : { kind: view.kind, jobId });
          changed(view.kind);
          backToCards();
        }}
      />
    );
  } else if (data && view.name === "relationship") {
    subTitle = "Change relationship";
    sub = (
      <RelationshipForm
        data={data}
        onCancel={backToCards}
        onDone={(next) => {
          setStatus(`Relationship changed to ${next.relationship === "existing" ? "existing" : "net new"}.`);
          // PUT /relationship answers with the whole panel: no second request.
          changed("relationship", false);
          setData(next as PanelData);
          backToCards();
        }}
      />
    );
  }

  const loading = !data && !loadError;
  const state = loadError ? (
    <div role="alert" className="flex flex-col items-start gap-2">
      <AgreementNote tone="warning">{loadError}</AgreementNote>
      <Button variant="secondary" onClick={() => setReload((n) => n + 1)}>
        Try again
      </Button>
    </div>
  ) : loading ? (
    <p role="status" className="text-body text-text-secondary">
      Loading the client's NDA and MSA…
    </p>
  ) : null;

  // A live region the screen reader hears even while a drawer hides the page's toasts.
  const live = (
    <p role="status" aria-live="polite" className="sr-only">
      {status}
    </p>
  );

  if (variant === "drawer") {
    const inSub = view.name !== "cards" && sub !== null;
    return (
      <AgreementsDrawer
        open={open}
        onOpenChange={(next) => onOpenChange?.(next)}
        kicker={inSub ? subKicker : "Client · agreements"}
        title={inSub ? subTitle : (data?.name ?? "Client agreements")}
        busy={busy}
        titleRef={titleRef}
      >
        {live}
        {state}
        {inSub ? sub : cards}
      </AgreementsDrawer>
    );
  }

  // Section (Pipeline client preview): the cards inline; a sub-view opens in a drawer over the preview.
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3">
      <h3 id={headingId} className="text-section text-text">
        Agreement documents
      </h3>
      {live}
      {state}
      {cards}
      <AgreementsDrawer
        open={view.name !== "cards" && sub !== null}
        onOpenChange={(next) => {
          if (!next) backToCards();
        }}
        kicker={subKicker}
        title={subTitle}
        busy={busy}
        fallbackFocus={() => {
          const key = returnKey.current?.split(":")[0];
          return (
            (key ? bodyRef.current?.querySelector<HTMLElement>(`[data-focus-card="${key}"]`) : null) ??
            document.getElementById(headingId)
          );
        }}
      >
        {sub}
      </AgreementsDrawer>
    </section>
  );
}

// --- one kind's card ------------------------------------------------------------------------------

function DocCardView({
  kind,
  card,
  heading: Heading,
  lock,
  standardAvailable,
  pending,
  mappedCovered,
  onDownload,
  onUpload,
  onAttach,
  onMark,
  onRemove,
}: {
  kind: AgreementKind;
  card: DocCard;
  heading: "h3" | "h4";
  lock: "writer" | null;
  standardAvailable: boolean;
  pending: string | null;
  mappedCovered: boolean;
  onDownload: () => void;
  onUpload: () => void;
  onAttach: () => void;
  onMark: () => void;
  onRemove: () => void;
}) {
  const file = holdsFile(card.state);
  const covered = card.state === "covered";
  const nothing = holdsNothing(card.state);
  const headingId = useId();
  const uploadLabel =
    card.state === "client" ? "Upload new version" : card.state === "standard" ? "Replace with client copy" : null;

  let detail: ReactNode;
  if (covered && card.mark) {
    const mark = card.mark;
    const note = mark.note || (mark.hubspot_value ? `msa_type “${mark.hubspot_value}”` : null);
    detail = (
      <dl className={FACTS_CLASS}>
        <Fact label="Marked by">{`${mark.marked_by} · ${calendarText(mark.marked_on)}`}</Fact>
        <Fact label="Reason">{(mark as { reason_label?: string }).reason_label || REASON_TEXT[mark.reason] || mark.reason}</Fact>
        <Fact label="Source">{mark.source === "hubspot" ? "HubSpot msa_type" : "DealGate"}</Fact>
        {note ? <Fact label="Note">{note}</Fact> : null}
      </dl>
    );
  } else if (file) {
    const source =
      card.state === "standard"
        ? `Standard ${kind}${card.standard_version ? ` v${card.standard_version}` : ""}${card.batch_id ? ` · batch ${card.batch_id}` : ""}`
        : `Client copy for this client${card.version_no && card.version_no > 1 ? ` · version ${card.version_no}` : ""}`;
    detail = (
      <dl className={FACTS_CLASS}>
        <Fact label="File">
          {card.file_size !== null && card.file_size !== undefined
            ? `${card.file_name ?? "File name not recorded"} · ${sizeText(card.file_size)}`
            : (card.file_name ?? "File name not recorded")}
        </Fact>
        <Fact label="Source">{source}</Fact>
        <Fact label="Uploaded by">{`${card.uploaded_by ?? "Uploader not recorded"} · ${pacificDate(card.uploaded_at)}`}</Fact>
        {card.note ? <Fact label="Note">{card.note}</Fact> : null}
      </dl>
    );
  } else {
    detail = <p className="text-body text-text-secondary">{NOTHING_HELD[card.state] ?? ""}</p>;
  }

  return (
    <article
      aria-labelledby={headingId}
      className="flex flex-col gap-3 rounded-card border border-border bg-surface-sunken p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <Heading id={headingId} tabIndex={-1} data-focus-card={kind} className="text-section text-text">
          {kind}
        </Heading>
        <AgreementStateTag state={card.state} />
      </div>
      {detail}
      {kind === "MSA" && card.hubspot_hint ? (
        <p className="text-secondary text-text-secondary">
          HubSpot <code className="font-mono">msa_type</code>: {`“${card.hubspot_hint}”`}{" "}
          <AgreementTag>hint only</AgreementTag>
          {mappedCovered && nothing ? " · mapped as Covered, applies when you run the mapping" : null}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {file ? (
          <Button
            variant="secondary"
            data-focus-key={`${kind}:download`}
            aria-busy={pending === `${kind}:download` || undefined}
            onClick={onDownload}
          >
            <span aria-hidden="true">{"↓ "}</span>
            Download
          </Button>
        ) : null}
        <LockedButton variant="secondary" lock={lock} data-focus-key={`${kind}:upload`} onClick={onUpload}>
          {uploadLabel ?? (
            <>
              <span aria-hidden="true">{"↑ "}</span>
              Upload client copy
            </>
          )}
        </LockedButton>
        {nothing && standardAvailable ? (
          <LockedButton
            variant="secondary"
            lock={lock}
            data-focus-key={`${kind}:attach`}
            aria-busy={pending === `${kind}:attach` || undefined}
            onClick={onAttach}
          >
            Attach standard copy
          </LockedButton>
        ) : null}
        {nothing ? (
          <LockedButton variant="secondary" lock={lock} data-focus-key={`${kind}:mark`} onClick={onMark}>
            Mark covered
          </LockedButton>
        ) : null}
        {!nothing ? (
          <LockedButton variant="secondary" lock={lock} data-focus-key={`${kind}:remove`} onClick={onRemove}>
            {covered ? "Remove mark" : "Remove from client"}
          </LockedButton>
        ) : null}
      </div>
      {card.history.length ? (
        <details className="text-secondary text-text-secondary">
          <summary className="cursor-pointer rounded-control text-primary-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus">
            {`History (${card.history.length})`}
          </summary>
          <ol className="mt-2 flex flex-col gap-1">
            {card.history.map((entry, i) => (
              <li key={`${entry.at}-${i}`} className="break-words [overflow-wrap:anywhere]">
                {`${pacificDate(entry.at)} · ${entry.by} · ${entry.what}`}
              </li>
            ))}
          </ol>
        </details>
      ) : null}
    </article>
  );
}

// --- sub-views ------------------------------------------------------------------------------------

function MarkForm({
  data,
  kind,
  onCancel,
  onDone,
}: {
  data: ClientAgreements;
  kind: AgreementKind;
  onCancel: () => void;
  onDone: (card: DocCard) => void;
}) {
  const today = useMemo(() => pacificToday(), []);
  const ids = useId();
  const [reason, setReason] = useState<Exclude<MarkReason, "per_hubspot">>("signed_outside_dealgate");
  const [date, setDate] = useState(today);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit() {
    if (saving) return;
    if (!date) {
      setError("Choose a date.");
      return;
    }
    if (date > today) {
      setError("The date cannot be in the future.");
      return;
    }
    setError(null);
    setSaving(true);
    try {
      const card = await markCovered(data.client_id, kind, {
        reason,
        marked_on: date,
        ...(note.trim() ? { note: note.trim() } : {}),
      });
      onDone(card);
    } catch (err) {
      setError(errorText(err, `The ${kind} could not be marked covered.`));
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-body text-text">
        {`Use this when the ${kind} is in place but there is no file to attach here.${
          data.relationship === "net_new" ? " The warning for this client clears." : ""
        } Records who marked it and why.`}
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label htmlFor={`${ids}-reason`} className={FIELD_LABEL}>
            Reason
          </label>
          <select
            id={`${ids}-reason`}
            className={SELECT_CLASS}
            value={reason}
            onChange={(event) => setReason(event.target.value as Exclude<MarkReason, "per_hubspot">)}
          >
            {MARK_REASONS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor={`${ids}-date`} className={FIELD_LABEL}>
            Date it was signed or confirmed
          </label>
          <Input
            id={`${ids}-date`}
            type="date"
            value={date}
            max={today}
            onChange={(event) => setDate(event.target.value)}
          />
        </div>
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor={`${ids}-note`} className={FIELD_LABEL}>
          Note (optional)
        </label>
        <Input id={`${ids}-note`} maxLength={200} value={note} onChange={(event) => setNote(event.target.value)} />
      </div>
      {error ? (
        <p role="alert" className="text-secondary text-danger">
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => void submit()} aria-busy={saving || undefined}>
          Mark covered
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

function RemoveConfirm({
  data,
  kind,
  card,
  onCancel,
  onDone,
}: {
  data: ClientAgreements;
  kind: AgreementKind;
  card: DocCard;
  onCancel: () => void;
  onDone: (jobId: string | null) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const mark = card.state === "covered";
  // Truthful per source: a standard attachment removes only this client's row (the shared file stays);
  // a client copy goes through the deletion job, which deletes its stored files and versions.
  const text = mark
    ? "The client goes back to its normal status."
    : card.state === "standard"
      ? `The standard copy is detached from ${data.name}. The shared standard file stays for every other client, and you can attach it again later.`
      : `The client copy is removed from ${data.name} with all its versions. The stored files are queued for cleanup. This cannot be undone.`;

  async function submit() {
    if (saving) return;
    setError(null);
    setSaving(true);
    try {
      if (mark) {
        await removeMark(data.client_id, kind);
        onDone(null);
        return;
      }
      const answer = await detachAgreement(data.client_id, kind);
      const jobId =
        answer && typeof answer === "object" && "job_id" in answer && answer.job_id ? String(answer.job_id) : null;
      onDone(jobId);
    } catch (err) {
      setError(errorText(err, `The ${kind} could not be removed.`));
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-body text-text">{text}</p>
      {error ? (
        <p role="alert" className="text-secondary text-danger">
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button variant="destructive" onClick={() => void submit()} aria-busy={saving || undefined}>
          Remove
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

function RelationshipForm({
  data,
  onCancel,
  onDone,
}: {
  data: ClientAgreements;
  onCancel: () => void;
  onDone: (next: ClientAgreements) => void;
}) {
  const id = useId();
  const [value, setValue] = useState<Relationship>(data.relationship);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit() {
    if (saving) return;
    // Only a stored manual value equal to the choice is a no-op; a provisional (live) value is stored by hand.
    if (value === data.relationship && data.relationship_basis === "manual") {
      onCancel();
      return;
    }
    setError(null);
    setSaving(true);
    try {
      onDone(await setRelationship(data.client_id, { relationship: value }));
    } catch (err) {
      setError(errorText(err, "The relationship could not be changed."));
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-body text-text">
        Existing clients are covered by the standard copies. Net-new clients need their own copy. Use this to correct a
        client, for example a duplicate or a test record.
      </p>
      <div className="flex flex-col gap-1">
        <label htmlFor={id} className={FIELD_LABEL}>
          Relationship
        </label>
        <select
          id={id}
          className={SELECT_CLASS}
          value={value}
          onChange={(event) => setValue(event.target.value as Relationship)}
        >
          <option value="existing">Existing: worked with before</option>
          <option value="net_new">Net new</option>
        </select>
      </div>
      {error ? (
        <p role="alert" className="text-secondary text-danger">
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => void submit()} aria-busy={saving || undefined}>
          Save
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
