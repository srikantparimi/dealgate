// S23-PL2 F8/F9/F15 · the small display pieces the Pipeline's records share:
// stage, SOW, agreement and flag tags, business unit with its region, owner
// chips and the watch star. Every HubSpot-sourced value is a React text node.
// Colours map spec §16 onto the app's tokens: violet stage and pending tags →
// primary, green → success, amber → warning, red → danger.
import { Star } from "lucide-react";
import type { ReactNode } from "react";

import type { Agreements, ClientFlag, DealRow, Owner } from "../../../api/pipelineWorkspace";
import { cn } from "../../../lib/cn";
import { Badge } from "../../../ui-v2/primitives/badge";
import { initials, plural } from "./format";

type Tone = "neutral" | "success" | "warning" | "danger" | "progress";

/** A compact tag: the kit's Badge without the leading dot. `wrap` lets a long label wrap instead of widening its column. */
export function Tag({
  tone = "neutral",
  wrap = false,
  children,
  className,
}: {
  tone?: Tone;
  wrap?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Badge
      tone={tone}
      showDot={false}
      className={cn("h-auto min-h-[22px] py-[3px] leading-tight", wrap ? "whitespace-normal" : "whitespace-nowrap", className)}
    >
      {children}
    </Badge>
  );
}

/**
 * A decorative glyph (arrow, star, plus) that screen readers skip. It carries its own
 * no-break space, so an arrow never wraps onto a line of its own.
 */
export function Glyph({ children, before = false }: { children: string; before?: boolean }) {
  return <span aria-hidden="true">{before ? `${children}\u00a0` : `\u00a0${children}`}</span>;
}

// --- deal status -------------------------------------------------------------

export type DealStatus = "open" | "won" | "lost" | "hold";

/**
 * A row carries its stage, not its status. Closed won / Closed lost / Hold are
 * read from the stage label the API sends ("Closed won", "Closed lost", "On hold").
 */
/** The deal's status as the API computed it (never derived from the stage name). */
export function dealStatus(deal: Pick<DealRow, "status">): DealStatus {
  return deal.status;
}

/** Open means not closed won and not closed lost; Hold is open (B5). */
export function isOpenDeal(deal: Pick<DealRow, "status">): boolean {
  const status = dealStatus(deal);
  return status === "open" || status === "hold";
}

// --- stage ---------------------------------------------------------------------

const STAGE_TONE: Record<DealStatus, Tone> = { open: "progress", won: "success", lost: "danger", hold: "warning" };

/** "6 · Contracting" for an open stage; "Closed won", "Closed lost", "On hold" otherwise. */
export function stageText(deal: Pick<DealRow, "stage_id" | "stage_label" | "status">): string {
  return dealStatus(deal) === "open" && deal.stage_id !== null ? `${deal.stage_id} · ${deal.stage_label}` : deal.stage_label;
}

export function StageTag({ deal }: { deal: Pick<DealRow, "stage_id" | "stage_label" | "status"> }) {
  return (
    <Badge tone={STAGE_TONE[dealStatus(deal)]} className="whitespace-nowrap">
      {stageText(deal)}
    </Badge>
  );
}

/** Six segments: open stages fill up to their number, Closed won fills all, lost and hold none. */
export function StageProgress({ deal }: { deal: Pick<DealRow, "stage_id" | "stage_label" | "status"> }) {
  const status = dealStatus(deal);
  const filled = status === "won" ? 6 : status === "open" ? Math.min(Math.max(deal.stage_id ?? 0, 0), 6) : 0;
  return (
    <span aria-hidden="true" className="mt-2 flex gap-1">
      {[1, 2, 3, 4, 5, 6].map((i) => (
        <span
          key={i}
          className={cn(
            "h-[3px] w-4 rounded-chip",
            i <= filled ? (status === "won" ? "bg-success" : "bg-primary") : "bg-border",
          )}
        />
      ))}
    </span>
  );
}

// --- SOW and agreements -----------------------------------------------------

const PENDING_SOW = new Set(["in_review_delivery_hr", "in_review_finance_legal", "ceo_exception"]);

/** The SOW state tag, plus "+N more" when the deal has several SOWs (B6). */
export function SowTag({
  deal,
  tone,
}: {
  deal: Pick<DealRow, "sow_state" | "sow_state_label" | "sow_count">;
  /** The preview always shows the SOW state in the pending tone (spec §6.1). */
  tone?: Tone;
}) {
  const own: Tone = tone ?? (PENDING_SOW.has(deal.sow_state) ? "progress" : deal.sow_state === "signed" ? "success" : "neutral");
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <Tag tone={own} wrap>
        {deal.sow_state_label}
      </Tag>
      {deal.sow_count > 1 ? <span className="text-secondary text-text-secondary">{sowMore(deal.sow_count)}</span> : null}
    </span>
  );
}

export function sowMore(sowCount: number): string {
  return `+${sowCount - 1} more`;
}

export function AgreementTags({ agreements }: { agreements: Agreements }) {
  return (
    <span className="inline-flex flex-wrap gap-1">
      <Tag tone={agreements.nda_on_file ? "success" : "warning"}>
        {agreements.nda_on_file ? "NDA on file" : "NDA missing"}
      </Tag>
      <Tag tone={agreements.msa_on_file ? "success" : "warning"}>
        {agreements.msa_on_file ? "MSA on file" : "MSA missing"}
      </Tag>
    </span>
  );
}

/** "None on file", "NDA MSA", "NDA" or "MSA" (client preview). */
export function agreementFilesText(agreements: Agreements): string {
  const parts = [agreements.nda_on_file ? "NDA" : null, agreements.msa_on_file ? "MSA" : null].filter(Boolean);
  return parts.length ? parts.join(" ") : "None on file";
}

// --- business unit -------------------------------------------------------------

const BU_TEXT: Record<string, string> = {
  ST21: "text-success",
  "IT Avalon": "text-primaryText",
  "Retro Rabbit": "text-warning",
};

/** "IT Avalon · US · Staffing": a business unit is never shown without its region (D3). */
export function BusinessUnitLine({
  deal,
  withNote = true,
}: {
  deal: Pick<DealRow, "business_unit" | "region" | "region_note" | "hubspot_region" | "bu_unmapped">;
  withNote?: boolean;
}) {
  if (!deal.business_unit) {
    return (
      <Tag tone="warning" wrap>
        {unmappedText(deal.hubspot_region)}
      </Tag>
    );
  }
  const tail = [deal.region, withNote ? deal.region_note : null].filter(Boolean).join(" · ");
  return (
    <span className="inline-flex flex-wrap items-baseline gap-1 text-secondary">
      <span className={cn("font-semibold", BU_TEXT[deal.business_unit] ?? "text-text")}>{deal.business_unit}</span>
      {tail ? <span className="text-text-secondary">{`· ${tail}`}</span> : null}
    </span>
  );
}

function unmappedText(raw: string | null): string {
  return raw ? `Unmapped region · ${raw}` : "No HubSpot region";
}

/** The preview's "Business unit" fact: "IT Avalon · US", or "Unmapped · {raw}". */
export function businessUnitFact(
  deal: Pick<DealRow, "business_unit" | "region" | "hubspot_region">,
): string {
  if (deal.business_unit) return [deal.business_unit, deal.region].filter(Boolean).join(" · ");
  return deal.hubspot_region ? `Unmapped · ${deal.hubspot_region}` : "Not set";
}

// --- owners --------------------------------------------------------------------

export function Avatar({ name }: { name: string }) {
  return (
    <span
      aria-hidden="true"
      className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-avatar bg-primary-subtle text-[10px] font-semibold text-primaryText"
    >
      {initials(name)}
    </span>
  );
}

/**
 * Avatar and first name; "Former HubSpot user" for an archived owner; "Not assigned"
 * for none — in amber only where it is a problem (an open deal, or a client).
 */
export function OwnerChip({ owner, warnWhenNone = true }: { owner: Owner; warnWhenNone?: boolean }) {
  if (owner.state === "archived") return <Tag wrap>Former HubSpot user</Tag>;
  if (owner.state === "none" || !owner.name) {
    return <Tag tone={warnWhenNone ? "warning" : "neutral"}>Not assigned</Tag>;
  }
  return (
    <span className="inline-flex items-center gap-2 text-table text-text">
      <Avatar name={owner.name} />
      <span>{owner.name.split(/\s+/)[0]}</span>
    </span>
  );
}

/** Full owner name for the previews. */
export function ownerFullName(owner: Owner, none = "Not assigned"): string {
  if (owner.state === "archived") return "Former HubSpot user";
  if (owner.state === "none" || !owner.name) return none;
  return owner.name;
}

/** Two-letter company mark. */
export function CompanyMark({ name }: { name: string }) {
  return (
    <span
      aria-hidden="true"
      className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-control border border-border bg-surface-sunken text-[11px] font-semibold text-primaryText"
    >
      {initials(name)}
    </span>
  );
}

// --- flags ---------------------------------------------------------------------

/** "Action overdue", "Close date passed", "No deal owner", "{N}d inactive"; or "No flags". */
export function DealFlags({ deal }: { deal: Pick<DealRow, "flags" | "days_since_activity"> }) {
  const tags: ReactNode[] = [];
  if (deal.flags.includes("action_overdue")) tags.push(<Tag key="o" tone="warning">Action overdue</Tag>);
  if (deal.flags.includes("close_passed")) tags.push(<Tag key="c" tone="warning">Close date passed</Tag>);
  if (deal.flags.includes("no_owner")) tags.push(<Tag key="n" tone="warning">No deal owner</Tag>);
  if (deal.flags.includes("inactive_14d")) {
    tags.push(
      <Tag key="i">
        {deal.days_since_activity !== null ? `${deal.days_since_activity}d inactive` : "14d+ inactive"}
      </Tag>,
    );
  }
  if (!tags.length) return <span className="text-secondary text-text-secondary">No flags</span>;
  return <span className="inline-flex flex-wrap gap-1">{tags}</span>;
}

const CLIENT_FLAG_TEXT: [ClientFlag, string][] = [
  ["no_owner", "Deal owner missing"],
  ["action_overdue", "Overdue next action"],
  ["close_passed", "Close date passed"],
];

/** The Clients-tab attention line, from the client's matching open deals only (B13). */
export function ClientFlagsText({ flags }: { flags: ClientFlag[] }) {
  const text = CLIENT_FLAG_TEXT.filter(([flag]) => flags.includes(flag)).map(([, label]) => label);
  if (!text.length) return <span className="text-secondary text-text-secondary">No flags</span>;
  return <span className="text-secondary font-medium text-warning">{text.join(" · ")}</span>;
}

// --- counts ----------------------------------------------------------------------

export function openDealsText(n: number): string {
  return `${n} open ${plural(n, "deal", "deals")}`;
}

export function matchingDealsText(n: number): string {
  return `${n} matching ${plural(n, "deal", "deals")}`;
}

// --- watching --------------------------------------------------------------------

/** The row and card star: "Watch {title}" / "Stop watching {title}", aria-pressed. */
export function WatchStar({
  title,
  watching,
  busy,
  onToggle,
}: {
  title: string;
  watching: boolean;
  busy?: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={watching}
      aria-label={`${watching ? "Stop watching" : "Watch"} ${title}`}
      disabled={busy}
      onClick={onToggle}
      className={cn(
        "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-control transition-motion",
        "focus-visible:outline-focus disabled:opacity-60",
        watching ? "text-warning" : "text-text-secondary hover:text-text",
      )}
    >
      <Star className={cn("h-4 w-4", watching && "fill-current")} aria-hidden="true" />
    </button>
  );
}
