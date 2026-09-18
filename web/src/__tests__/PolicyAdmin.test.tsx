import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import { PolicyAdminPage } from "../pages/PolicyAdmin";

const list: apiClient.PolicyListResponse = {
  items: [
    {
      id: "22222222-2222-2222-2222-222222222222",
      effective_from: "2026-09-01",
      us_floor: "0.3500",
      india_floor: "0.5000",
      fx_convention: "fixed_at_sow_date",
      published_at: "2026-09-10T09:00:00Z",
      published_by: null,
      notes: "Baseline",
      is_active: true,
    },
  ],
  active: {
    id: "22222222-2222-2222-2222-222222222222",
    effective_from: "2026-09-01",
    us_floor: "0.3500",
    india_floor: "0.5000",
    fx_convention: "fixed_at_sow_date",
    is_default: false,
  },
  allowed_fx_conventions: ["fixed_at_sow_date", "monthly_average"],
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/admin/policy"]}>
      <PolicyAdminPage />
    </MemoryRouter>,
  );
}

describe("PolicyAdmin", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, "listPolicies").mockResolvedValue(list);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the active policy and version list", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByLabelText("Active policy")).toBeInTheDocument();
    });
    // Active chip in the header card + Active chip in the table row.
    const chips = screen.getAllByText("Active");
    expect(chips.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Effective 2026-09-01/)).toBeInTheDocument();
  });

  it("submits publishPolicy from the modal", async () => {
    const published = vi.spyOn(apiClient, "publishPolicy").mockResolvedValue({
      id: "33333333-3333-3333-3333-333333333333",
      effective_from: "2026-09-15",
      us_floor: "0.4000",
      india_floor: "0.5500",
      fx_convention: "monthly_average",
      published_at: "2026-09-15T00:00:00Z",
      published_by: null,
      notes: null,
      is_active: true,
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByLabelText("Active policy")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /publish new policy/i }));

    await user.type(await screen.findByLabelText("Effective from"), "2026-09-15");
    // Replace defaults.
    const usInput = screen.getByLabelText("US floor") as HTMLInputElement;
    await user.clear(usInput);
    await user.type(usInput, "0.40");
    const indiaInput = screen.getByLabelText("India floor") as HTMLInputElement;
    await user.clear(indiaInput);
    await user.type(indiaInput, "0.55");
    await user.selectOptions(screen.getByLabelText("FX convention"), "monthly_average");

    await user.click(screen.getByRole("button", { name: /^publish$/i }));

    await waitFor(() => {
      expect(published).toHaveBeenCalledTimes(1);
    });
    // Number inputs collapse trailing zeros ("0.40" -> "0.4"); the server
    // parses either as a Decimal so the on-the-wire form is fine.
    expect(published.mock.calls[0][0]).toMatchObject({
      effective_from: "2026-09-15",
      us_floor: "0.4",
      india_floor: "0.55",
      fx_convention: "monthly_average",
    });
  });

  it("blocks submit and shows a hint when US floor >= India floor", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByLabelText("Active policy")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /publish new policy/i }));

    await user.type(await screen.findByLabelText("Effective from"), "2026-09-15");
    const usInput = screen.getByLabelText("US floor") as HTMLInputElement;
    await user.clear(usInput);
    await user.type(usInput, "0.60");
    const indiaInput = screen.getByLabelText("India floor") as HTMLInputElement;
    await user.clear(indiaInput);
    await user.type(indiaInput, "0.50");

    // Client-side hint appears; submit disabled.
    expect(
      screen.getByText(/India floor must be strictly greater than US floor/),
    ).toBeInTheDocument();
    const publishBtn = screen.getByRole("button", { name: /^publish$/i });
    expect(publishBtn).toBeDisabled();
  });

  it("surfaces API errors from publishPolicy (422)", async () => {
    vi.spyOn(apiClient, "publishPolicy").mockRejectedValueOnce(
      new apiClient.ApiError(
        422,
        { detail: "us_floor must be strictly less than india_floor" },
        "us_floor must be strictly less than india_floor",
      ),
    );
    renderPage();
    await waitFor(() => {
      expect(screen.getByLabelText("Active policy")).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /publish new policy/i }));
    await user.type(await screen.findByLabelText("Effective from"), "2026-09-15");
    // Client thinks it's ok — mocked API rejects.
    await user.click(screen.getByRole("button", { name: /^publish$/i }));

    await waitFor(() => {
      expect(
        screen.getByText("us_floor must be strictly less than india_floor"),
      ).toBeInTheDocument();
    });
  });
});
