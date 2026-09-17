import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import { AuditPage } from "../pages/Audit";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/audit"]}>
      <AuditPage />
    </MemoryRouter>,
  );
}

const sample: apiClient.AuditListResponse = {
  items: [
    {
      id: "aaaa1111-aaaa-1111-aaaa-111111111111",
      ts: "2026-09-17T12:00:00Z",
      actor_id: "22222222-2222-2222-2222-222222222222",
      actor_email: "finance@smartek21.com",
      action: "opportunity.owner_changed",
      entity: "opportunity",
      entity_id: "O-100",
      before: { owner_id: null },
      after: { owner_id: "22222222-2222-2222-2222-222222222222" },
      correlation_id: "corr-1",
      prev_hash: null,
      row_hash: "deadbeef",
    },
    {
      id: "bbbb2222-bbbb-2222-bbbb-222222222222",
      ts: "2026-09-17T12:05:00Z",
      actor_id: null,
      actor_email: null,
      action: "task.create",
      entity: "task",
      entity_id: "T-1",
      before: null,
      after: { subject: "Chase NDA" },
      correlation_id: null,
      prev_hash: "deadbeef",
      row_hash: "cafebabe",
    },
  ],
  page: 1,
  size: 25,
  total: 2,
};

describe("AuditPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders rows from listAudit", async () => {
    vi.spyOn(apiClient, "listAudit").mockResolvedValue(sample);
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Audit log" })).toBeInTheDocument();
    });
    expect(screen.getByText("opportunity.owner_changed")).toBeInTheDocument();
    expect(screen.getByText("task.create")).toBeInTheDocument();
    expect(screen.getByText("finance@smartek21.com")).toBeInTheDocument();
    expect(screen.getByText("O-100")).toBeInTheDocument();
    expect(screen.getByText("T-1")).toBeInTheDocument();
  });

  it("expands the diff cell on click", async () => {
    vi.spyOn(apiClient, "listAudit").mockResolvedValue(sample);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("opportunity.owner_changed")).toBeInTheDocument();
    });
    const showButtons = screen.getAllByRole("button", { name: "Show diff" });
    const user = userEvent.setup();
    await user.click(showButtons[0]);
    const diff = await screen.findByLabelText("Diff details");
    expect(diff.textContent).toContain("after:");
    expect(diff.textContent).toContain("owner_id");
  });

  it("shows Chain valid chip on ok:true", async () => {
    vi.spyOn(apiClient, "listAudit").mockResolvedValue(sample);
    vi.spyOn(apiClient, "verifyAudit").mockResolvedValue({
      ok: true,
      first_broken_row: null,
      checked: 2,
      message: "Chain valid across 2 rows (full chain).",
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /verify chain/i })).toBeInTheDocument();
    });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /verify chain/i }));
    const status = await screen.findByLabelText("Verification result");
    expect(within(status).getByText("Chain valid")).toBeInTheDocument();
    expect(within(status).getByText(/Chain valid across 2 rows/)).toBeInTheDocument();
  });

  it("shows Chain broken chip with the broken row id on ok:false", async () => {
    vi.spyOn(apiClient, "listAudit").mockResolvedValue(sample);
    const brokenId = "cccc3333-cccc-3333-cccc-333333333333";
    vi.spyOn(apiClient, "verifyAudit").mockResolvedValue({
      ok: false,
      first_broken_row: brokenId,
      checked: 1,
      message: `Chain broken at row ${brokenId}: row_hash does not match recomputed value.`,
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /verify chain/i })).toBeInTheDocument();
    });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /verify chain/i }));
    const status = await screen.findByLabelText("Verification result");
    expect(within(status).getByText(`Chain broken at ${brokenId}`)).toBeInTheDocument();
  });

  it("shows an empty state when zero rows", async () => {
    vi.spyOn(apiClient, "listAudit").mockResolvedValue({
      items: [],
      page: 1,
      size: 25,
      total: 0,
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("No audit events")).toBeInTheDocument();
    });
  });

  it("shows an error state on fetch failure", async () => {
    vi.spyOn(apiClient, "listAudit").mockRejectedValue(new Error("nope"));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    });
    expect(screen.getByText("nope")).toBeInTheDocument();
  });
});
