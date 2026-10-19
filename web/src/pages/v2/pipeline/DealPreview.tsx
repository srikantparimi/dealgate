// S23-PL2 F11 · the deal preview (spec §6.1): a right drawer with the deal's
// facts, the open-deal callouts, the next action and its editor, SOW and
// agreement documents, and real destinations (Upload SOW / Open SOW workspace,
// HubSpot). No alerts, no notes, no editing of HubSpot fields.
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { hubspotDealUrl } from "../../../api/appConfig";
import type { DealRow } from "../../../api/pipelineWorkspace";
import { Button } from "../../../ui-v2/primitives/button";
import { Sheet, SheetContent, SheetTitle } from "../../../ui-v2/primitives/sheet";
import { calendarDate, currencyCode, fullMoney } from "./format";
import { NextActionEditor, type ShownNextAction } from "./NextActionEditor";
import {
  AgreementTags,
  BusinessUnitLine,
  Glyph,
  SowTag,
  StageTag,
  Tag,
  businessUnitFact,
  isOpenDeal,
  ownerFullName,
} from "./tags";

export interface DealPreviewProps {
  deal: DealRow | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  today: string;
  hubspotPortalId: string | null;
  /** The signed-in user's id (from /me): a new next action is assigned to them. */
  assigneeId: string | null;
  onOpenClient: (client: { id: string; name: string }) => void;
  /** Receives the deal with `watching` as shown before the click: false → watch, true → stop watching. */
  onToggleWatch: (deal: DealRow) => Promise<void>;
  /** After a next action is saved: the page asks for the workspace again. */
  onChanged: () => void;
}

export const previewSheetClass = "flex w-full flex-col gap-5 overflow-y-auto sm:max-w-[530px]";
export const kickerClass = "text-label uppercase text-primaryText";

export function DealPreview({
  deal,
  open,
  onOpenChange,
  today,
  hubspotPortalId,
  assigneeId,
  onOpenClient,
  onToggleWatch,
  onChanged,
}: DealPreviewProps) {
  return (
    <Sheet open={open && deal !== null} onOpenChange={onOpenChange}>
      <SheetContent side="right" className={previewSheetClass} aria-describedby={undefined}>
        {deal ? (
          <DealPreviewBody
            key={deal.id}
            deal={deal}
            today={today}
            hubspotPortalId={hubspotPortalId}
            assigneeId={assigneeId}
            onOpenClient={onOpenClient}
            onToggleWatch={onToggleWatch}
            onChanged={onChanged}
          />
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function DealPreviewBody({
  deal,
  today,
  hubspotPortalId,
  assigneeId,
  onOpenClient,
  onToggleWatch,
  onChanged,
}: Omit<DealPreviewProps, "open" | "onOpenChange" | "deal"> & { deal: DealRow }) {
  const open = isOpenDeal(deal);

  // What the panel shows follows the row, and a save made here shows at once.
  const [action, setAction] = useState<ShownNextAction | null>(deal.next_action);
  const rowAction = deal.next_action;
  useEffect(() => {
    setAction(rowAction);
    // The row's action changed (a refreshed row for the same deal).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rowAction?.id, rowAction?.text, rowAction?.due_on]);

  const [watching, setWatching] = useState(deal.watching);
  const [watchBusy, setWatchBusy] = useState(false);
  // Every fresh row for this deal (after the page asks the API again) says what is true.
  useEffect(() => setWatching(deal.watching), [deal]);
  const toggleWatch = async () => {
    const before = watching;
    setWatching(!before);
    setWatchBusy(true);
    try {
      await onToggleWatch({ ...deal, watching: before });
    } catch {
      setWatching(before);
    } finally {
      setWatchBusy(false);
    }
  };

  const currency = currencyCode(deal.currency);
  const noOwner = open && (deal.deal_owner.state === "none" || deal.flags.includes("no_owner"));
  const closePassed = open && deal.flags.includes("close_passed");
  const hasSow = deal.sow_state !== "none";
  const hubspotHref = hubspotPortalId && deal.hubspot_deal_id ? hubspotDealUrl(hubspotPortalId, deal.hubspot_deal_id) : null;

  return (
    <>
      <header className="flex flex-col gap-2 pr-8">
        <p className={kickerClass}>Opportunity · quick preview</p>
        <SheetTitle>
          {/* The size sits on the inner span: the kit's cn() would merge it away against text-text. */}
          <span className="text-pageHeading">{deal.title}</span>
        </SheetTitle>
        <p className="flex flex-wrap items-center gap-2 text-secondary text-text-secondary">
          {deal.client.id && deal.client.name ? (
            <button
              type="button"
              onClick={() => onOpenClient({ id: deal.client.id!, name: deal.client.name! })}
              className="rounded-control text-left text-body text-text hover:underline focus-visible:outline-focus"
            >
              {deal.client.name}
              <Glyph>↗</Glyph>
            </button>
          ) : (
            <span className="text-body text-text-secondary">No client</span>
          )}
          <span aria-hidden="true">·</span>
          <BusinessUnitLine deal={deal} />
        </p>
        <p className="flex flex-wrap gap-2">
          <StageTag deal={deal} />
          {deal.pipeline_label ? <Tag>{deal.pipeline_label}</Tag> : null}
        </p>
      </header>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-4 border-y border-border py-4">
        <Fact label={currency ? `Deal value · ${currency}` : "Deal value"}>
          {fullMoney(deal.amount, { currency: deal.currency })}
        </Fact>
        <Fact label="Expected close">{calendarDate(deal.close_date, today)}</Fact>
        <Fact label="HubSpot deal owner">{ownerFullName(deal.deal_owner)}</Fact>
        <Fact label="Account owner">{ownerFullName(deal.account_owner)}</Fact>
        <Fact label="Created">{calendarDate(deal.created_date, today)}</Fact>
        <Fact label="Last activity">{calendarDate(deal.last_activity_date, today, "None recorded")}</Fact>
        <Fact label="HubSpot region">{deal.hubspot_region ?? "Not set"}</Fact>
        <Fact label="Business unit">{businessUnitFact(deal)}</Fact>
      </dl>

      {noOwner ? <Callout>The deal needs an owner in HubSpot. Its client account owner is a separate field.</Callout> : null}
      {closePassed ? <Callout>The expected close date has passed. Update it in HubSpot or move the deal.</Callout> : null}

      <section aria-labelledby={`na-${deal.id}`} className="flex flex-col gap-3">
        <h3 id={`na-${deal.id}`} className="text-section text-text">
          Next action
        </h3>
        <NextActionSummary action={action} open={open} today={today} />
        {open ? (
          <NextActionEditor
            dealId={deal.id}
            current={action}
            assigneeId={assigneeId}
            onSaved={(saved) => {
              setAction(saved);
              onChanged();
            }}
          />
        ) : null}
      </section>

      <section aria-labelledby={`sow-${deal.id}`} className="flex flex-col gap-3">
        <h3 id={`sow-${deal.id}`} className="text-section text-text">
          SOW &amp; agreement documents
        </h3>
        <p className="flex flex-wrap items-center gap-1">
          <AgreementTags agreements={deal.agreements} />
          <SowTag deal={deal} tone="progress" />
        </p>
        <p className="text-secondary text-text-secondary">
          NDA and MSA show the client's state: Client copy, Standard copy, Marked covered, Missing or Due at stage 2. A warning only; nothing is blocked. The SOW state is separate from the HubSpot sales stage.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button asChild>
            {hasSow ? (
              <Link to={`/sows/${encodeURIComponent(deal.id)}`}>
                Open SOW workspace
                <Glyph>→</Glyph>
              </Link>
            ) : (
              <Link
                to={`/sows/new?bindOppId=${encodeURIComponent(deal.id)}${deal.client.id ? `&bindClientId=${encodeURIComponent(deal.client.id)}` : ""}`}
              >
                Upload SOW
                <Glyph>→</Glyph>
              </Link>
            )}
          </Button>
          <Button variant="secondary" aria-pressed={watching} disabled={watchBusy} onClick={() => void toggleWatch()}>
            {watching ? (
              <>
                <Glyph before>★</Glyph>
                Watching
              </>
            ) : (
              <>
                <Glyph before>☆</Glyph>
                Watch deal
              </>
            )}
          </Button>
          {hubspotHref ? (
            <Button variant="secondary" asChild>
              <a href={hubspotHref} target="_blank" rel="noopener noreferrer">
                HubSpot
                <Glyph>↗</Glyph>
              </a>
            </Button>
          ) : null}
        </div>
      </section>
    </>
  );
}

function NextActionSummary({ action, open, today }: { action: ShownNextAction | null; open: boolean; today: string }) {
  if (action) {
    const overdue = open && action.due_on !== null && action.due_on < today;
    return (
      <p className="flex flex-col text-body text-text-secondary">
        <strong className="font-semibold text-text">{action.text}</strong>
        <span className={overdue ? "font-medium text-warning" : undefined}>
          {action.due_on
            ? `Due ${calendarDate(action.due_on, today)}${overdue ? " · overdue" : ""}`
            : "No due date."}
        </span>
      </p>
    );
  }
  return (
    <p className="text-body text-text-secondary">
      {open ? "No next action set for this deal." : "Deal is closed."}
    </p>
  );
}

export function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <dt className="text-secondary text-text-secondary">{label}</dt>
      <dd className="break-words text-body font-semibold text-text">{children}</dd>
    </div>
  );
}

export function Callout({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-control border border-border bg-warning-surface px-3 py-2 text-secondary text-warning">
      {children}
    </p>
  );
}
