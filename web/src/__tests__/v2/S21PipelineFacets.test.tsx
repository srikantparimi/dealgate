import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import * as api from "../../api/client";
import { PipelinePage } from "../../pages/v2/Pipeline";

beforeEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  const page = { items: [], total: 0, page: 1, page_size: 25, meta: { stage_counts: [], unknown_bucket: 0 } };
  vi.spyOn(api, "listPipelineClients").mockResolvedValue(page as never);
  vi.spyOn(api, "listPipelineOpportunities").mockResolvedValue(page as never);
  vi.spyOn(api, "getPipelineSummary").mockResolvedValue({ open_count: 0, open_value_by_currency: {},
    closing_this_month: 0, overdue_actions: 0, pending_approvals: 0, agreement_gaps: 0 } as never);
  vi.spyOn(api, "listTrackingGroups").mockResolvedValue({ items: [] } as never);
  vi.spyOn(api, "listSavedViews").mockResolvedValue({ items: [] } as never);
  vi.spyOn(api, "getUserPreference").mockResolvedValue(null);
  vi.spyOn(api, "listWatchlist").mockResolvedValue({ items: [], counts: {} });
  vi.spyOn(api, "getSyncStatus").mockResolvedValue({ items: [] });
});

it("requests facets with the identical active query as rows and refreshes on filter changes", async () => {
  vi.spyOn(api, "getPipelineFacets").mockResolvedValue({ owners: [], business_units: ["east"] });
  render(<MemoryRouter initialEntries={["/pipeline?pipeline=p&stage=a&stage=b&business_unit=east&group=g&watching=true&client=c"]}>
    <PipelinePage />
  </MemoryRouter>);
  await waitFor(() => expect(api.getPipelineFacets).toHaveBeenCalledWith(expect.objectContaining({
    pipeline: "p", stage: ["a", "b"], business_unit: ["east"], group: ["g"], watching: true, client: ["c"],
  })));
  expect(vi.mocked(api.getPipelineFacets).mock.lastCall?.[0]).toEqual(vi.mocked(api.listPipelineClients).mock.lastCall?.[0]);
  fireEvent.change(screen.getByTestId("filter-open-closed"), { target: { value: "closed_lost" } });
  await waitFor(() => expect(api.getPipelineFacets).toHaveBeenLastCalledWith(expect.objectContaining({ open_closed: "closed_lost", client: ["c"] })));
});

it("an older facet response cannot replace a newer empty population", async () => {
  let finish!: (value: api.PipelineFacets) => void;
  const old = new Promise<api.PipelineFacets>(resolve => { finish = resolve; });
  vi.spyOn(api, "getPipelineFacets").mockImplementation(filters => filters?.open_closed === "closed_lost"
    ? Promise.resolve({ owners: [], business_units: [] }) : old);
  render(<MemoryRouter initialEntries={["/pipeline?open_closed=open"]}><PipelinePage /></MemoryRouter>);
  await waitFor(() => expect(api.getPipelineFacets).toHaveBeenCalled());
  fireEvent.change(screen.getByTestId("filter-open-closed"), { target: { value: "closed_lost" } });
  await waitFor(() => expect(api.getPipelineFacets).toHaveBeenCalledTimes(2));
  await act(async () => finish({ owners: [], business_units: ["stale-east"] }));
  expect(screen.queryByRole("option", { name: "stale-east" })).not.toBeInTheDocument();
  expect(screen.getByTestId("filter-business-unit")).toBeDisabled();
});

it("serializes repeated facet filters with the shared request query contract", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ owners: [], business_units: [] }),
    { status: 200, headers: { "Content-Type": "application/json" } }));
  await api.getPipelineFacets({ stage: ["a", "b"], business_unit: ["east"], group: ["group-id"], watching: true, search: "A & B" });
  const url = new URL(String(fetch.mock.calls[0][0]), "http://localhost");
  expect(url.pathname).toContain("/pipeline/facets");
  expect(url.searchParams.getAll("stage")).toEqual(["a", "b"]);
  expect(url.searchParams.get("business_unit")).toBe("east");
  expect(url.searchParams.get("group")).toBe("group-id");
  expect(url.searchParams.get("watching")).toBe("true");
  expect(url.searchParams.get("search")).toBe("A & B");
});

it("applying a saved view replaces stale filters rather than intersecting them", async () => {
  vi.spyOn(api, "getPipelineFacets").mockResolvedValue({ owners: [], business_units: [] });
  vi.mocked(api.listSavedViews).mockResolvedValue({ items: [{ id: "saved-stage", name: "Qualified only", filter_json: { stage: ["qualified"] }, sort_json: { column: "client_name", descending: false } }] } as never);
  vi.spyOn(api, "putUserPreference").mockResolvedValue({} as never);
  render(<MemoryRouter initialEntries={["/pipeline?owner=old-owner&business_unit=old-bu&search=old-search&page_size=50"]}><PipelinePage /></MemoryRouter>);
  await screen.findByRole("option", { name: "Qualified only" });
  fireEvent.change(screen.getByTestId("filter-saved-view"), { target: { value: "saved-stage" } });
  await waitFor(() => expect(api.listPipelineClients).toHaveBeenLastCalledWith(expect.objectContaining({ stage: ["qualified"], sort: "client_name", page: 1, page_size: 50 })));
  const filters = vi.mocked(api.listPipelineClients).mock.lastCall?.[0];
  expect(filters?.owner).toEqual([]);
  expect(filters?.business_unit).toEqual([]);
  expect(filters?.search).toBeFalsy();
});

it("exports all matching pages using the shared authenticated filter contract", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("deal,amount\nSelected,100\n", { status: 200 }));
  const result = await api.downloadPipelineCsv({ stage: ["a", "b"], business_unit: ["east"], search: "A & B", page: 3, page_size: 25, show_clients_without_matches: true });
  const url = new URL(String(fetch.mock.calls[0][0]), "http://localhost");
  expect(url.pathname).toContain("/reports/pipeline/export.csv");
  expect(url.searchParams.getAll("stage")).toEqual(["a", "b"]);
  expect(url.searchParams.get("business_unit")).toBe("east");
  expect(url.searchParams.get("search")).toBe("A & B");
  expect(url.searchParams.has("page")).toBe(false);
  expect(url.searchParams.has("page_size")).toBe(false);
  expect(url.searchParams.has("show_clients_without_matches")).toBe(false);
  const content = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(result);
  });
  expect(content).toContain("Selected,100");
});

it("offers filtered export and reports a failed download without losing filters", async () => {
  vi.spyOn(api, "getPipelineFacets").mockResolvedValue({ owners: [], business_units: [] });
  render(<MemoryRouter initialEntries={["/pipeline?stage=qualified"]}><PipelinePage /></MemoryRouter>);
  const button = await screen.findByRole("button", { name: "Export filtered CSV" });
  vi.spyOn(api, "downloadPipelineCsv").mockRejectedValue(new Error("Export unavailable"));
  fireEvent.click(button);
  await screen.findByRole("alert");
  expect(api.downloadPipelineCsv).toHaveBeenCalledWith(expect.objectContaining({ stage: ["qualified"] }));
  expect(screen.getByRole("alert")).toHaveTextContent("Export unavailable");
});
