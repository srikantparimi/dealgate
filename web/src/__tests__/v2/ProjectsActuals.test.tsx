/**
 * Delivery & actuals — Sprint 8 Wave 3 acceptance tests (spec §15).
 *
 * Every network call is mocked so the tests are deterministic. Rules
 * exercised:
 *   - Three portfolio tabs render (Portfolio / Actuals / Staffing) and
 *     switch on click.
 *   - Import Actuals action is gated to Finance / SystemAdmin — hidden
 *     for other roles (client-side UX; server independently enforces).
 *   - Project detail's "Update forecast" primary action is accessible
 *     only from Delivery / SystemAdmin roles.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../../api/client";
import type {
  ActualBatchListResponse,
  DealListResponse,
  DeliveryLatestResponse,
} from "../../api/client";
import { ProjectsActualsPage } from "../../pages/v2/ProjectsActuals";
import { ProjectDetailPage } from "../../pages/v2/projects/ProjectDetail";

const useAuthMock = vi.fn();

vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => useAuthMock(),
}));

function setUser(groups: string[]) {
  useAuthMock.mockReturnValue({
    user: {
      sub: "u1",
      email: "u@example.com",
      name: "U",
      groups,
      role: groups[0] ?? "User",
    },
  });
}

function emptyDeals(): DealListResponse {
  return { items: [], page: 1, size: 100, total: 0 };
}
function emptyBatches(): ActualBatchListResponse {
  return { items: [], page: 1, size: 20, total: 0 };
}

function seedDeals(): DealListResponse {
  return {
    items: [
      {
        id: "11111111-1111-1111-1111-111111111111",
        hubspot_deal_id: "HS-100",
        owner_id: null,
        client_id: "c1",
        client_name: "Acme Corp",
        engagement_type: "staff_aug",
        sales_stage: "closed_won",
        governance_status: "released",
        next_client_action: "Kickoff",
        next_client_date: "2026-10-01",
        coverage_state: "ready",
      },
      {
        id: "22222222-2222-2222-2222-222222222222",
        hubspot_deal_id: "HS-200",
        owner_id: null,
        client_id: "c2",
        client_name: "Beta Ltd",
        engagement_type: "fixed_bid",
        sales_stage: "in_progress",
        governance_status: "pending_delivery_hr",
        next_client_action: null,
        next_client_date: null,
        coverage_state: "gap",
      },
    ],
    page: 1,
    size: 100,
    total: 2,
  };
}

function stubList(opts: {
  deals?: DealListResponse;
  batches?: ActualBatchListResponse;
} = {}) {
  vi.spyOn(apiClient, "getDeals").mockResolvedValue(opts.deals ?? emptyDeals());
  vi.spyOn(apiClient, "listActualBatches").mockResolvedValue(
    opts.batches ?? emptyBatches(),
  );
}

function renderPortfolio() {
  return render(
    <MemoryRouter initialEntries={["/projects"]}>
      <Routes>
        <Route path="/projects/*" element={<ProjectsActualsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderDetail(role: string, tab?: string) {
  setUser([role]);
  const model: DeliveryLatestResponse = {
    gm_model: {
      id: "33333333-3333-3333-3333-333333333333",
      opportunity_id: "abc",
      sow_version_id: null,
      engagement_type: "staff_aug",
      delivery_pattern: null,
      contingency_pct: null,
      warranty_days: null,
      revenue_us: "100000",
      revenue_india: null,
      created_by: null,
      created_at: null,
      resource_lines: [],
      cost_lines: [],
      completeness_issues: [],
    },
  };
  vi.spyOn(apiClient, "getLatestDeliveryModel").mockResolvedValue(model);
  vi.spyOn(apiClient, "getLatestForecast").mockResolvedValue(null);

  const path = tab ? `/projects/abc/${tab}` : "/projects/abc";
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/projects/:id" element={<ProjectDetailPage />} />
        <Route
          path="/projects/:id/:tab"
          element={<ProjectDetailPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProjectsActualsPage — portfolio index", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAuthMock.mockReset();
    setUser(["Finance"]);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders three portfolio tabs (Portfolio, Actuals, Staffing)", async () => {
    stubList({ deals: seedDeals() });
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /Portfolio/i })).toBeInTheDocument();
    });
    expect(screen.getByRole("tab", { name: /Actuals/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Staffing/i })).toBeInTheDocument();
  });

  it("shows the Portfolio table with rows sourced from getDeals", async () => {
    stubList({ deals: seedDeals() });
    renderPortfolio();
    const table = await screen.findByTestId("portfolio-table");
    expect(within(table).getByText("Acme Corp")).toBeInTheDocument();
    expect(within(table).getByText("Beta Ltd")).toBeInTheDocument();
  });

  it("exposes the Import Actuals primary action for Finance users", async () => {
    setUser(["Finance"]);
    stubList();
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getByTestId("import-actuals")).toBeInTheDocument();
    });
    expect(screen.getByTestId("export-portfolio")).toBeInTheDocument();
  });

  it("also exposes the Import Actuals action for SystemAdmin", async () => {
    setUser(["SystemAdmin"]);
    stubList();
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getByTestId("import-actuals")).toBeInTheDocument();
    });
  });

  it("hides the Import Actuals action for non-Finance roles", async () => {
    setUser(["Sales"]);
    stubList();
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getByTestId("export-portfolio")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("import-actuals")).not.toBeInTheDocument();
  });

  it("switches to the Actuals tab and shows the period picker + upload gate", async () => {
    setUser(["Finance"]);
    stubList();
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /Actuals/i })).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole("tab", { name: /^Actuals/i }));
    // Period picker present.
    expect(
      screen.getByLabelText(/Reconciliation period/i),
    ).toBeInTheDocument();
    // Finance sees the upload primary.
    expect(screen.getByTestId("actuals-upload-primary")).toBeInTheDocument();
  });

  it("switches to the Staffing tab and shows the filter row", async () => {
    setUser(["Finance"]);
    stubList();
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /Staffing/i })).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole("tab", { name: /^Staffing/i }));
    expect(screen.getByLabelText(/^Role$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Location$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Delivery owner/i)).toBeInTheDocument();
  });
});

describe("ProjectDetailPage — forecast update role gate", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAuthMock.mockReset();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the Update forecast primary action for Delivery users", async () => {
    renderDetail("Delivery", "financials");
    await waitFor(() => {
      expect(screen.getByTestId("forecast-update")).toBeInTheDocument();
    });
    expect(
      screen.queryByTestId("forecast-update-gated"),
    ).not.toBeInTheDocument();
  });

  it("also shows the Update forecast action for SystemAdmin", async () => {
    renderDetail("SystemAdmin", "financials");
    await waitFor(() => {
      expect(screen.getByTestId("forecast-update")).toBeInTheDocument();
    });
  });

  it("hides the Update forecast action for non-Delivery roles (Finance)", async () => {
    renderDetail("Finance", "financials");
    await waitFor(() => {
      expect(
        screen.getByTestId("forecast-update-gated"),
      ).toBeInTheDocument();
    });
    expect(screen.queryByTestId("forecast-update")).not.toBeInTheDocument();
  });

  it("renders all five detail tabs", async () => {
    renderDetail("Delivery", "overview");
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /Overview/i })).toBeInTheDocument();
    });
    expect(screen.getByRole("tab", { name: /Financials/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^Staffing$/i })).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: /Risks & changes/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Activity/i })).toBeInTheDocument();
  });
});
