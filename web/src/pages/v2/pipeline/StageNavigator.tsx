// S23-PL2 F5 · the sales stage navigator: all nine stages, all-status counts
// (they ignore the status and stage filters and respect every other filter).
// Selecting the first stage switches status to All and remembers the old one;
// clearing the last stage restores it (setStages / toggleStage).
import type { StageCount } from "../../../api/pipelineWorkspace";
import { fullMoney, plural, shortMoney } from "./format";

const HOLD_STAGE = 9;
const CLOSED_WON_STAGE = 7;
const CLOSED_LOST_STAGE = 8;

function barFill(stageId: number): string {
  if (stageId === CLOSED_WON_STAGE) return "fill-success";
  if (stageId === CLOSED_LOST_STAGE) return "fill-danger";
  if (stageId === HOLD_STAGE) return "fill-warning";
  return "fill-primary";
}

export interface StageNavigatorProps {
  stages: StageCount[];
  selected: number[];
  onToggle: (stageId: number) => void;
}

export function StageNavigator({ stages, selected, onToggle }: StageNavigatorProps) {
  const max = Math.max(1, ...stages.map((s) => Number(s.known_value_usd) || 0));
  return (
    <section aria-label="HubSpot sales stages" className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-label uppercase text-text-secondary">Sales stage navigator</h2>
        <p className="text-secondary text-text-secondary">All-status overview · select stages to filter in place</p>
      </div>
      <div className="grid grid-cols-3 gap-2 md:grid-cols-5 xl:grid-cols-9">
        {stages.map((stage) => {
          const on = selected.includes(stage.stage_id);
          const value = Number(stage.known_value_usd) || 0;
          const pct = Math.max(0, Math.min(100, (value / max) * 100));
          const label = `${stage.full_label}: ${stage.deals} ${plural(stage.deals, "deal", "deals")}, ${fullMoney(stage.known_value_usd)} known value`;
          return (
            <button
              key={stage.stage_id}
              type="button"
              aria-pressed={on}
              aria-label={label}
              onClick={() => onToggle(stage.stage_id)}
              className={`flex min-w-0 flex-col gap-1 rounded-card border p-3 text-left transition-motion focus-visible:outline-focus ${
                on ? "border-primary bg-primary-subtle" : "border-border bg-surface hover:border-primary"
              } ${stage.deals === 0 && !on ? "opacity-60" : ""}`}
            >
              <span className="flex items-baseline gap-2">
                <span className="font-mono text-secondary text-text-secondary">
                  {stage.stage_id === HOLD_STAGE ? "HOLD" : String(stage.stage_id).padStart(2, "0")}
                </span>
                <strong className="font-mono text-section text-text">{stage.deals}</strong>
              </span>
              <span className="text-table text-text">{stage.label}</span>
              <span className="text-secondary text-text-secondary">
                {shortMoney(stage.known_value_usd)}
                {stage.deals_without_amount ? ` + ${stage.deals_without_amount} no amount` : ""}
              </span>
              <svg aria-hidden focusable="false" className="mt-1 h-[3px] w-full" preserveAspectRatio="none">
                <rect width="100%" height="100%" className="fill-border" />
                <rect width={`${pct}%`} height="100%" className={barFill(stage.stage_id)} />
              </svg>
            </button>
          );
        })}
      </div>
    </section>
  );
}
