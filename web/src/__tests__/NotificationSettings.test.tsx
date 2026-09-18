import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import { NotificationSettingsPage } from "../pages/NotificationSettings";

const settings: apiClient.NotificationSettingsResponse = {
  categories: ["task_assigned", "approval_pending"],
  channels: ["email", "inapp"],
  items: [
    { category: "task_assigned", channel: "email", enabled: true },
    { category: "task_assigned", channel: "inapp", enabled: true },
    { category: "approval_pending", channel: "email", enabled: true },
    { category: "approval_pending", channel: "inapp", enabled: true },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter>
      <NotificationSettingsPage />
    </MemoryRouter>,
  );
}

describe("NotificationSettings", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, "getNotificationSettings").mockResolvedValue(settings);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the matrix and toggles a checkbox after debounce", async () => {
    const patch = vi
      .spyOn(apiClient, "patchNotificationSetting")
      .mockResolvedValue({ category: "task_assigned", channel: "email", enabled: false });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("task_assigned")).toBeInTheDocument();
    });

    const cb = screen.getByLabelText("task_assigned email") as HTMLInputElement;
    expect(cb.checked).toBe(true);

    const user = userEvent.setup();
    await user.click(cb);

    // Debounce is 350ms; wait for the PATCH.
    await waitFor(
      () => {
        expect(patch).toHaveBeenCalledTimes(1);
      },
      { timeout: 2000 },
    );
    expect(patch.mock.calls[0][0]).toEqual({
      category: "task_assigned",
      channel: "email",
      enabled: false,
    });
  });
});
