/**
 * SOW approval preview — DealGate v2.1 prototype (lines 201–216, 383–386,
 * 559).
 *
 * Three lanes shown from the six-lane SOW board (Scope & GM, Functional
 * review, CEO exception). Each `.lane` is a rounded canvas sitting on the
 * surface, containing a header with title/count and one or more `.sow`
 * cards that mirror the SOW board's structure (GM chip, NDA/MSA chip
 * pair, FunctionMark row, owner + next-action + age foot).
 */

import { Link } from "react-router-dom";
import { cn } from "../../../lib/cn";
import { StatusBadge, type StatusTone } from "../../../ui-v2/StatusBadge";
import {
  FunctionMarkRow,
  type FunctionState,
} from "../../../ui-v2/FunctionMark";
import { cardStripeClass, type CardStripeVariant } from "../../../ui-v2/CardStripe";

export type FunctionalReviewMarker = "approved" | "pending" | "rejected";

export interface FunctionalReviewMarkers {
  delivery: FunctionalReviewMarker;
  hr: FunctionalReviewMarker;
  finance: FunctionalReviewMarker;
  legal: FunctionalReviewMarker;
}

export interface ApprovalCard {
  id: string;
  href: string;
  client: string;
  engagement: string | null;
  value: string | null;
  margin: string | null;
  marginOutcome?: "pass" | "fail" | "unavailable";
  ndaLabel: string;
  ndaTone: StatusTone;
  msaLabel: string;
  msaTone: StatusTone;
  markers: FunctionalReviewMarkers;
  owner: string | null;
  nextAction: string | null;
  ageDays?: number | null;
  stripe?: CardStripeVariant;
}

export interface ApprovalLane {
  id: string;
  title: string;
  description?: string;
  cards: ApprovalCard[];
}

export interface ApprovalPreviewProps {
  lanes: ApprovalLane[];
  viewAllHref?: string;
  title?: string;
  caption?: string;
}

const MARKER_STATE: Record<FunctionalReviewMarker, FunctionState> = {
  approved: "ok",
  pending: "pending",
  rejected: "bad",
};

function marginTone(outcome?: "pass" | "fail" | "unavailable"): StatusTone {
  if (outcome === "pass") return "success";
  if (outcome === "fail") return "danger";
  return "neutral";
}

function SowMiniCard({ card }: { card: ApprovalCard }) {
  const states: Record<"D" | "H" | "F" | "L", FunctionState> = {
    D: MARKER_STATE[card.markers.delivery],
    H: MARKER_STATE[card.markers.hr],
    F: MARKER_STATE[card.markers.finance],
    L: MARKER_STATE[card.markers.legal],
  };
  const gmLabel = card.margin
    ? `${card.margin}${card.marginOutcome === "fail" ? " · below floor" : ""}`
    : "GM not built";
  const gmTone: StatusTone = card.margin ? marginTone(card.marginOutcome) : "neutral";

  return (
    <Link
      to={card.href}
      className={cn(
        "flex flex-col gap-[6px] rounded-[8px] border border-border bg-surface",
        "px-3 py-[10px] text-[13px] text-text",
        "transition-motion hover:border-borderStrong",
        "focus-visible:outline-focus",
        cardStripeClass(card.stripe),
      )}
      data-testid={`preview-sow-${card.id}`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-semibold text-text truncate">{card.client}</span>
        {card.value ? (
          <span className="tnum text-[12px] text-text-secondary">
            {card.value}
          </span>
        ) : null}
      </div>
      {card.engagement ? (
        <div className="text-[12px] text-text-secondary truncate">
          {card.engagement}
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-[4px]">
        <StatusBadge tone={gmTone} label={gmLabel} />
      </div>
      <div className="flex flex-wrap items-center gap-[4px]">
        <span className="text-[11px] text-text-muted">NDA</span>
        <StatusBadge tone={card.ndaTone} label={card.ndaLabel} />
        <span className="text-[11px] text-text-muted ml-1">MSA</span>
        <StatusBadge tone={card.msaTone} label={card.msaLabel} />
      </div>
      <FunctionMarkRow states={states} />
      <div className="mt-1 flex items-center justify-between text-[12px] text-text-muted">
        <span className="truncate">
          {card.owner ? `${card.owner} · ` : ""}
          {card.nextAction ?? "Awaiting next reviewer"}
        </span>
        {card.ageDays != null ? (
          <span className="tnum shrink-0">{card.ageDays}d</span>
        ) : null}
      </div>
    </Link>
  );
}

export function ApprovalPreview({
  lanes,
  viewAllHref = "/sows",
  title = "SOW approvals",
  caption,
}: ApprovalPreviewProps) {
  return (
    <section
      aria-label={title}
      className="rounded-card border border-border bg-surface"
    >
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-5 pt-4">
        <h2 className="text-section font-semibold text-text">{title}</h2>
        {caption ? (
          <span className="text-[12px] text-text-muted">{caption}</span>
        ) : null}
        <Link
          to={viewAllHref}
          className="ml-auto text-[13px] text-primaryText hover:underline focus-visible:outline-focus"
        >
          All stages →
        </Link>
      </header>
      <div className="grid gap-3 p-5 md:grid-cols-2 xl:grid-cols-3">
        {lanes.map((lane) => (
          <section
            key={lane.id}
            aria-label={lane.title}
            className="flex min-w-0 flex-col gap-2 rounded-[10px] bg-surface-sunken p-[10px]"
          >
            <div className="flex items-center justify-between px-1 text-[12px] font-semibold text-text-secondary">
              <span>{lane.title}</span>
              <span className="tnum">{lane.cards.length}</span>
            </div>
            {lane.cards.length === 0 ? (
              <div
                role="status"
                className={cn(
                  "rounded-[8px] border border-dashed border-borderStrong bg-surface",
                  "p-4 text-center text-[12px] text-text-muted",
                )}
              >
                Nothing at this gate
              </div>
            ) : (
              lane.cards.slice(0, 3).map((c) => <SowMiniCard key={c.id} card={c} />)
            )}
          </section>
        ))}
      </div>
    </section>
  );
}
