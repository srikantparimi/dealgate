/**
 * SOW approval preview — spec §5 item 4.
 *
 * Three lanes: Scope & GM, Functional review, CEO exception. Each lane
 * shows up to 3 cards; a "View all" tertiary link at the top of every
 * lane always opens the complete board at /sows.
 *
 * Card content mirrors the spec: client, engagement, value, margin,
 * agreement states, four functional review markers, accountable owner,
 * next action. Any field the API doesn't hydrate degrades to a labelled
 * "Unavailable" — the page never fabricates a value.
 */

import { Link } from "react-router-dom";
import { CheckCircle2, MinusCircle, XCircle } from "lucide-react";
import { cn } from "../../../lib/cn";
import { MoneyCell } from "../../../ui-v2/MoneyCell";
import { MarginCell } from "../../../ui-v2/MarginCell";
import { StatusBadge, type StatusTone } from "../../../ui-v2/StatusBadge";

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
  value: string | null; // pre-formatted money string
  margin: string | null; // pre-formatted percent string
  marginOutcome?: "pass" | "fail" | "unavailable";
  ndaLabel: string;
  ndaTone: StatusTone;
  msaLabel: string;
  msaTone: StatusTone;
  markers: FunctionalReviewMarkers;
  owner: string | null;
  nextAction: string | null;
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
}

const MARKER_ICON = {
  approved: CheckCircle2,
  pending: MinusCircle,
  rejected: XCircle,
};
const MARKER_TONE: Record<FunctionalReviewMarker, string> = {
  approved: "text-success",
  pending: "text-text-secondary",
  rejected: "text-danger",
};
const MARKER_LABEL: Record<FunctionalReviewMarker, string> = {
  approved: "approved",
  pending: "pending",
  rejected: "rejected",
};

function MarkerRow({ markers }: { markers: FunctionalReviewMarkers }) {
  const entries: Array<[keyof FunctionalReviewMarkers, string]> = [
    ["delivery", "Delivery"],
    ["hr", "HR"],
    ["finance", "Finance"],
    ["legal", "Legal"],
  ];
  return (
    <ul
      aria-label="Functional review markers"
      className="flex flex-wrap items-center gap-x-3 gap-y-1"
    >
      {entries.map(([key, label]) => {
        const status = markers[key];
        const Icon = MARKER_ICON[status];
        return (
          <li
            key={key}
            className={cn(
              "inline-flex items-center gap-1 text-secondary",
              MARKER_TONE[status],
            )}
            aria-label={`${label} ${MARKER_LABEL[status]}`}
          >
            <Icon className="h-3 w-3" aria-hidden />
            <span className="text-text-secondary">{label}</span>
          </li>
        );
      })}
    </ul>
  );
}

function LaneCard({ card }: { card: ApprovalCard }) {
  return (
    <Link
      to={card.href}
      className={cn(
        "flex flex-col gap-2 rounded-panel border border-divider bg-surface p-4",
        "transition-motion hover:border-primary/40 hover:shadow-menu",
        "focus-visible:outline-focus",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-body text-text font-medium truncate">
            {card.client}
          </p>
          <p className="text-secondary text-text-secondary">
            {card.engagement ?? "Engagement unknown"}
          </p>
        </div>
        <div className="text-right">
          <MoneyCell value={card.value} />
          <MarginCell
            value={card.margin}
            outcome={card.marginOutcome ?? (card.margin ? undefined : "unavailable")}
          />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge tone={card.ndaTone} label={`NDA: ${card.ndaLabel}`} />
        <StatusBadge tone={card.msaTone} label={`MSA: ${card.msaLabel}`} />
      </div>
      <MarkerRow markers={card.markers} />
      <div className="mt-1 flex flex-wrap justify-between gap-x-3 gap-y-1 text-secondary text-text-secondary">
        <span>Owner: {card.owner ?? "Unassigned"}</span>
        <span>{card.nextAction ?? "No next action"}</span>
      </div>
    </Link>
  );
}

export function ApprovalPreview({
  lanes,
  viewAllHref = "/sows",
}: ApprovalPreviewProps) {
  return (
    <section aria-label="SOW approval preview">
      <div className="mb-3 flex items-end justify-between gap-3">
        <h2 className="text-section text-text">SOW approval preview</h2>
        <Link
          to={viewAllHref}
          className="text-body text-primary hover:underline focus-visible:outline-focus"
        >
          View all stages
        </Link>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {lanes.map((lane) => (
          <section
            key={lane.id}
            className="flex flex-col gap-3 rounded-panel bg-canvas/40 p-3"
            aria-label={lane.title}
          >
            <div className="flex items-baseline justify-between gap-2 px-1">
              <h3 className="text-body text-text font-semibold">
                {lane.title}
              </h3>
              <Link
                to={viewAllHref}
                className="text-secondary text-primary hover:underline focus-visible:outline-focus"
              >
                View all
              </Link>
            </div>
            {lane.description ? (
              <p className="px-1 text-secondary text-text-secondary">
                {lane.description}
              </p>
            ) : null}
            {lane.cards.length === 0 ? (
              <div
                role="status"
                className={cn(
                  "rounded-panel border border-dashed border-divider bg-surface",
                  "p-4 text-secondary text-text-secondary text-center",
                )}
              >
                Nothing in this lane.
              </div>
            ) : (
              lane.cards.slice(0, 3).map((c) => <LaneCard key={c.id} card={c} />)
            )}
          </section>
        ))}
      </div>
    </section>
  );
}
