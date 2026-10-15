// S21 · the shared Pipeline query contract of the API client. The old Pipeline
// page's tests that lived here (facet refresh, stale facet responses, saved-view
// application, filtered export on the page) moved with the page's replacement in
// S23-PL2 to web/src/__tests__/v2/S23PipelineShell*.test.tsx; these two pin
// client functions that other pages still call (getPipelineFacets: Command Center).
import { beforeEach, expect, it, vi } from "vitest";
import * as api from "../../api/client";

beforeEach(() => {
  vi.restoreAllMocks();
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
