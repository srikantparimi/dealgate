// S24-AG1 F1/B3 · the six cards. Label, value and note are the server's
// (computed over ALL clients, ignoring the filters); a click resets the filters
// and applies the card's drill, so the Clients list has exactly the card's
// number. "Needs attention" reads red above zero and green at zero.
import type { Card } from "../../../api/agreements";
import { cn } from "../../../lib/cn";

export interface AgreementMetricCardsProps {
  cards: Card[];
  onDrill: (card: Card) => void;
}

function valueClass(card: Card): string {
  if (card.key !== "needs_attention") return "text-text";
  return card.value > 0 ? "text-danger" : "text-success";
}

export function AgreementMetricCards({ cards, onDrill }: AgreementMetricCardsProps) {
  return (
    <section aria-label="Agreement summary" className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
      {cards.map((card) => (
        <button
          key={card.key}
          type="button"
          data-card={card.key}
          onClick={() => onDrill(card)}
          className="flex min-w-0 flex-col gap-2 rounded-card border border-border bg-surface p-4 text-left transition-motion hover:border-primary focus-visible:outline-focus"
        >
          <span className="text-secondary text-text-secondary">{card.label}</span>
          <strong className={cn("tnum text-metric", valueClass(card))}>{card.value}</strong>
          <span className="text-secondary text-text-secondary [overflow-wrap:anywhere]">{card.note}</span>
        </button>
      ))}
    </section>
  );
}
