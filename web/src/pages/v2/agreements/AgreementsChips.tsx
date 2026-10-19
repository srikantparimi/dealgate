// S24-AG1 F1 · every active filter as a removable chip ("Needs attention ×",
// "ST21 · US ×", "Search: …"), then "Reset filters". Nothing shows when no
// filter is set (the prototype).
import { buildChips, type AgreementsUrlState } from "./agreementsState";

// A long search chip wraps instead of widening the page (no horizontal scroll at 375 px).
const CHIP_CLASS =
  "inline-flex min-h-7 max-w-full items-center gap-1 rounded-chip border border-transparent bg-primary-subtle px-2 py-0.5 text-left text-secondary text-primary-text [overflow-wrap:anywhere] hover:border-primary focus-visible:outline-focus";

export interface AgreementsChipsProps {
  state: AgreementsUrlState;
  onChange: (next: AgreementsUrlState) => void;
  onReset: () => void;
}

export function AgreementsChips({ state, onChange, onReset }: AgreementsChipsProps) {
  const chips = buildChips(state);
  if (!chips.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-2">
      {chips.map((chip) => (
        <button
          key={chip.key}
          type="button"
          aria-label={`Remove ${chip.text}`}
          onClick={() => onChange(chip.next)}
          className={CHIP_CLASS}
        >
          {chip.text}
          <span aria-hidden>×</span>
        </button>
      ))}
      <button
        type="button"
        onClick={onReset}
        className="h-7 rounded-control px-2 text-secondary text-text-secondary hover:text-text focus-visible:outline-focus"
      >
        Reset filters
      </button>
    </div>
  );
}
