import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import * as api from "../../api/client";
import { PipelinePage } from "../../pages/v2/Pipeline";

// S23-PL1 item 8: "Last synced" reads last_success_at from GET /hubspot/sync-health,
// never the intake heartbeat row (hubspot_webhook), which froze on 2026-10-01.

const page = { items: [], total: 0, page: 1, page_size: 25, meta: { stage_counts: [], unknown_bucket: 0 } };
const aggregate = { open_count: 0, open_value_by_currency: {}, closing_this_month: 0, overdue_actions: 0, pending_approvals: 0, agreement_gaps: 0 };
const hoursAgo = (h: number) => new Date(Date.now() - h * 3600_000).toISOString();

beforeEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  vi.spyOn(api, "getPipelineFacets").mockResolvedValue({ owners: [], business_units: [] });
  vi.spyOn(api, "listTrackingGroups").mockResolvedValue({ items: [] } as never);
  vi.spyOn(api, "listSavedViews").mockResolvedValue({ items: [] } as never);
  vi.spyOn(api, "getUserPreference").mockResolvedValue(null);
  vi.spyOn(api, "putUserPreference").mockResolvedValue(undefined as never);
  vi.spyOn(api, "listWatchlist").mockResolvedValue({ items: [], counts: {} });
  vi.spyOn(api, "listPipelineClients").mockResolvedValue(page as never);
  vi.spyOn(api, "listPipelineOpportunities").mockResolvedValue(page as never);
  vi.spyOn(api, "getPipelineSummary").mockResolvedValue(aggregate as never);
  // The frozen intake heartbeat the old label used to read.
  vi.spyOn(api, "getSyncStatus").mockResolvedValue({ items: [
    { source: "hubspot_webhook", last_success_at: hoursAgo(24 * 12), last_attempt_at: hoursAgo(24 * 12), last_error: null, lag_seconds: 0 },
    { source: "hubspot_backfill", last_success_at: hoursAgo(3), last_attempt_at: hoursAgo(3), last_error: null, lag_seconds: 0 },
  ] });
});

it("labels the banner with the last successful deal sync, not the heartbeat", async () => {
  vi.spyOn(api, "getSyncHealth").mockResolvedValue({
    state: "fresh", last_success_at: hoursAgo(2), last_attempt_at: hoursAgo(2), last_status: "ok", schedule: "nightly",
  });
  render(<MemoryRouter initialEntries={["/pipeline"]}><PipelinePage /></MemoryRouter>);
  const banner = await screen.findByTestId("sync-banner");
  await waitFor(() => expect(banner).toHaveTextContent("Last synced2h ago"));
  expect(banner).not.toHaveTextContent("12d ago");
});

it("says there is no recorded sync when sync-health cannot be read", async () => {
  vi.spyOn(api, "getSyncHealth").mockRejectedValue(new Error("offline"));
  render(<MemoryRouter initialEntries={["/pipeline"]}><PipelinePage /></MemoryRouter>);
  const banner = await screen.findByTestId("sync-banner");
  await waitFor(() => expect(banner).toHaveTextContent("Last syncedno recorded sync"));
  expect(banner).not.toHaveTextContent("12d ago");
});
