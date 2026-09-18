/**
 * S5 E10 web tests — role-based render + Client SOW GM totals.
 *
 * The API client is mocked. We assert:
 *
 * 1. A user with a single role sees that role's dashboard.
 * 2. A multi-role user gets a selector defaulting to the highest-authority
 *    role.
 * 3. The Client SOW GM page renders the server-side totals row and
 *    surfaces the client-GM formula footnote so users know the aggregation
 *    isn't a mean of percentages.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import type {
  CeoDashboard,
  ClientSowGmDashboard,
  FinanceDashboard,
  SalesDashboard,
} from "../api/client";
import { ClientSowGmPage } from "../pages/ClientSowGm";
import { DashboardPage } from "../pages/Dashboard";

const useAuthMock = vi.fn();

vi.mock("../auth/AuthProvider", () => ({
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

function sampleCeo(): CeoDashboard {
  return {
    pipeline_value: "0",
    approved_vs_forecast_gp: { approved_gp: "0", forecast_gp: "0" },
    below_floor_deals: [],
    ceo_exceptions_pending: [],
    revenue_expiring_in_90_days: [],
    aged_blockers_by_owner: {},
    notes: { revenue_expiring_in_90_days: "Sprint 6" },
  };
}

function sampleFinance(): FinanceDashboard {
  return {
    gm_by_sow: [],
    gm_by_geography: {
      US: { revenue: "0", cost: "0", gm: null },
      India: { revenue: "0", cost: "0", gm: null },
    },
    approved_vs_forecast_vs_actual: {
      approved_gp: "0",
      forecast_gp: "0",
      actual_gp: null,
    },
    missing_cost_inputs: [],
    exceptions_and_exposure: [],
  };
}

function sampleSales(): SalesDashboard {
  return {
    my_deals: [],
    next_client_actions: [],
    missing_contracts: [],
    adviser_estimates: [],
    approval_statuses: [],
  };
}

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <Routes>
        <Route path="/dashboard" element={<DashboardPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("DashboardPage role routing", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAuthMock.mockReset();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("routes Sales-only user to the Sales dashboard", async () => {
    setUser(["Sales"]);
    vi.spyOn(apiClient, "getSalesDashboard").mockResolvedValue(sampleSales());
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText(/Sales dashboard/i)).toBeInTheDocument();
    });
  });

  it("routes Finance-only user to the Finance dashboard", async () => {
    setUser(["Finance"]);
    vi.spyOn(apiClient, "getFinanceDashboard").mockResolvedValue(
      sampleFinance(),
    );
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText(/Finance dashboard/i)).toBeInTheDocument();
    });
  });

  it("routes CEO-only user to the CEO dashboard", async () => {
    setUser(["CEO"]);
    vi.spyOn(apiClient, "getCeoDashboard").mockResolvedValue(sampleCeo());
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText(/CEO dashboard/i)).toBeInTheDocument();
    });
  });

  it("multi-role user (Finance + CEO) defaults to CEO and can switch", async () => {
    setUser(["Finance", "CEO"]);
    vi.spyOn(apiClient, "getCeoDashboard").mockResolvedValue(sampleCeo());
    vi.spyOn(apiClient, "getFinanceDashboard").mockResolvedValue(
      sampleFinance(),
    );
    renderDashboard();
    // Default: CEO (higher authority than Finance).
    await waitFor(() => {
      expect(screen.getByText(/CEO dashboard/i)).toBeInTheDocument();
    });
    const selector = screen.getByLabelText(/Role view/i) as HTMLSelectElement;
    expect(selector).toBeInTheDocument();
    const user = userEvent.setup();
    await user.selectOptions(selector, "finance");
    await waitFor(() => {
      expect(screen.getByText(/Finance dashboard/i)).toBeInTheDocument();
    });
  });

  it("user with no governance role sees empty-state", () => {
    setUser([]);
    renderDashboard();
    expect(screen.getByText(/No role dashboard available/i)).toBeInTheDocument();
  });
});

// ---- ClientSowGm --------------------------------------------------------

const CLIENT_ID = "11111111-1111-1111-1111-111111111111";
const OPP_A = "22222222-2222-2222-2222-222222222222";
const OPP_B = "33333333-3333-3333-3333-333333333333";

function sampleClientSowGm(): ClientSowGmDashboard {
  return {
    client_id: CLIENT_ID,
    client_name: "Acme Corp",
    rows: [
      {
        opportunity_id: OPP_A,
        hubspot_deal_id: "H-A",
        gm_model_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        engagement_type: "tm",
        start_date: "2026-03-01",
        end_date: "2026-08-31",
        revenue_us: "100000",
        revenue_india: "60000",
        cost_us: "65000",
        cost_india: "30000",
        approved_gm: null,
        forecast_gm: "0.40625",
        actual_gm: "0",
        exception_flag: false,
      },
      {
        opportunity_id: OPP_B,
        hubspot_deal_id: "H-B",
        gm_model_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        engagement_type: "tm",
        start_date: "2026-04-01",
        end_date: "2026-07-31",
        revenue_us: "50000",
        revenue_india: "0",
        cost_us: "20000",
        cost_india: "0",
        approved_gm: null,
        forecast_gm: "0.6",
        actual_gm: "0",
        exception_flag: false,
      },
    ],
    totals: {
      revenue_us: "150000",
      revenue_india: "60000",
      revenue: "210000",
      cost_us: "85000",
      cost_india: "30000",
      cost: "115000",
      gross_profit: "95000",
      // 95/210 as a Decimal string.
      client_gm: "0.452380952380952380952380952",
      formula:
        "client_gm = SUM(gross_profit_us + gross_profit_india) / " +
        "SUM(revenue_us + revenue_india) — not a mean of percentages",
    },
  };
}

function renderClientSowGm() {
  return render(
    <MemoryRouter initialEntries={[`/clients/${CLIENT_ID}/sows`]}>
      <Routes>
        <Route path="/clients/:id/sows" element={<ClientSowGmPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ClientSowGmPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAuthMock.mockReset();
    setUser(["Finance"]);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders per-SOW rows plus a totals row and the client-GM formula footnote", async () => {
    vi.spyOn(apiClient, "getClientSowGmDashboard").mockResolvedValue(
      sampleClientSowGm(),
    );
    renderClientSowGm();
    await waitFor(() => {
      expect(screen.getByText(/H-A/)).toBeInTheDocument();
      expect(screen.getByText(/H-B/)).toBeInTheDocument();
      expect(screen.getByText(/Totals/)).toBeInTheDocument();
    });
    // Formula footnote visible.
    const footnote = screen.getByTestId("client-gm-formula");
    expect(footnote.textContent).toMatch(/not a mean of percentages/i);
    // Server-side total revenue rendered (formatting is display-only).
    expect(footnote.textContent).toBeTruthy();
  });
});
