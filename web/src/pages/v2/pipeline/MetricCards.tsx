// S23-PL2 F4 / B7 · six metric cards. Every number is computed on the server
// over the current filters; a click adds the card's `drill` to the current
// filters (applyDrill), so the list it opens has exactly the card's number.
// S24-AG1 F6: "Agreement gaps" counts the clients that need attention on the
// NDA & MSA page (net new, past stage 1, NDA or MSA missing), with that page's note.
import type { MetricDrill, WorkspaceMetrics } from "../../../api/pipelineWorkspace";
import { plural, shortMoney } from "./format";

interface Card {
  key: keyof WorkspaceMetrics;
  label: string;
  value: string;
  note: string;
  drill: MetricDrill;
  accent?: boolean;
}

/** The gap card's note: the prototype's definition, the same words as the NDA & MSA page's card. */
export const AGREEMENT_GAP_NOTE = "Net new, past stage 1, NDA or MSA missing";

function cards(m: WorkspaceMetrics): Card[] {
  const gaps = m.agreement_gap_clients;
  return [
    {
      key: "open_deals",
      label: "Open deals",
      value: String(m.open_deals.value),
      note: `${m.open_deals.accounts} ${plural(m.open_deals.accounts, "account", "accounts")}`,
      drill: m.open_deals.drill,
    },
    {
      key: "open_value_usd",
      label: "Open value · USD",
      value: shortMoney(m.open_value_usd.value),
      note: m.open_value_usd.includes_on_hold
        ? `includes ${m.open_value_usd.includes_on_hold} on hold · unweighted`
        : "unweighted",
      drill: m.open_value_usd.drill,
      accent: true,
    },
    {
      key: "closing_this_month",
      label: "Closing this month",
      value: String(m.closing_this_month.value),
      note: `${shortMoney(m.closing_this_month.value_usd)} proposed value`,
      drill: m.closing_this_month.drill,
    },
    {
      key: "overdue_next_actions",
      label: "Overdue next actions",
      value: String(m.overdue_next_actions.value),
      note: m.overdue_next_actions.with_next_action
        ? `of ${m.overdue_next_actions.with_next_action} ${plural(m.overdue_next_actions.with_next_action, "deal", "deals")} with a next action`
        : "No deal has a next action yet",
      drill: m.overdue_next_actions.drill,
    },
    {
      key: "pending_approvals",
      label: "Pending approvals",
      value: String(m.pending_approvals.value),
      note: "Deals with a SOW in review or CEO exception",
      drill: m.pending_approvals.drill,
    },
    {
      key: "agreement_gap_clients",
      label: "Agreement gaps",
      value: String(gaps.value),
      note: AGREEMENT_GAP_NOTE,
      drill: gaps.drill,
    },
  ];
}

export interface MetricCardsProps {
  metrics: WorkspaceMetrics;
  onDrill: (drill: MetricDrill) => void;
}

export function MetricCards({ metrics, onDrill }: MetricCardsProps) {
  return (
    <section aria-label="Pipeline summary" className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-[1.2fr_1.5fr_1fr_1fr_1fr_1fr]">
      {cards(metrics).map((card) => (
        <button
          key={card.key}
          type="button"
          onClick={() => onDrill(card.drill)}
          className="flex min-w-0 flex-col gap-2 rounded-card border border-border bg-surface p-4 text-left transition-motion hover:border-primary focus-visible:outline-focus"
        >
          <span className="flex items-start justify-between gap-2 text-secondary text-text-secondary">
            {card.label}
            <span aria-hidden className="opacity-50">
              ↗
            </span>
          </span>
          <strong className={`tnum text-metric ${card.accent ? "text-primary-text" : "text-text"}`}>{card.value}</strong>
          <span className="text-secondary text-text-secondary">{card.note}</span>
        </button>
      ))}
    </section>
  );
}
