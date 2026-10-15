// S23-PL2 F3 / B15 · the freshness line under the header. Three states with the
// prototype's copy: fresh (quiet), stale (warning) and failed (danger, naming
// the last good sync). Freshness comes from sync run records only, never the
// intake heartbeat; the state is the server's. Times in America/Los_Angeles.
import type { Freshness } from "../../../api/pipelineWorkspace";
import { hoursSince, pacificDateTime, plural } from "./format";

export interface FreshnessCopy {
  icon: string;
  strong: string;
  rest: string;
  link: string;
}

/** The line's words for a freshness state. */
export function freshnessCopy(f: Freshness, now: Date = new Date()): FreshnessCopy {
  const success = f.last_success_at ? pacificDateTime(f.last_success_at) : null;
  if (f.state === "failed") {
    return {
      icon: "◷",
      strong: f.last_attempt_at
        ? `The last sync failed (${pacificDateTime(f.last_attempt_at)}).`
        : "The last sync failed.",
      rest: success ? ` Showing deals from the last good sync, ${success}.` : " No successful deal sync is recorded yet.",
      link: "Inspect sync",
    };
  }
  const hours = hoursSince(f.last_success_at, now);
  if (f.state === "fresh" && success && hours !== null) {
    return {
      icon: "●",
      strong: `Deals synced ${success}`,
      rest: ` · ${hours} h ago · ${f.schedule} sync`,
      link: "Sync details",
    };
  }
  if (success && hours !== null) {
    const days = Math.max(1, Math.round(hours / 24));
    return {
      icon: "◷",
      strong: `Deal data is ${days} ${plural(days, "day", "days")} old.`,
      rest: ` Last successful sync ${success}. Check sync health before relying on these figures.`,
      link: "Inspect sync",
    };
  }
  return {
    icon: "◷",
    strong: "No successful deal sync is recorded yet.",
    rest: " Check sync health before relying on these figures.",
    link: "Inspect sync",
  };
}

const TONE: Record<Freshness["state"], string> = {
  fresh: "border-success text-text-secondary",
  stale: "border-warning text-warning",
  failed: "border-danger text-danger",
};

export interface FreshnessLineProps {
  freshness: Freshness;
  onInspect: () => void;
  now?: Date;
}

export function FreshnessLine({ freshness, onInspect, now }: FreshnessLineProps) {
  const copy = freshnessCopy(freshness, now);
  const quiet = freshness.state === "fresh";
  return (
    <div
      data-state={freshness.state}
      className={`flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-l-4 py-2 pl-3 text-table ${TONE[freshness.state]}`}
    >
      <p className="min-w-0">
        <span aria-hidden>{`${copy.icon} \u00a0`}</span>
        <strong className={quiet ? "font-semibold text-text" : "font-semibold"}>{copy.strong}</strong>
        {copy.rest}
      </p>
      <button
        type="button"
        aria-haspopup="dialog"
        onClick={onInspect}
        className={`rounded-control text-table font-semibold hover:underline focus-visible:outline-focus ${
          quiet ? "text-text-secondary" : ""
        }`}
      >
        {copy.link}
        {quiet ? null : <span aria-hidden> →</span>}
      </button>
    </div>
  );
}
