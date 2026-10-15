// S23-PL2 F10 · the board: lanes in stage order with at most 6 cards and
// "Show all N in list →"; the clients "Cards" layout.
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { BoardLane, DealRow } from "../../api/pipelineWorkspace";
import { RecordsPanel, type RecordsPanelProps } from "../../pages/v2/pipeline/RecordsPanel";
import { client, deal, urlState, workspace } from "./S23PipelineRecordsFixtures";

function lane(stageId: number, label: string, total: number, value: string, count = Math.min(total, 6)): BoardLane {
  return {
    total,
    value_usd: value,
    deals: Array.from({ length: count }, (_, i) =>
      deal({ title: `${label} deal ${i + 1}`, stage_id: stageId, stage_label: label }),
    ),
  };
}

function renderBoard(rowsByStage: Record<string, BoardLane> | null, overrides: Partial<RecordsPanelProps> = {}) {
  const props: RecordsPanelProps = {
    workspace: workspace({
      rows: [],
      rows_by_stage: rowsByStage,
      page: { number: 1, size: 25, total_rows: 109, total_value_usd: "21596444.14" },
    }),
    loading: false,
    error: null,
    state: urlState({ layout: "board" }),
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
  render(
    <MemoryRouter>
      <RecordsPanel {...props} />
    </MemoryRouter>,
  );
  return props;
}

const laneOf = (name: string) => screen.getByRole("region", { name });

describe("opportunities board (F10)", () => {
  it("draws lanes in stage order with count and short money, and at most 6 cards", () => {
    renderBoard({
      "9": lane(9, "On hold", 2, "344500"),
      "1": lane(1, "Prospecting", 22, "3950000"),
      "2": lane(2, "Qualification", 4, "1200000"),
    });
    const lanes = screen.getAllByRole("region").filter((r) => r.getAttribute("aria-label") !== "Pipeline records");
    expect(lanes.map((l) => l.getAttribute("aria-label"))).toEqual(["Prospecting", "Qualification", "On hold"]);
    const prospecting = within(laneOf("Prospecting"));
    expect(prospecting.getByText("22 · $3.95m")).toBeInTheDocument();
    expect(prospecting.getAllByRole("article")).toHaveLength(6);
    expect(within(laneOf("On hold")).getByText("2 · $344.5k")).toBeInTheDocument();
  });

  it("shows a card amount with no currency without '$'; the lane's USD total keeps it", () => {
    const unpriced = deal({
      title: "Unpriced rollout",
      stage_id: 1,
      stage_label: "Prospecting",
      amount: "542000",
      currency: null,
    });
    renderBoard({ "1": { total: 1, value_usd: "0", deals: [unpriced] } });
    const prospecting = within(laneOf("Prospecting"));
    expect(prospecting.getByText("542k · no currency")).toBeInTheDocument();
    expect(prospecting.getByText("1 · $0")).toBeInTheDocument();
  });

  it("links a lane with more than 6 deals to the list of that stage", () => {
    const props = renderBoard({ "1": lane(1, "Prospecting", 22, "3950000"), "2": lane(2, "Qualification", 4, "1") });
    const more = within(laneOf("Prospecting")).getByRole("button", { name: "Show all 22 in list" });
    expect(more).toHaveTextContent("Show all 22 in list →");
    fireEvent.click(more);
    expect(props.onShowStageInList).toHaveBeenCalledWith(1);
    expect(within(laneOf("Qualification")).queryByRole("button", { name: /Show all/ })).not.toBeInTheDocument();
  });

  it("never draws more than 6 cards even if a lane carries more", () => {
    renderBoard({ "1": lane(1, "Prospecting", 7, "1", 7) });
    expect(within(laneOf("Prospecting")).getAllByRole("article")).toHaveLength(6);
    expect(screen.getByRole("button", { name: "Show all 7 in list" })).toBeInTheDocument();
  });

  it("shows a card: client, title, money, business unit, close and SOW, flags, owner and star", async () => {
    const d: DealRow = deal({
      title: "Managed services renewal",
      client: { id: "c-copper", name: "Copper Systems" },
      stage_id: 1,
      stage_label: "Prospecting",
      amount: "538000",
      business_unit: "Retro Rabbit",
      region: "South Africa",
      hubspot_region: "South Africa",
      deal_owner: { name: "Janice Krpan", state: "active" },
      close_date: "2027-02-17",
      sow_state: "draft",
      sow_state_label: "Draft",
      sow_count: 2,
      watching: true,
    });
    const props = renderBoard({ "1": { total: 1, value_usd: "538000", deals: [d] } });
    const card = within(screen.getByRole("article"));
    expect(card.getByText("Copper Systems")).toBeInTheDocument();
    expect(card.getByText("$538k")).toBeInTheDocument();
    expect(card.getByText("Retro Rabbit")).toBeInTheDocument();
    expect(card.getByText("· South Africa")).toBeInTheDocument();
    expect(card.getByText("Close Feb 17, 2027 · Draft +1 more")).toBeInTheDocument();
    expect(card.getByText("No flags")).toBeInTheDocument();
    expect(card.getByText("Janice")).toBeInTheDocument();
    fireEvent.click(card.getByRole("button", { name: "Managed services renewal" }));
    expect(props.onOpenDeal).toHaveBeenCalledWith(d);
    const star = card.getByRole("button", { name: "Stop watching Managed services renewal" });
    expect(star).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(star);
    expect(props.onToggleWatch).toHaveBeenCalledWith({ ...d, watching: true });
    expect(await card.findByRole("button", { name: "Watch Managed services renewal" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(card.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("summarises the board instead of paging it, with no page controls", () => {
    renderBoard({ "1": lane(1, "Prospecting", 22, "1"), "2": lane(2, "Qualification", 20, "1") });
    expect(screen.getByText("109 opportunities across 2 stages")).toBeInTheDocument();
    expect(screen.getByText("All filtered deals")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Rows" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Next page" })).not.toBeInTheDocument();
  });

  it("says when no opportunity matches", () => {
    renderBoard({}, {
      workspace: workspace({ rows: [], rows_by_stage: {}, page: { number: 1, size: 25, total_rows: 0, total_value_usd: "0" } }),
    });
    expect(screen.getByText("No matching opportunities.")).toBeInTheDocument();
  });

  it("waits for board data instead of drawing list rows as lanes", () => {
    renderBoard(null, { workspace: workspace({ rows: [deal()] }), loading: true });
    expect(screen.getByText("Loading opportunities…")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cloud modernization" })).not.toBeInTheDocument();
  });
});

describe("clients cards (F10)", () => {
  function renderCards(rows = [client()], overrides: Partial<RecordsPanelProps> = {}) {
    return renderBoard(null, {
      state: urlState({ tab: "clients", layout: "board" }),
      workspace: workspace({ rows, page: { number: 1, size: 25, total_rows: rows.length, total_value_usd: null } }),
      ...overrides,
    });
  }

  it("shows a client card: mark and name, open deals, money and matching tag, agreements, owner, preview", () => {
    const c = client();
    const props = renderCards([c]);
    const card = within(screen.getByRole("article"));
    expect(card.getByText("BB")).toBeInTheDocument();
    expect(card.getByText("2 open deals")).toBeInTheDocument();
    expect(card.getByText("$665.5k")).toBeInTheDocument();
    expect(card.getByText("2 matching deals")).toBeInTheDocument();
    expect(card.getByText("NDA on file")).toBeInTheDocument();
    expect(card.getByText("MSA on file")).toBeInTheDocument();
    expect(card.getByText("Srikanth")).toBeInTheDocument();
    fireEvent.click(card.getByRole("button", { name: "Bramble Bank" }));
    fireEvent.click(card.getByRole("button", { name: "Preview Bramble Bank" }));
    expect(props.onOpenClient).toHaveBeenCalledTimes(2);
    // The card's own facts go to the preview (a client without HubSpot deals has no deal to read them from).
    expect(props.onOpenClient).toHaveBeenCalledWith({
      id: c.id,
      name: "Bramble Bank",
      facts: { account_owner: c.account_owner, agreements: c.agreements },
    });
    expect(screen.getByText("1–1 of 1 client")).toBeInTheDocument();
  });

  it("says 'No matches' for a client without matching deals", () => {
    renderCards([client({ name: "Sapphire Foods", matching_deals: 0, open_deals: 0, matching_value_usd: null })]);
    const card = within(screen.getByRole("article"));
    expect(card.getByText("No matches")).toBeInTheDocument();
    expect(card.getByText("0 matching deals")).toBeInTheDocument();
    expect(card.getByText("0 open deals")).toBeInTheDocument();
  });

  it("says when no client matches", () => {
    renderCards([]);
    expect(screen.getByText("No matching clients.")).toBeInTheDocument();
  });
});
