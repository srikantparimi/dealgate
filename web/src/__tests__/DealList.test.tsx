import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import { DealListPage } from "../pages/DealList";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/deals"]}>
      <DealListPage />
    </MemoryRouter>,
  );
}

const sampleList: apiClient.DealListResponse = {
  items: [
    {
      id: "11111111-1111-1111-1111-111111111111",
      hubspot_deal_id: "H-100",
      owner_id: "22222222-2222-2222-2222-222222222222",
      client_id: null,
      client_name: null,
      engagement_type: "Fixed",
      sales_stage: "Qualified",
      governance_status: "Intake",
      next_client_action: "Send NDA",
      next_client_date: "2026-03-01",
      coverage_state: "NDA missing",
    },
  ],
  page: 1,
  size: 25,
  total: 1,
};

describe("DealList", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders rows from getDeals", async () => {
    vi.spyOn(apiClient, "getDeals").mockResolvedValue(sampleList);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("H-100")).toBeInTheDocument();
    });
    expect(screen.getByText("Fixed")).toBeInTheDocument();
    expect(screen.getByText("NDA missing")).toBeInTheDocument();
  });

  it("shows an empty state when zero rows", async () => {
    vi.spyOn(apiClient, "getDeals").mockResolvedValue({
      items: [],
      page: 1,
      size: 25,
      total: 0,
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("No deals yet")).toBeInTheDocument();
    });
  });

  it("shows an error state when the fetch fails", async () => {
    vi.spyOn(apiClient, "getDeals").mockRejectedValue(new Error("boom"));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    });
    expect(screen.getByText("boom")).toBeInTheDocument();
  });
});
