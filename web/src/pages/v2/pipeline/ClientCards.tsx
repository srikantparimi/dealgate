// S23-PL2 F10 · the Clients "Cards" layout (spec §5.2): the same paged client
// rows as the list, drawn as a grid of cards.
import type { ClientRow } from "../../../api/pipelineWorkspace";
import { EmptyState } from "../../../ui-v2/EmptyState";
import type { ClientRef } from "./ClientPreview";
import { linkButtonClass } from "./DealsTable";
import { shortMoney } from "./format";
import { AgreementTags, CompanyMark, Glyph, OwnerChip, matchingDealsText, openDealsText } from "./tags";

export interface ClientCardsProps {
  rows: ClientRow[];
  /** Passes the row's facts, so the preview of a client without deals still shows them. */
  onOpenClient: (client: ClientRef) => void;
}

export function ClientCards({ rows, onOpenClient }: ClientCardsProps) {
  if (!rows.length) return <EmptyState className="m-4" title="No matching clients." />;
  return (
    <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3">
      {rows.map((c) => {
        const facts = { account_owner: c.account_owner, agreements: c.agreements };
        const open = () => onOpenClient({ id: c.id, name: c.name, facts });
        return (
          <article
            key={c.id}
            className="flex min-w-0 flex-col gap-3 rounded-card border border-border border-l-[3px] border-l-primary bg-surface p-4"
          >
            <span className="flex items-center gap-3">
              <CompanyMark name={c.name} />
              <button
                type="button"
                onClick={open}
                className="rounded-control text-left text-body font-semibold text-text hover:underline focus-visible:outline-focus"
              >
                {c.name}
              </button>
            </span>
            <span className="text-secondary text-text-secondary">{openDealsText(c.open_deals)}</span>
            <span className="flex flex-wrap items-baseline justify-between gap-2">
              <strong className="font-mono text-body font-semibold text-text tnum">
                {c.matching_deals === 0 ? "No matches" : shortMoney(c.matching_value_usd)}
              </strong>
              <span className="font-mono text-secondary text-text-secondary">{matchingDealsText(c.matching_deals)}</span>
            </span>
            <AgreementTags agreements={c.agreements} />
            <span className="flex items-center justify-between gap-2">
              <OwnerChip owner={c.account_owner} />
              <button
                type="button"
                onClick={open}
                aria-label={`Preview ${c.name}`}
                className={`${linkButtonClass} text-table font-semibold`}
              >
                Preview
                <Glyph>→</Glyph>
              </button>
            </span>
          </article>
        );
      })}
    </div>
  );
}
