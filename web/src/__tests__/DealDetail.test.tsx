import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import { DealDetailPage } from "../pages/DealDetail";

const DEAL_ID = "11111111-1111-1111-1111-111111111111";

const initialDeal: apiClient.DealDetail = {
  id: DEAL_ID,
  hubspot_deal_id: "H-100",
  owner_id: "22222222-2222-2222-2222-222222222222",
  client_id: null,
  client_name: null,
  engagement_type: null,
  sales_stage: "Discovery",
  governance_status: "Intake",
  next_client_action: "Discovery call",
  next_client_date: null,
  coverage_state: "No client linked",
  tasks: [],
  audit: [],
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/deals/${DEAL_ID}`]}>
      <Routes>
        <Route path="/deals/:id" element={<DealDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("DealDetail", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders Intake, Coverage, Tasks and Audit panels", async () => {
    vi.spyOn(apiClient, "getDeal").mockResolvedValue(initialDeal);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Deal H-100")).toBeInTheDocument();
    });
    expect(screen.getByRole("heading", { name: "Intake" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Coverage" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Tasks" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Recent audit" })).toBeInTheDocument();
  });

  it("calls patchDeal on save with the changed fields", async () => {
    vi.spyOn(apiClient, "getDeal").mockResolvedValue(initialDeal);
    const updated = { ...initialDeal, engagement_type: "Fixed" };
    const patch = vi.spyOn(apiClient, "patchDeal").mockResolvedValue(updated);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Deal H-100")).toBeInTheDocument();
    });

    const engagementInput = screen.getByLabelText("Engagement type") as HTMLInputElement;
    const user = userEvent.setup();
    await user.clear(engagementInput);
    await user.type(engagementInput, "Fixed");
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => {
      expect(patch).toHaveBeenCalledTimes(1);
    });
    expect(patch.mock.calls[0][0]).toBe(DEAL_ID);
    expect(patch.mock.calls[0][1]).toEqual({ engagement_type: "Fixed" });
    await waitFor(() => {
      expect(screen.getByText("Saved")).toBeInTheDocument();
    });
  });
});
