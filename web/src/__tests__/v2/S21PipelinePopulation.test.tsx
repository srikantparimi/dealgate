import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import * as api from "../../api/client";
import { PipelinePage } from "../../pages/v2/Pipeline";

const page = (total: number) => ({ items: [], total, page: 1, page_size: 25, meta: { stage_counts: [], unknown_bucket: 0 } });
const aggregate = (total: number) => ({ open_count: total, open_value_by_currency: {}, closing_this_month: 0, overdue_actions: 0, pending_approvals: 0, agreement_gaps: 0 });

beforeEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  vi.spyOn(api, "getPipelineFacets").mockResolvedValue({ owners: [], business_units: [] });
  vi.spyOn(api, "listTrackingGroups").mockResolvedValue({ items: [] } as never);
  vi.spyOn(api, "listSavedViews").mockResolvedValue({ items: [] } as never);
  vi.spyOn(api, "getUserPreference").mockResolvedValue(null);
  vi.spyOn(api, "putUserPreference").mockResolvedValue(undefined as never);
  vi.spyOn(api, "listWatchlist").mockResolvedValue({ items: [], counts: {} });
  vi.spyOn(api, "getSyncStatus").mockResolvedValue({ items: [] });
});

it("an older response cannot replace a newer zero selection", async () => {
  let finishOld!: (value: unknown) => void;
  const old = new Promise(resolve => { finishOld = resolve; });
  vi.spyOn(api, "listPipelineClients").mockImplementation(f => (f?.open_closed === "closed_lost" ? Promise.resolve(page(0)) : old) as never);
  vi.spyOn(api, "listPipelineOpportunities").mockImplementation(f => (f?.open_closed === "closed_lost" ? Promise.resolve(page(0)) : old) as never);
  vi.spyOn(api, "getPipelineSummary").mockResolvedValue(aggregate(0) as never);
  render(<MemoryRouter initialEntries={["/pipeline?open_closed=open"]}><PipelinePage /></MemoryRouter>);
  await waitFor(() => expect(api.listPipelineClients).toHaveBeenCalled());
  fireEvent.change(screen.getByTestId("filter-open-closed"), { target: { value: "closed_lost" } });
  await screen.findByRole("tab", { name: "Opportunities (0)" });
  await act(async () => finishOld(page(99)));
  expect(screen.getByRole("tab", { name: "Opportunities (0)" })).toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: "Opportunities (99)" })).not.toBeInTheDocument();
});

it("renders removable chips for each active filter", async () => {
  vi.spyOn(api, "listPipelineClients").mockResolvedValue(page(0) as never);
  vi.spyOn(api, "listPipelineOpportunities").mockResolvedValue(page(0) as never);
  vi.spyOn(api, "getPipelineSummary").mockResolvedValue(aggregate(0) as never);
  render(<MemoryRouter initialEntries={["/pipeline?open_closed=open&search=Target"]}><PipelinePage /></MemoryRouter>);
  const remove = await screen.findByRole("button", { name: "Remove Status: Open" });
  fireEvent.click(remove);
  await waitFor(() => expect(api.listPipelineClients).toHaveBeenLastCalledWith(expect.objectContaining({ search: "Target", open_closed: undefined })));
  expect(screen.getByRole("button", { name: "Remove Search: Target" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("checkbox", { name: "Show clients with no match" }));
  await waitFor(() => expect(api.listPipelineClients).toHaveBeenLastCalledWith(expect.objectContaining({ show_clients_without_matches: true, search: "Target" })));
});

it("Watching count follows current filters instead of the global open watch count", async () => {
  vi.mocked(api.listWatchlist).mockResolvedValue({ items: [], counts: { opportunity: 7 }, matching_deal_count: 7 });
  vi.spyOn(api, "listPipelineClients").mockResolvedValue(page(0) as never);
  vi.spyOn(api, "listPipelineOpportunities").mockImplementation(f => Promise.resolve(page(
    f?.watching ? (f.open_closed === "closed_lost" ? 2 : 0) : 10,
  )) as never);
  vi.spyOn(api, "getPipelineSummary").mockResolvedValue(aggregate(0) as never);
  render(<MemoryRouter initialEntries={["/pipeline?search=Target&open_closed=open"]}><PipelinePage /></MemoryRouter>);
  await screen.findByRole("checkbox", { name: "Watching (0)" });
  await waitFor(() => expect(api.listPipelineOpportunities).toHaveBeenCalledWith(expect.objectContaining({
    search: "Target", open_closed: "open", watching: true, page: 1, page_size: 25,
  })));
  fireEvent.change(screen.getByTestId("filter-open-closed"), { target: { value: "closed_lost" } });
  await screen.findByRole("checkbox", { name: "Watching (2)" });
});
