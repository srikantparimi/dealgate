import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import { AdminReplayPage } from "../pages/AdminReplay";

const HUBSPOT_JOB_ID = "11111111-1111-1111-1111-111111111111";
const NOTIF_ID = "22222222-2222-2222-2222-222222222222";
const EVENT_ID = "33333333-3333-3333-3333-333333333333";

const hubspotList: apiClient.AdminReplayListResponse<apiClient.AdminReplayHubspotRow> = {
  items: [
    {
      id: HUBSPOT_JOB_ID,
      opportunity_id: "44444444-4444-4444-4444-444444444444",
      hubspot_deal_id: "999",
      target_state: { governance_status: "Ready to Sign" },
      status: "failed",
      attempts: 5,
      next_attempt_at: null,
      last_error: "hubspot 500",
      created_at: "2026-09-01T10:00:00Z",
      sent_at: null,
    },
  ],
  page: 1,
  size: 25,
  total: 1,
};

const notifList: apiClient.AdminReplayListResponse<apiClient.AdminReplayNotificationRow> = {
  items: [
    {
      id: NOTIF_ID,
      user_id: "55555555-5555-5555-5555-555555555555",
      category: "task_assigned",
      channel: "email",
      subject: "You have a task",
      status: "failed",
      attempts: 5,
      next_attempt_at: null,
      last_error: "smtp bounce",
      created_at: "2026-09-01T09:00:00Z",
      sent_at: null,
    },
  ],
  page: 1,
  size: 25,
  total: 1,
};

const eventList: apiClient.AdminReplayListResponse<apiClient.AdminReplayIntegrationEventRow> = {
  items: [
    {
      id: EVENT_ID,
      source: "hubspot",
      source_event_id: "abc-123",
      received_at: "2026-09-01T08:00:00Z",
      processed_at: null,
      payload: { eventId: 42 },
    },
  ],
  page: 1,
  size: 25,
  total: 1,
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/admin/replay"]}>
      <AdminReplayPage />
    </MemoryRouter>,
  );
}

describe("AdminReplayPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, "listAdminReplayHubspotWriteback").mockResolvedValue(
      hubspotList,
    );
    vi.spyOn(apiClient, "listAdminReplayNotifications").mockResolvedValue(
      notifList,
    );
    vi.spyOn(apiClient, "listAdminReplayIntegrationEvents").mockResolvedValue(
      eventList,
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the three DLQ sections with their rows and last_error", async () => {
    renderPage();

    // Section headings appear.
    expect(
      await screen.findByRole("heading", { name: /hubspot writeback/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /notifications/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /integration events/i }),
    ).toBeInTheDocument();

    // Rows populated from the mocked APIs.
    await waitFor(() => {
      expect(screen.getByText("999")).toBeInTheDocument();
    });
    expect(screen.getByText("You have a task")).toBeInTheDocument();
    expect(screen.getByText("abc-123")).toBeInTheDocument();

    // last_error surfaces inline for the two lifecycle DLQs.
    expect(screen.getByText("hubspot 500")).toBeInTheDocument();
    expect(screen.getByText("smtp bounce")).toBeInTheDocument();
  });

  it("Replay button on the HubSpot section calls the POST client", async () => {
    const replay = vi
      .spyOn(apiClient, "replayAdminHubspotWriteback")
      .mockResolvedValue({ id: HUBSPOT_JOB_ID, status: "sent" });

    renderPage();
    await waitFor(() => {
      expect(screen.getByText("999")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    const hubspotSection = screen.getByRole("region", {
      name: /hubspot writeback dlq/i,
    });
    const button = within(hubspotSection).getByRole("button", { name: /replay/i });
    await user.click(button);

    await waitFor(() => {
      expect(replay).toHaveBeenCalledWith(HUBSPOT_JOB_ID);
    });
  });

  it("Replay button on the Notifications section calls the POST client", async () => {
    const replay = vi
      .spyOn(apiClient, "replayAdminNotification")
      .mockResolvedValue({ id: NOTIF_ID, status: "pending" });

    renderPage();
    await waitFor(() => {
      expect(screen.getByText("You have a task")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    const section = screen.getByRole("region", { name: /notifications dlq/i });
    await user.click(within(section).getByRole("button", { name: /replay/i }));

    await waitFor(() => {
      expect(replay).toHaveBeenCalledWith(NOTIF_ID);
    });
  });

  it("Replay button on the Integration Events section calls the POST client", async () => {
    const replay = vi
      .spyOn(apiClient, "replayAdminIntegrationEvent")
      .mockResolvedValue({ id: EVENT_ID, status: "processed" });

    renderPage();
    await waitFor(() => {
      expect(screen.getByText("abc-123")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    const section = screen.getByRole("region", {
      name: /integration events dlq/i,
    });
    await user.click(within(section).getByRole("button", { name: /replay/i }));

    await waitFor(() => {
      expect(replay).toHaveBeenCalledWith(EVENT_ID);
    });
  });
});
