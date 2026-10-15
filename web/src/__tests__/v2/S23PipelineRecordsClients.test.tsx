// S23-PL2 F9 · the Clients tab: columns, cells, flags only from matching open
// deals (B13), clients without matching deals, sorts, and names as text (F15).
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { ClientRow } from "../../api/pipelineWorkspace";
import { RecordsPanel, type RecordsPanelProps } from "../../pages/v2/pipeline/RecordsPanel";
import { INJECTION_TITLE, client, urlState, workspace } from "./S23PipelineRecordsFixtures";

function renderClients(rows: ClientRow[], overrides: Partial<RecordsPanelProps> = {}) {
  const props: RecordsPanelProps = {
    workspace: workspace({ rows, page: { number: 1, size: 25, total_rows: rows.length, total_value_usd: null } }),
    loading: false,
    error: null,
    state: urlState({ tab: "clients" }),
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

function rowOf(name: string): HTMLElement {
  const row = screen.getByRole("button", { name }).closest("tr");
  if (!row) throw new Error(`no row for ${name}`);
  return row as HTMLElement;
}

describe("clients list (F9)", () => {
  it("has the seven columns of the spec and no selection box", () => {
    renderClients([client()]);
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent?.trim())).toEqual([
      "Client",
      "Account owner",
      "Matching / open",
      "Matching value",
      "Agreements",
      "Attention",
      "Last activity",
    ]);
    expect(screen.queryByRole("checkbox", { name: "Select current page" })).not.toBeInTheDocument();
  });

  it("shows a client row: mark, open deals, owner, matching / open, value, agreements, no flags, activity", () => {
    renderClients([client()]);
    const row = within(rowOf("Bramble Bank"));
    expect(row.getByText("BB")).toBeInTheDocument();
    expect(row.getByText("2 open deals")).toBeInTheDocument();
    expect(row.getByText("Srikanth")).toBeInTheDocument();
    expect(row.getByText("2")).toBeInTheDocument();
    expect(row.getByText("/ 2")).toBeInTheDocument();
    expect(row.getByText("$665.5k")).toBeInTheDocument();
    expect(row.getByText("USD · unweighted")).toBeInTheDocument();
    expect(row.getByText("NDA on file")).toBeInTheDocument();
    expect(row.getByText("MSA on file")).toBeInTheDocument();
    expect(row.getByText("No flags")).toBeInTheDocument();
    expect(row.getByText("Oct 8")).toBeInTheDocument();
    expect(row.getByText("6 days ago")).toBeInTheDocument();
    expect(row.getByRole("button", { name: "Preview Bramble Bank" })).toHaveTextContent("Preview →");
  });

  it("joins the flags of the client's matching open deals in amber, and says when the owner is missing", () => {
    renderClients([
      client({
        name: "Northstar Industries",
        account_owner: { name: null, state: "none" },
        open_deals: 1,
        matching_deals: 1,
        flags: ["no_owner", "action_overdue", "close_passed"],
        agreements: { nda_on_file: false, msa_on_file: false },
        days_since_activity: 1,
      }),
    ]);
    const row = within(rowOf("Northstar Industries"));
    const flags = row.getByText("Deal owner missing · Overdue next action · Close date passed");
    expect(flags.className).toContain("text-warning");
    expect(row.getByText("Not assigned").className).toContain("bg-warning-surface");
    expect(row.getByText("1 open deal")).toBeInTheDocument();
    expect(row.getByText("1 day ago")).toBeInTheDocument();
    expect(row.getByText("NDA missing")).toBeInTheDocument();
    expect(row.getByText("MSA missing")).toBeInTheDocument();
  });

  it("shows a client without matching deals (include unmatched): zeros as counts, reasons for the rest", () => {
    renderClients([
      client({
        name: "Sapphire Foods",
        matching_deals: 0,
        open_deals: 0,
        matching_value_usd: null,
        earliest_close_date: null,
        last_activity_date: null,
        days_since_activity: null,
        flags: [],
      }),
    ]);
    const row = within(rowOf("Sapphire Foods"));
    expect(row.getByText("0 open deals")).toBeInTheDocument();
    expect(row.getByText("0")).toBeInTheDocument();
    expect(row.getByText("/ 0")).toBeInTheDocument();
    expect(row.getByText("No matching deals")).toBeInTheDocument();
    expect(row.queryByText("USD · unweighted")).not.toBeInTheDocument();
    expect(row.getByText("No matching activity")).toBeInTheDocument();
    expect(row.getByText("No flags")).toBeInTheDocument();
  });

  it("shows 'Former HubSpot user' for an archived account owner", () => {
    renderClients([client({ name: "Old Owner Co", account_owner: { name: null, state: "archived" } })]);
    expect(within(rowOf("Old Owner Co")).getByText("Former HubSpot user")).toBeInTheDocument();
  });

  it("opens the client preview from the name and from 'Preview →'", () => {
    const c = client();
    const props = renderClients([c]);
    fireEvent.click(screen.getByRole("button", { name: "Bramble Bank" }));
    fireEvent.click(screen.getByRole("button", { name: "Preview Bramble Bank" }));
    // The row's own facts go to the preview (a client without HubSpot deals has no deal to read them from).
    const ref = { id: c.id, name: "Bramble Bank", facts: { account_owner: c.account_owner, agreements: c.agreements } };
    expect(props.onOpenClient).toHaveBeenNthCalledWith(1, ref);
    expect(props.onOpenClient).toHaveBeenNthCalledWith(2, ref);
  });

  it("sorts the clients with the same four sorts", () => {
    const state = urlState({ tab: "clients", page: 2 });
    const props = renderClients([client()], { state });
    fireEvent.change(screen.getByRole("combobox", { name: "Sort records" }), { target: { value: "close" } });
    expect(props.onStateChange).toHaveBeenCalledWith({ ...state, query: { ...state.query, sort: "close", page: 1 } });
  });

  it("ticks 'Include clients without matching deals' when the filter is on and unticks it", () => {
    const state = urlState({ tab: "clients", include_unmatched_clients: true });
    const props = renderClients([client()], { state });
    const box = screen.getByRole("checkbox", { name: "Include clients without matching deals" });
    expect(box).toHaveAttribute("aria-checked", "true");
    fireEvent.click(box);
    expect(props.onStateChange).toHaveBeenCalledWith({
      ...state,
      query: { ...state.query, include_unmatched_clients: false, page: 1 },
    });
  });

  it("renders a client name with HTML in it as text (F15)", () => {
    renderClients([client({ name: INJECTION_TITLE })]);
    expect(screen.getByRole("button", { name: INJECTION_TITLE })).toHaveTextContent(INJECTION_TITLE);
    expect(document.querySelector("img")).toBeNull();
  });
});
