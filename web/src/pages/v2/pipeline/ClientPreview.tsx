// S23-PL2 F11 · the client preview (spec §6.2): account owner, the client's open
// value and deal counts, agreement documents, and every linked opportunity with
// whether it matches the current view. Two workspace reads, both scoped to the
// client: every deal (any status), and the deals matching the page's filters.
// S24-AG1 F3 · the agreement documents are the shared client panel (section
// variant): the same states, warning and actions as the Agreements page.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  DEFAULT_WORKSPACE_QUERY,
  getWorkspace,
  workspaceParams,
  type ClientRow,
  type DealRow,
  type Owner,
  type Workspace,
} from "../../../api/pipelineWorkspace";
import { Button } from "../../../ui-v2/primitives/button";
import { Sheet, SheetContent, SheetTitle } from "../../../ui-v2/primitives/sheet";
import { ClientAgreementsPanel } from "../agreements/ClientAgreementsPanel";
import { Callout, Fact, kickerClass, previewSheetClass } from "./DealPreview";
import { linkButtonClass } from "./DealsTable";
import { fullMoney, shortMoney } from "./format";
import { Glyph, Tag, ownerFullName } from "./tags";
import type { WorkspaceUrlState } from "./workspaceState";

/** The client-level facts a Clients row shows; every deal row of the client carries them too. */
export type ClientFacts = Pick<ClientRow, "account_owner" | "agreements">;

/**
 * The client a preview opens. From the Clients list it carries the row's facts: a client with
 * no HubSpot deal (listed by "Include clients without matching deals") has no deal to read them from.
 */
export interface ClientRef {
  id: string;
  name: string;
  facts?: ClientFacts;
}

const NO_OWNER: Owner = { name: null, state: "none" };

export interface ClientPreviewProps {
  client: ClientRef | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  state: WorkspaceUrlState;
  today: string;
  onOpenDeal: (deal: DealRow) => void;
  /** "Show this client’s deals": the page resets the filters, status All, search = the client's name, Opportunities. */
  onShowClientDeals: (clientName: string) => void;
  /** After an agreement change in the panel (upload, mark, attach…): the page asks for the workspace again. */
  onChanged?: () => void;
}

/** Room for every deal of one client in one answer. */
const CLIENT_PAGE_SIZE = 100;

interface Loaded {
  all: Workspace;
  matching: Workspace;
}

export function ClientPreview({
  client,
  open,
  onOpenChange,
  state,
  onOpenDeal,
  onShowClientDeals,
  onChanged,
}: ClientPreviewProps) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const clientId = client?.id ?? null;
  const viewKey = workspaceParams(state.query).toString();

  useEffect(() => {
    if (!open || !clientId) return;
    const ctl = new AbortController();
    setLoaded(null);
    setError(null);
    Promise.all([
      getWorkspace(
        { ...DEFAULT_WORKSPACE_QUERY, client: clientId, status: "all", page_size: CLIENT_PAGE_SIZE },
        ctl.signal,
      ),
      getWorkspace(
        { ...state.query, client: clientId, tab: "deals", layout: "list", page: 1, page_size: CLIENT_PAGE_SIZE },
        ctl.signal,
      ),
    ])
      .then(([all, matching]) => {
        if (!ctl.signal.aborted) setLoaded({ all, matching });
      })
      .catch((err: unknown) => {
        if (ctl.signal.aborted) return;
        setError(err instanceof Error && err.message ? err.message : "Please try again.");
      });
    return () => ctl.abort();
    // `viewKey` stands for every field of the current view.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, clientId, viewKey]);

  return (
    <Sheet open={open && client !== null} onOpenChange={onOpenChange}>
      <SheetContent side="right" className={previewSheetClass} aria-describedby={undefined}>
        {client ? (
          <>
            <header className="flex flex-col gap-2 pr-8">
              <p className={kickerClass}>Client · relationship overview</p>
              <SheetTitle>
                {/* The size sits on the inner span: the kit's cn() would merge it away against text-text. */}
                <span className="text-pageHeading">{client.name}</span>
              </SheetTitle>
            </header>
            {error ? (
              <div role="alert" className="flex flex-col gap-1">
                <Callout>The client details could not load.</Callout>
                <p className="text-secondary text-text-secondary">{error}</p>
              </div>
            ) : !loaded ? (
              <p role="status" className="text-body text-text-secondary">
                Loading client details…
              </p>
            ) : (
              <ClientPreviewBody
                client={client}
                loaded={loaded}
                onOpenDeal={onOpenDeal}
                onShowClientDeals={onShowClientDeals}
                onChanged={onChanged}
              />
            )}
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

function ClientPreviewBody({
  client,
  loaded,
  onOpenDeal,
  onShowClientDeals,
  onChanged,
}: {
  client: ClientRef;
  loaded: Loaded;
  onOpenDeal: (deal: DealRow) => void;
  onShowClientDeals: (clientName: string) => void;
  onChanged?: () => void;
}) {
  const { all, matching } = loaded;
  const deals = all.rows as DealRow[];
  const matchingIds = new Set((matching.rows as DealRow[]).map((d) => d.id));
  // The account owner belongs to the client: every deal row of it carries it, and the Clients row
  // passes it for a client without deals. With neither, none is recorded.
  const first = deals[0] ?? null;
  const accountOwner = first?.account_owner ?? client.facts?.account_owner ?? NO_OWNER;
  const fullLabel = (stageId: number | null, fallback: string) =>
    all.stages.find((s) => s.stage_id === stageId)?.full_label ?? fallback;

  return (
    <>
      <p className="text-body text-text-secondary">{`Account owner: ${ownerFullName(accountOwner)}`}</p>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-4 border-y border-border py-4">
        <Fact label="All open deal value">{fullMoney(all.metrics.open_value_usd.value)}</Fact>
        <Fact label="Deals matching current filters">{String(matching.page.total_rows)}</Fact>
        <Fact label="Total open deals">{String(all.metrics.open_deals.value)}</Fact>
      </dl>

      <ClientAgreementsPanel clientId={client.id} variant="section" onChanged={onChanged} />

      <section className="flex flex-col gap-2">
        <h3 className="text-section text-text">{`All linked opportunities · ${all.page.total_rows}`}</h3>
        {deals.length ? (
          <ul className="flex flex-col">
            {deals.map((d) => {
              const matches = matchingIds.has(d.id);
              return (
                <li key={d.id} className="flex flex-col items-start gap-1 border-b border-border py-3 last:border-b-0">
                  <button
                    type="button"
                    onClick={() => onOpenDeal(d)}
                    className={`${linkButtonClass} text-body font-semibold`}
                  >
                    {d.title}
                    <Glyph>→</Glyph>
                  </button>
                  <span className="text-secondary text-text-secondary">
                    {`${fullLabel(d.stage_id, d.stage_label)} · ${shortMoney(d.amount, { currency: d.currency })} · ${ownerFullName(
                      d.deal_owner,
                      "Deal owner not assigned",
                    )}`}
                  </span>
                  <Tag tone={matches ? "success" : "neutral"}>
                    {matches ? "Matches current view" : "Outside current filters"}
                  </Tag>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-body text-text-secondary">No opportunities linked to this client.</p>
        )}
      </section>

      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={() => onShowClientDeals(client.name)}>
          Show this client’s deals
        </Button>
        <Button variant="secondary" asChild>
          <Link to={`/agreements?client_id=${encodeURIComponent(client.id)}`}>
            Agreement documents
            <Glyph>→</Glyph>
          </Link>
        </Button>
      </div>
    </>
  );
}
