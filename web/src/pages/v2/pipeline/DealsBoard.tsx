// S23-PL2 F10 · the Opportunities board (spec §5.1): one lane per stage that has
// a filtered deal, in stage order, at most 6 cards each by the current sort,
// and "Show all N in list →" when the lane holds more.
import type { BoardLane, DealRow, StageCount } from "../../../api/pipelineWorkspace";
import { EmptyState } from "../../../ui-v2/EmptyState";
import { linkButtonClass } from "./DealsTable";
import { calendarDate, shortMoney } from "./format";
import { BusinessUnitLine, DealFlags, Glyph, OwnerChip, WatchStar, isOpenDeal, sowMore } from "./tags";

export const LANE_CARD_LIMIT = 6;

export interface DealsBoardProps {
  lanes: Record<string, BoardLane>;
  stages: StageCount[];
  today: string;
  isWatching: (deal: DealRow) => boolean;
  isWatchBusy: (deal: DealRow) => boolean;
  onToggleWatch: (deal: DealRow) => void;
  onOpenDeal: (deal: DealRow) => void;
  onShowStageInList: (stageId: number) => void;
}

/** Stage ids of the lanes, in stage order. */
export function laneOrder(lanes: Record<string, BoardLane>): number[] {
  return Object.keys(lanes)
    .map(Number)
    .filter((id) => Number.isInteger(id))
    .sort((a, b) => a - b);
}

export function DealsBoard({
  lanes,
  stages,
  today,
  isWatching,
  isWatchBusy,
  onToggleWatch,
  onOpenDeal,
  onShowStageInList,
}: DealsBoardProps) {
  const order = laneOrder(lanes);
  if (!order.length) return <EmptyState className="m-4" title="No matching opportunities." />;
  return (
    <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3">
      {order.map((stageId) => {
        const lane = lanes[String(stageId)]!;
        const shown = lane.deals.slice(0, LANE_CARD_LIMIT);
        const name =
          stages.find((s) => s.stage_id === stageId)?.label ?? shown[0]?.stage_label ?? lane.deals[0]?.stage_label ?? "";
        return (
          <section
            key={stageId}
            aria-label={name}
            className="flex min-w-0 flex-col gap-3 rounded-card border border-border bg-surface-sunken p-3"
          >
            <header className="flex items-baseline justify-between gap-2">
              <h3 className="text-table font-semibold text-text">{name}</h3>
              <span className="font-mono text-secondary text-text-secondary tnum">
                {`${lane.total} · ${shortMoney(lane.value_usd)}`}
              </span>
            </header>
            {shown.map((deal) => (
              <DealCard
                key={deal.id}
                deal={deal}
                today={today}
                watching={isWatching(deal)}
                busy={isWatchBusy(deal)}
                onToggleWatch={onToggleWatch}
                onOpenDeal={onOpenDeal}
              />
            ))}
            {lane.total > shown.length ? (
              <button
                type="button"
                onClick={() => onShowStageInList(stageId)}
                className={`${linkButtonClass} self-center text-table font-semibold`}
              >
                {`Show all ${lane.total} in list`}
                <Glyph>→</Glyph>
              </button>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}

function DealCard({
  deal,
  today,
  watching,
  busy,
  onToggleWatch,
  onOpenDeal,
}: {
  deal: DealRow;
  today: string;
  watching: boolean;
  busy: boolean;
  onToggleWatch: (deal: DealRow) => void;
  onOpenDeal: (deal: DealRow) => void;
}) {
  const close = deal.close_date ? `Close ${calendarDate(deal.close_date, today)}` : "No close date";
  const more = deal.sow_count > 1 ? ` ${sowMore(deal.sow_count)}` : "";
  return (
    <article className="flex flex-col gap-2 rounded-card border border-border border-l-[3px] border-l-primary bg-surface p-3 hover:border-primary">
      <span className="text-secondary text-text-secondary">{deal.client.name ?? "No client"}</span>
      <button
        type="button"
        onClick={() => onOpenDeal(deal)}
        className="rounded-control text-left text-body font-semibold text-text hover:underline focus-visible:outline-focus"
      >
        {deal.title}
      </button>
      <span className="flex flex-wrap items-baseline justify-between gap-2">
        <strong className="font-mono text-body font-semibold text-text tnum">
          {shortMoney(deal.amount, { currency: deal.currency })}
        </strong>
        <BusinessUnitLine deal={deal} />
      </span>
      <span className="text-secondary text-text-secondary">{`${close} · ${deal.sow_state_label}${more}`}</span>
      <DealFlags deal={deal} />
      <span className="flex items-center justify-between gap-2">
        <OwnerChip owner={deal.deal_owner} warnWhenNone={isOpenDeal(deal)} />
        <WatchStar title={deal.title} watching={watching} busy={busy} onToggle={() => onToggleWatch(deal)} />
      </span>
    </article>
  );
}
