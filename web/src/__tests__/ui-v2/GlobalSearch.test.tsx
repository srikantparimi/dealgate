import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../../api/client";
import { GlobalSearch } from "../../ui-v2/GlobalSearch";

function renderPalette() {
  return render(
    <MemoryRouter>
      <GlobalSearch />
    </MemoryRouter>,
  );
}

describe("GlobalSearch", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, "getDeals").mockResolvedValue({
      items: [
        {
          id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
          hubspot_deal_id: "H-42",
          owner_id: null,
          client_id: null,
          client_name: "Atlas Robotics",
          engagement_type: "Fixed",
          sales_stage: null,
          governance_status: "Intake",
          next_client_action: null,
          next_client_date: null,
          coverage_state: "NDA missing",
        },
      ],
      page: 1,
      size: 25,
      total: 1,
    });
    vi.spyOn(apiClient, "listClients").mockResolvedValue({
      items: [
        {
          id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
          name: "Atlas Robotics",
          hubspot_company_id: "HS-1",
          coverage_state: "NDA missing",
          opportunity_count: 2,
          owner_ids: [],
        },
      ],
      page: 1,
      size: 25,
      total: 1,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("opens on ⌘K and closes on Escape", async () => {
    renderPalette();
    const user = userEvent.setup();

    // Fire the Cmd+K shortcut.
    await user.keyboard("{Meta>}k{/Meta}");

    await waitFor(() => {
      expect(
        screen.getByRole("dialog", { name: /global search/i }),
      ).toBeInTheDocument();
    });

    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(
        screen.queryByRole("dialog", { name: /global search/i }),
      ).not.toBeInTheDocument();
    });
  });

  it("shows grouped results for opportunities, clients and pages", async () => {
    renderPalette();
    const user = userEvent.setup();

    await user.click(
      screen.getByRole("button", { name: /open global search/i }),
    );

    const input = await screen.findByPlaceholderText(/search opportunities/i);
    await user.type(input, "atlas");

    await waitFor(() => {
      expect(screen.getByText(/opportunities/i)).toBeInTheDocument();
      expect(screen.getAllByText(/atlas robotics/i).length).toBeGreaterThan(0);
      expect(screen.getByText(/^clients$/i)).toBeInTheDocument();
    });
  });
});
