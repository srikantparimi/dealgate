// S23-PL2 L3 test seam · stand-ins for the records lane's components, so the
// page-shell tests exercise the page's state and wiring through the props the
// two lanes agreed (build-plan-web.md §3), independent of how the records draw.
import { useState } from "react";

import type { ClientPreviewProps } from "../../pages/v2/pipeline/ClientPreview";
import type { DealPreviewProps } from "../../pages/v2/pipeline/DealPreview";
import type { RecordsPanelProps } from "../../pages/v2/pipeline/RecordsPanel";
import { fakeDeal } from "./S23PipelineShellFixtures";

export function FakeRecordsPanel(props: RecordsPanelProps) {
  const { workspace, state, selected } = props;
  // How the page answered the last star click: the real star undoes itself on a rejection.
  const [watchOutcome, setWatchOutcome] = useState("");
  const q = state.query;
  const go = (patch: Partial<typeof q>) => props.onStateChange({ ...state, query: { ...q, ...patch } });
  return (
    <section aria-label="Pipeline records">
      {props.filterBar}
      <p data-testid="records-total">{workspace ? `${workspace.page.total_rows} rows` : "no rows yet"}</p>
      <p data-testid="records-tab">{q.tab}</p>
      <p data-testid="records-selected">{`${selected.size} selected`}</p>
      {props.error ? <p data-testid="records-error">{props.error}</p> : null}
      <button type="button" onClick={props.onOpenViewsPanel}>
        Views &amp; groups
      </button>
      <button type="button" onClick={() => props.onSelectedChange(new Set(["deal-1", "deal-2"]))}>
        fake: select two
      </button>
      <button type="button" onClick={props.onAddSelectedToGroup}>
        fake: add to group
      </button>
      <button type="button" onClick={() => void props.onWatchSelected()}>
        fake: watch selected
      </button>
      <button type="button" onClick={() => go({ page: q.page + 1 })}>
        fake: next page
      </button>
      <button type="button" onClick={() => go({ sort: "name", page: 1 })}>
        fake: sort by name
      </button>
      <button type="button" onClick={() => go({ tab: q.tab === "deals" ? "clients" : "deals", page: 1 })}>
        fake: switch tab
      </button>
      <button type="button" onClick={props.onResetFilters}>
        fake: reset filters
      </button>
      <button type="button" onClick={() => props.onShowStageInList(1)}>
        fake: show stage 1 in list
      </button>
      <button type="button" onClick={() => props.onOpenDeal(fakeDeal())}>
        fake: open deal
      </button>
      <p data-testid="watch-outcome">{watchOutcome}</p>
      <button
        type="button"
        onClick={() =>
          props.onToggleWatch(fakeDeal()).then(
            () => setWatchOutcome("resolved"),
            () => setWatchOutcome("rejected"),
          )
        }
      >
        fake: watch deal
      </button>
    </section>
  );
}

export function FakeDealPreview(props: DealPreviewProps) {
  if (!props.open || !props.deal) return null;
  return (
    <div data-testid="deal-preview">
      <p>{props.deal.title}</p>
      <p data-testid="deal-preview-watching">{props.deal.watching ? "watching" : "not watching"}</p>
      <p data-testid="deal-preview-assignee">{props.assigneeId ?? "no assignee"}</p>
      <button type="button" onClick={() => props.onOpenClient({ id: props.deal!.client.id!, name: props.deal!.client.name! })}>
        fake: open client
      </button>
    </div>
  );
}

export function FakeClientPreview(props: ClientPreviewProps) {
  if (!props.open || !props.client) return null;
  return (
    <div data-testid="client-preview">
      <p>{props.client.name}</p>
      <button type="button" onClick={() => props.onShowClientDeals(props.client!.name)}>
        fake: show this client’s deals
      </button>
    </div>
  );
}
