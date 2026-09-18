import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import * as authModule from "../auth/AuthProvider";
import { MyTasksPage } from "../pages/MyTasks";

const OWNER = "11111111-1111-1111-1111-111111111111";
const OTHER = "22222222-2222-2222-2222-222222222222";

const baseTask: apiClient.TaskInboxRow = {
  id: "33333333-3333-3333-3333-333333333333",
  owner_id: OWNER,
  subject: "Confirm engagement type",
  status: "assigned",
  category: "intake",
  due_date: "2026-01-15",
  wake_at: null,
  completed_at: null,
  completed_by: null,
  escalation_level: 0,
};

const list: apiClient.TaskListResponse = {
  items: [baseTask],
  page: 1,
  size: 25,
  total: 1,
};

function stubAuth(groups: string[] = ["Sales"]) {
  vi.spyOn(authModule, "useAuth").mockReturnValue({
    user: {
      sub: OWNER,
      email: "owner@smartek21.com",
      name: "Owner",
      groups,
      role: groups[0] ?? "User",
    },
    isAuthenticated: true,
    tokenReady: true,
    login: vi.fn(),
    logout: vi.fn(),
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/tasks"]}>
      <MyTasksPage />
    </MemoryRouter>,
  );
}

describe("MyTasks", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    stubAuth();
    vi.spyOn(apiClient, "listTasks").mockResolvedValue(list);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the caller's tasks", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Confirm engagement type")).toBeInTheDocument();
    });
    // "intake" and "assigned" appear in both the filter dropdown options and
    // the table row — scope to the row cell so the assertion is unambiguous.
    const row = screen.getByText("Confirm engagement type").closest("tr");
    expect(row).not.toBeNull();
    expect(row!.textContent).toContain("intake");
    expect(row!.textContent).toContain("assigned");
  });

  it("PATCHes the task to in_progress when Start is clicked", async () => {
    const patch = vi.spyOn(apiClient, "patchTask").mockResolvedValue({
      ...baseTask,
      status: "in_progress",
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Confirm engagement type")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /start confirm/i }));

    await waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(1);
    });
    expect(patch.mock.calls[0][0]).toBe(baseTask.id);
    expect(patch.mock.calls[0][1]).toEqual({ status: "in_progress" });
  });

  it("hides Reassign for non-leaders and shows it for leaders", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Confirm engagement type")).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("button", { name: /reassign confirm/i }),
    ).not.toBeInTheDocument();

    vi.restoreAllMocks();
    stubAuth(["SalesLeader"]);
    vi.spyOn(apiClient, "listTasks").mockResolvedValue(list);
    const reassign = vi
      .spyOn(apiClient, "reassignTask")
      .mockResolvedValue({ ...baseTask, owner_id: OTHER });

    renderPage();
    const user = userEvent.setup();
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /reassign confirm/i }),
      ).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /reassign confirm/i }));
    const input = await screen.findByLabelText("New owner id");
    await user.type(input, OTHER);
    await user.click(screen.getByRole("button", { name: /^reassign$/i }));

    await waitFor(() => {
      expect(reassign).toHaveBeenCalledWith(baseTask.id, { new_owner_id: OTHER });
    });
  });

  it("shows empty state when there are no tasks", async () => {
    vi.spyOn(apiClient, "listTasks").mockResolvedValue({
      items: [],
      page: 1,
      size: 25,
      total: 0,
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("No tasks")).toBeInTheDocument();
    });
  });
});
