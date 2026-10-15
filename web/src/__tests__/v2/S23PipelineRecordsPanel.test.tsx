// S23-PL2 records panel: tabs with counts, layout toggle, the records header
// (basis line, sort, include-unmatched), the unmapped-region note, empty and
// loading states, pagination (25/50/100 only), the bulk bar (F13) and the
// phone order of the work area (F16/F17).
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { DealRow, Workspace } from "../../api/pipelineWorkspace";
import { RecordsPanel, type RecordsPanelProps } from "../../pages/v2/pipeline/RecordsPanel";
import { client, deal, urlState, workspace } from "./S23PipelineRecordsFixtures";

function renderPanel(overrides: Partial<RecordsPanelProps> = {}) {
  const props: RecordsPanelProps = {
    workspace: workspace({ rows: [deal()] }),
    loading: false,
    error: null,
    state: urlState(),
    onStateChange: vi.fn(),
    onShowStageInList: vi.fn(),
    selected: new Set<string>(),
    onSelectedChange: vi.fn(),
    onOpenDeal: vi.fn(),
    onOpenClient: vi.fn(),
    onToggleWatch: vi.fn().mockResolvedValue(undefined),
    onWatchSelected: vi.fn().mockResolvedValue(undefined),
    onAddSelectedToGroup: vi.fn(),
    onOpenViewsPanel: vi.fn(),
    onResetFilters: vi.fn(),
    ...overrides,
  };
  const view = render(
    <MemoryRouter>
      <RecordsPanel {...props} />
    </MemoryRouter>,
  );
  return { props, ...view };
}

const manyDeals = (n: number): DealRow[] => Array.from({ length: n }, (_, i) => deal({ title: `Deal ${i + 1}` }));

describe("tabs and layout toggle", () => {
  it("shows both tabs with the counts of the current filters, the active one pressed", () => {
    renderPanel();
    const opps = screen.getByRole("button", { name: /^Opportunities/ });
    const clients = screen.getByRole("button", { name: /^Clients/ });
    expect(opps).toHaveTextContent("Opportunities 109");
    expect(clients).toHaveTextContent("Clients 55");
    expect(opps).toHaveAttribute("aria-pressed", "true");
    expect(clients).toHaveAttribute("aria-pressed", "false");
  });

  it("switches tab and goes back to page 1, keeping every filter", () => {
    const state = urlState({ page: 3, bu: ["ST21"], q: "bank" });
    const { props } = renderPanel({ state });
    fireEvent.click(screen.getByRole("button", { name: /^Clients/ }));
    expect(props.onStateChange).toHaveBeenCalledWith({
      ...state,
      query: { ...state.query, tab: "clients", page: 1 },
    });
  });

  it("toggles List / Board (Cards on the Clients tab) with aria-pressed and page 1", () => {
    const state = urlState({ page: 2 });
    const { props, unmount } = renderPanel({ state });
    expect(screen.getByRole("button", { name: "List" })).toHaveAttribute("aria-pressed", "true");
    const board = screen.getByRole("button", { name: "Board" });
    expect(board).toHaveAttribute("aria-pressed", "false");
    expect(board).toHaveTextContent("▦ Board");
    fireEvent.click(board);
    expect(props.onStateChange).toHaveBeenCalledWith({ ...state, query: { ...state.query, layout: "board", page: 1 } });
    unmount();

    renderPanel({ state: urlState({ tab: "clients" }), workspace: workspace({ rows: [client()] }) });
    expect(screen.getByRole("button", { name: "Cards" })).toHaveTextContent("▦ Cards");
    expect(screen.queryByRole("button", { name: "Board" })).not.toBeInTheDocument();
  });

  it("opens the views panel from the 'Views & groups' button, placed between the tabs and the layout toggle (spec §9)", () => {
    const { props } = renderPanel({ filterBar: <div>FILTER BAR SLOT</div> });
    const views = screen.getByRole("button", { name: "Views & groups" });
    fireEvent.click(views);
    expect(props.onOpenViewsPanel).toHaveBeenCalledTimes(1);
    const tabs = screen.getByRole("button", { name: /^Clients/ });
    const list = screen.getByRole("button", { name: "List" });
    const slot = screen.getByText("FILTER BAR SLOT");
    const sort = screen.getByRole("combobox", { name: "Sort records" });
    const follows = (a: Node, b: Node) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    expect(follows(tabs, views)).toBe(true);
    expect(follows(views, list)).toBe(true);
    expect(follows(list, slot)).toBe(true);
    expect(follows(slot, sort)).toBe(true);
  });

  it("is the 'Pipeline records' region", () => {
    renderPanel();
    expect(screen.getByRole("region", { name: "Pipeline records" })).toBeInTheDocument();
  });
});

describe("records header", () => {
  it("states the deals basis: count, short money, USD unweighted, same population as the cards", () => {
    renderPanel({
      workspace: workspace({
        rows: [deal()],
        page: { number: 1, size: 25, total_rows: 109, total_value_usd: "21596444.14" },
      }),
    });
    expect(
      screen.getByText("109 deals · $21.60m · USD, unweighted · same population as the cards above"),
    ).toBeInTheDocument();
  });

  it("uses the singular for one deal", () => {
    renderPanel({
      workspace: workspace({ rows: [deal()], page: { number: 1, size: 25, total_rows: 1, total_value_usd: "542000" } }),
    });
    expect(screen.getByText("1 deal · $542k · USD, unweighted · same population as the cards above")).toBeInTheDocument();
  });

  it("states the clients basis with matching deals", () => {
    renderPanel({
      state: urlState({ tab: "clients" }),
      workspace: workspace({ rows: [client()], page: { number: 1, size: 25, total_rows: 55, total_value_usd: null } }),
    });
    expect(screen.getByText("55 clients · 109 matching deals")).toBeInTheDocument();
  });

  it("offers exactly the four sorts and goes to page 1 on a change", () => {
    const state = urlState({ page: 4 });
    const { props } = renderPanel({ state });
    const sort = screen.getByRole("combobox", { name: "Sort records" });
    expect(Array.from((sort as HTMLSelectElement).options).map((o) => [o.value, o.textContent])).toEqual([
      ["value", "Value · highest first"],
      ["close", "Close date · soonest"],
      ["activity", "Activity · oldest first"],
      ["name", "Name · A–Z"],
    ]);
    expect(sort).toHaveValue("value");
    fireEvent.change(sort, { target: { value: "activity" } });
    expect(props.onStateChange).toHaveBeenCalledWith({ ...state, query: { ...state.query, sort: "activity", page: 1 } });
  });

  it("shows 'Include clients without matching deals' only on the Clients tab, as a filter change", () => {
    const { unmount } = renderPanel();
    expect(screen.queryByRole("checkbox", { name: "Include clients without matching deals" })).not.toBeInTheDocument();
    unmount();

    const state = urlState({ tab: "clients", page: 2 });
    const { props } = renderPanel({ state, workspace: workspace({ rows: [client()] }) });
    const box = screen.getByRole("checkbox", { name: "Include clients without matching deals" });
    expect(box).toHaveAttribute("aria-checked", "false");
    fireEvent.click(box);
    expect(props.onStateChange).toHaveBeenCalledWith({
      ...state,
      query: { ...state.query, include_unmatched_clients: true, page: 1 },
    });
  });

  it("links the unmapped-region note to Settings → Business units (F8)", () => {
    renderPanel({ workspace: workspace({ rows: [deal()], unmapped_regions: 3 }) });
    expect(
      screen.getByText((_, el) =>
        el?.tagName === "P" &&
        el.textContent === "3 deals have a HubSpot region with no business unit yet. Map it in Settings → Business units.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings → Business units" })).toHaveAttribute(
      "href",
      "/settings/business-units",
    );
  });

  it("uses the singular in the unmapped note and hides it when every region is mapped", () => {
    const { unmount } = renderPanel({ workspace: workspace({ rows: [deal()], unmapped_regions: 1 }) });
    expect(screen.getByText(/^1 deal has a HubSpot region with no business unit yet\./)).toBeInTheDocument();
    unmount();
    renderPanel({ workspace: workspace({ rows: [deal()], unmapped_regions: 0 }) });
    expect(screen.queryByRole("link", { name: "Settings → Business units" })).not.toBeInTheDocument();
  });
});

describe("empty, loading and error states", () => {
  it("says no records match and resets the filters from the link (spec L166)", () => {
    const { props } = renderPanel({
      workspace: workspace({ rows: [], page: { number: 1, size: 25, total_rows: 0, total_value_usd: "0" } }),
    });
    expect(screen.getByText("No records match this view.")).toBeInTheDocument();
    expect(screen.getByText("Remove a filter, change status, or reset the view.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(props.onResetFilters).toHaveBeenCalledTimes(1);
    expect(screen.getByText("0–0 of 0 opportunities")).toBeInTheDocument();
  });

  it("shows a loading line before the first answer", () => {
    renderPanel({ workspace: null, loading: true });
    expect(screen.getByRole("status")).toHaveTextContent("Loading opportunities…");
  });

  it("does not draw deal rows as clients while the Clients tab is loading", () => {
    renderPanel({ state: urlState({ tab: "clients" }), workspace: workspace({ rows: [deal()] }), loading: true });
    expect(screen.getByText("Loading clients…")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cloud modernization" })).not.toBeInTheDocument();
  });

  it("names the failure and offers a retry when the parent gives one", () => {
    const onRetry = vi.fn();
    renderPanel({ workspace: null, error: "API error 502", onRetry });
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("The records could not load.");
    expect(alert).toHaveTextContent("API error 502");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("moves back to the last page when the page is past the end, replacing the history entry", () => {
    const state = urlState({ page: 9 });
    const { props } = renderPanel({
      state,
      workspace: workspace({ rows: [], page: { number: 9, size: 25, total_rows: 30, total_value_usd: "1" } }),
    });
    // A correction, not a step the user took: Back must not return to the empty page.
    expect(props.onStateChange).toHaveBeenCalledTimes(1);
    expect(props.onStateChange).toHaveBeenCalledWith({ ...state, query: { ...state.query, page: 2 } }, { replace: true });
  });
});

describe("pagination (25 / 50 / 100 only)", () => {
  const ws = (page: number, size: 25 | 50 | 100 = 25): Workspace =>
    workspace({ rows: manyDeals(3), page: { number: page, size, total_rows: 109, total_value_usd: "21596444.14" } });

  it("shows the range, the page and offers only 25, 50 and 100 rows", () => {
    renderPanel({ workspace: ws(1) });
    expect(screen.getByText("1–25 of 109 opportunities")).toBeInTheDocument();
    expect(screen.getByText("1 / 5")).toBeInTheDocument();
    const rows = screen.getByRole("combobox", { name: "Rows" });
    expect(Array.from((rows as HTMLSelectElement).options).map((o) => o.value)).toEqual(["25", "50", "100"]);
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next page" })).toBeEnabled();
  });

  it("moves to the next page and keeps everything else", () => {
    const state = urlState();
    const { props } = renderPanel({ state, workspace: ws(1) });
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(props.onStateChange).toHaveBeenCalledWith({ ...state, query: { ...state.query, page: 2 } });
  });

  it("changes the page size and goes to page 1", () => {
    const state = urlState({ page: 3 });
    const { props } = renderPanel({ state, workspace: ws(3) });
    fireEvent.change(screen.getByRole("combobox", { name: "Rows" }), { target: { value: "50" } });
    expect(props.onStateChange).toHaveBeenCalledWith({ ...state, query: { ...state.query, page_size: 50, page: 1 } });
  });

  it("shows the last page with next disabled", () => {
    renderPanel({ state: urlState({ page: 5 }), workspace: ws(5) });
    expect(screen.getByText("101–109 of 109 opportunities")).toBeInTheDocument();
    expect(screen.getByText("5 / 5")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeEnabled();
  });

  it("counts clients on the Clients tab", () => {
    renderPanel({
      state: urlState({ tab: "clients", page_size: 50 }),
      workspace: workspace({ rows: [client()], page: { number: 1, size: 50, total_rows: 55, total_value_usd: null } }),
    });
    expect(screen.getByText("1–50 of 55 clients")).toBeInTheDocument();
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
  });
});

describe("bulk bar (F13)", () => {
  it("is absent without a selection", () => {
    renderPanel();
    expect(screen.queryByRole("button", { name: "Watch selected" })).not.toBeInTheDocument();
  });

  it("watches the selection, adds it to a group and clears it", async () => {
    const { props } = renderPanel({ selected: new Set(["a", "b", "c"]) });
    expect(screen.getByText("3 selected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Watch selected" })).toHaveTextContent("☆ Watch selected");
    expect(screen.getByRole("button", { name: "Add to group" })).toHaveTextContent("＋ Add to group");
    fireEvent.click(screen.getByRole("button", { name: "Watch selected" }));
    expect(props.onWatchSelected).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.getByRole("button", { name: "Watch selected" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Add to group" }));
    expect(props.onAddSelectedToGroup).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Clear selection" }));
    expect(props.onSelectedChange).toHaveBeenCalledWith(new Set());
  });
});
