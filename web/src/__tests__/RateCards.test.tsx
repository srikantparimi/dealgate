import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import { RateCardsPage } from "../pages/RateCards";

const V1_ID = "11111111-1111-1111-1111-111111111111";

const list: apiClient.RateCardListResponse = {
  items: [
    {
      id: V1_ID,
      effective_from: "2026-09-01",
      published_at: "2026-09-10T09:00:00Z",
      published_by: null,
      notes: "Baseline",
      row_count: 3,
      is_active: true,
    },
  ],
  active_id: V1_ID,
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/admin/rate-cards"]}>
      <RateCardsPage />
    </MemoryRouter>,
  );
}

describe("RateCards", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, "listRateCards").mockResolvedValue(list);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders versions from listRateCards and flags the active one", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("2026-09-01")).toBeInTheDocument();
    });
    expect(screen.getByText("Baseline")).toBeInTheDocument();
    // Active chip near the active row.
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("submits publishRateCard from the modal", async () => {
    const published = vi.spyOn(apiClient, "publishRateCard").mockResolvedValue({
      version: {
        id: V1_ID,
        effective_from: "2026-09-15",
        published_at: "2026-09-15T00:00:00Z",
        published_by: null,
        notes: null,
        row_count: 1,
        is_active: true,
        rows: [],
      },
      warnings: [],
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("2026-09-01")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /publish new version/i }));

    const dateInput = await screen.findByLabelText("Effective from");
    await user.type(dateInput, "2026-09-15");
    await user.type(screen.getByLabelText("Row 1 role"), "Engineer");
    await user.type(screen.getByLabelText("Row 1 seniority"), "Mid");
    await user.type(screen.getByLabelText("Row 1 cost_low"), "55");
    await user.type(screen.getByLabelText("Row 1 cost_base"), "70");
    await user.type(screen.getByLabelText("Row 1 cost_high"), "85");

    await user.click(screen.getByRole("button", { name: /^publish$/i }));

    await waitFor(() => {
      expect(published).toHaveBeenCalledTimes(1);
    });
    const body = published.mock.calls[0][0];
    expect(body.effective_from).toBe("2026-09-15");
    expect(body.rows[0]).toMatchObject({
      role: "Engineer",
      seniority: "Mid",
      location: "US",
      cost_low: "55",
      cost_base: "70",
      cost_high: "85",
    });
  });

  it("surfaces API errors from publishRateCard (422)", async () => {
    vi.spyOn(apiClient, "publishRateCard").mockRejectedValueOnce(
      new apiClient.ApiError(
        422,
        { detail: "rows[0].cost_base must be > 0" },
        "rows[0].cost_base must be > 0",
      ),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("2026-09-01")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /publish new version/i }));
    await user.type(await screen.findByLabelText("Effective from"), "2026-09-15");
    await user.type(screen.getByLabelText("Row 1 role"), "Engineer");
    await user.type(screen.getByLabelText("Row 1 seniority"), "Mid");
    await user.type(screen.getByLabelText("Row 1 cost_low"), "55");
    await user.type(screen.getByLabelText("Row 1 cost_base"), "70");
    await user.type(screen.getByLabelText("Row 1 cost_high"), "85");
    await user.click(screen.getByRole("button", { name: /^publish$/i }));

    await waitFor(() => {
      expect(
        screen.getByText("rows[0].cost_base must be > 0"),
      ).toBeInTheDocument();
    });
  });
});
