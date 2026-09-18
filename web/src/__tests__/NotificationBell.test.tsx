import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import { NotificationBell } from "../ui/NotificationBell";

const notif: apiClient.NotificationRow = {
  id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  category: "task_assigned",
  channel: "inapp",
  subject: "You have a task",
  body_md: "Please review.",
  related_entity: "task",
  related_entity_id: "t-1",
  status: "sent",
  created_at: "2026-01-01T10:00:00Z",
  read_at: null,
};

describe("NotificationBell", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, "listInboxNotifications").mockResolvedValue({
      items: [notif],
      unread_count: 1,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the unread count badge and opens the panel on click", async () => {
    render(<NotificationBell />);
    await waitFor(() => {
      expect(screen.getByTestId("unread-count")).toHaveTextContent("1");
    });

    const user = userEvent.setup();
    await user.click(
      screen.getByRole("button", { name: /notifications \(1 unread\)/i }),
    );
    expect(await screen.findByText("You have a task")).toBeInTheDocument();
  });

  it("marks a notification read when the row is clicked", async () => {
    const markRead = vi
      .spyOn(apiClient, "markNotificationRead")
      .mockResolvedValue({ ...notif, read_at: "2026-01-01T10:05:00Z" });
    render(<NotificationBell />);
    await waitFor(() => {
      expect(screen.getByTestId("unread-count")).toHaveTextContent("1");
    });
    const user = userEvent.setup();
    await user.click(
      screen.getByRole("button", { name: /notifications \(1 unread\)/i }),
    );
    await user.click(await screen.findByText("You have a task"));
    await waitFor(() => {
      expect(markRead).toHaveBeenCalledWith(notif.id);
    });
    // Badge decremented to zero → no badge rendered.
    await waitFor(() => {
      expect(screen.queryByTestId("unread-count")).not.toBeInTheDocument();
    });
  });
});
