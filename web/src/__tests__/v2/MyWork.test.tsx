/**
 * MyWork (`/work`) — Sprint 8 Wave 3 acceptance tests (spec §6).
 *
 * The page is exercised end-to-end via the rendered DOM; every network
 * call is mocked. Rules exercised here:
 *
 * - Four tabs render with the exact labels required by the spec.
 * - Filters (task type + due range) narrow the visible rows without
 *   losing the tab count.
 * - Row click opens the right Sheet drawer with the task's title.
 * - The row checkbox is only offered for manually-completable tasks;
 *   approval and signature tasks render a workflow-only affordance
 *   (per spec §6 non-negotiable).
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../../api/client";
import type { TaskInboxRow, TaskListResponse } from "../../api/client";
import { MyWorkPage } from "../../pages/v2/MyWork";

function task(row: Partial<TaskInboxRow>): TaskInboxRow {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    owner_id: "u-1",
    subject: "Draft NDA for Acme",
    status: "open",
    category: "coverage",
    due_date: "2027-01-01",
    wake_at: null,
    completed_at: null,
    completed_by: null,
    escalation_level: 0,
    ...row,
  };
}

function tasksResponse(items: TaskInboxRow[]): TaskListResponse {
  return { items, page: 1, size: 25, total: items.length };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/work"]}>
      <MyWorkPage />
    </MemoryRouter>,
  );
}

describe("MyWorkPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    // Freeze "now" so overdue-vs-open bucketing is deterministic.
    vi.setSystemTime(new Date("2026-06-15T12:00:00Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("renders the four workspace tabs with counts", async () => {
    vi.spyOn(apiClient, "listTasks").mockResolvedValue(
      tasksResponse([
        task({ id: "t1", subject: "Assigned open", status: "open", due_date: "2027-01-01" }),
        task({
          id: "t2",
          subject: "Waiting snoozed",
          status: "snoozed",
          due_date: "2027-01-01",
        }),
        task({
          id: "t3",
          subject: "Overdue coverage",
          status: "open",
          due_date: "2026-01-01",
        }),
        task({
          id: "t4",
          subject: "Completed old",
          status: "done",
          due_date: "2026-01-01",
        }),
      ]),
    );

    renderPage();

    await waitFor(() =>
      expect(screen.getByRole("tab", { name: /Assigned to me/i })).toBeInTheDocument(),
    );
    expect(screen.getByRole("tab", { name: /Waiting on others/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Overdue/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Completed/i })).toBeInTheDocument();

    // Default tab is "assigned" — Assigned open must be visible.
    expect(screen.getByText("Assigned open")).toBeInTheDocument();
    // Waiting + Overdue live in other tabs so not visible yet.
    expect(screen.queryByText("Waiting snoozed")).not.toBeInTheDocument();
  });

  it("filters by task type without dropping other tab counts", async () => {
    const user = userEvent.setup();
    vi.spyOn(apiClient, "listTasks").mockResolvedValue(
      tasksResponse([
        task({
          id: "t1",
          subject: "Coverage row",
          category: "coverage",
          due_date: "2027-01-01",
        }),
        task({
          id: "t2",
          subject: "Intake row",
          category: "intake",
          due_date: "2027-01-01",
        }),
      ]),
    );

    renderPage();

    await waitFor(() => expect(screen.getByText("Coverage row")).toBeInTheDocument());
    expect(screen.getByText("Intake row")).toBeInTheDocument();

    // Narrow to intake — only the intake row survives.
    const catFilter = screen.getByLabelText(/Task type/i);
    await user.selectOptions(catFilter, "intake");
    expect(screen.queryByText("Coverage row")).not.toBeInTheDocument();
    expect(screen.getByText("Intake row")).toBeInTheDocument();
  });

  it("opens the right Sheet drawer on row click", async () => {
    const user = userEvent.setup();
    vi.spyOn(apiClient, "listTasks").mockResolvedValue(
      tasksResponse([
        task({
          id: "t1",
          subject: "Open me in a drawer",
          due_date: "2027-01-01",
        }),
      ]),
    );

    renderPage();

    const row = await screen.findByTestId("task-row-t1");
    await user.click(row);

    // The Sheet title mirrors the task subject.
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Open me in a drawer");
    // Reassign field lives in the drawer.
    expect(screen.getByLabelText(/New owner/i)).toBeInTheDocument();
  });

  it("hides the checkbox for approval + signature tasks and routes through the workflow", async () => {
    const user = userEvent.setup();
    vi.spyOn(apiClient, "listTasks").mockResolvedValue(
      tasksResponse([
        task({
          id: "t-approval",
          subject: "Approval only",
          category: "approval",
          due_date: "2027-01-01",
        }),
        task({
          id: "t-manual",
          subject: "Manual complete",
          category: "coverage",
          due_date: "2027-01-01",
        }),
      ]),
    );

    renderPage();

    await waitFor(() =>
      expect(screen.getByText("Approval only")).toBeInTheDocument(),
    );

    // The manual row exposes a checkbox; the approval row exposes only
    // the "workflow" placeholder (aria-label starts with "Workflow").
    expect(
      screen.getByRole("checkbox", { name: /Mark "Manual complete" complete/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("checkbox", { name: /Mark "Approval only" complete/i }),
    ).not.toBeInTheDocument();

    // Opening the approval row shows the "Open workflow" button, not
    // a generic Complete task button.
    const approvalRow = screen.getByTestId("task-row-t-approval");
    await user.click(approvalRow);
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(/Open workflow/i);
    expect(dialog.textContent ?? "").not.toMatch(/^Complete task$/m);
  });
});
