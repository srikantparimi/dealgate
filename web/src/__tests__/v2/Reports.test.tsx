/**
 * Reports — Sprint 8 Wave 3 acceptance tests (spec §17).
 *
 * Rules exercised:
 *   - All five report tabs render (Portfolio / Margin / Revenue /
 *     Renewals / Approval turnaround).
 *   - The export buttons invoke the injected handler with the correct
 *     kind + format.
 *   - The Revenue tab surfaces the "invoice/cash not sourced" caveat
 *     by default (spec §17: never combine them as "Revenue").
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../../api/client";
import type {
  CeoDashboard,
  DealListResponse,
  FinanceDashboard,
  RenewalListResponse,
} from "../../api/client";
import { ReportsPage } from "../../pages/v2/Reports";

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

function emptyCeo(): CeoDashboard {
  return {
    pipeline_value: "0",
    approved_vs_forecast_gp: { approved_gp: "0", forecast_gp: "0" },
    below_floor_deals: [],
    ceo_exceptions_pending: [],
    revenue_expiring_in_90_days: [],
    aged_blockers_by_owner: {},
  };
}
function emptyFinance(): FinanceDashboard {
  return {
    gm_by_sow: [],
    gm_by_geography: {
      US: { revenue: null, cost: null, gm: "0.42" },
      India: { revenue: null, cost: null, gm: "0.55" },
    },
    approved_vs_forecast_vs_actual: {
      approved_gp: "0.45",
      forecast_gp: "0.43",
      actual_gp: null,
    },
    missing_cost_inputs: [],
    exceptions_and_exposure: [],
  };
}
function emptyDeals(): DealListResponse {
  return { items: [], page: 1, size: 100, total: 0 };
}
function emptyRenewals(): RenewalListResponse {
  return { items: [], page: 1, size: 100, total: 0 };
}

function stubEverything() {
  vi.spyOn(apiClient, "getCeoDashboard").mockResolvedValue(emptyCeo());
  vi.spyOn(apiClient, "getFinanceDashboard").mockResolvedValue(emptyFinance());
  vi.spyOn(apiClient, "getDeals").mockResolvedValue(emptyDeals());
  vi.spyOn(apiClient, "listRenewals").mockResolvedValue(emptyRenewals());
}

function renderReports(exportHandler = vi.fn()) {
  render(
    <MemoryRouter initialEntries={["/reports"]}>
      <ReportsPage onExport={exportHandler} />
    </MemoryRouter>,
  );
  return exportHandler;
}

describe("ReportsPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAuthMock.mockReset();
    setUser(["CEO"]);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders all five report tabs", async () => {
    stubEverything();
    renderReports();
    await waitFor(() => {
      expect(screen.getByTestId("tab-portfolio")).toBeInTheDocument();
    });
    expect(screen.getByTestId("tab-margin")).toBeInTheDocument();
    expect(screen.getByTestId("tab-revenue")).toBeInTheDocument();
    expect(screen.getByTestId("tab-renewals")).toBeInTheDocument();
    expect(screen.getByTestId("tab-turnaround")).toBeInTheDocument();
  });

  it("shows the Revenue tab's invoice/cash caveat by default", async () => {
    stubEverything();
    renderReports();
    await waitFor(() => {
      expect(screen.getByTestId("tab-revenue")).toBeInTheDocument();
    });
    await userEvent.click(screen.getByTestId("tab-revenue"));
    const caveat = await screen.findByTestId("revenue-invoice-cash-caveat");
    expect(caveat.textContent).toMatch(/invoice and cash/i);
    expect(caveat.textContent).toMatch(/only when sourced/i);
    expect(caveat.textContent).toMatch(/never combined/i);
    // Both metric tiles surface the "Not sourced" state by default.
    expect(screen.getAllByText(/Not sourced/i).length).toBeGreaterThanOrEqual(2);
  });

  it("Portfolio tab export CSV calls the handler with the right args", async () => {
    stubEverything();
    const onExport = renderReports();
    await waitFor(() => {
      expect(screen.getByTestId("tab-portfolio")).toBeInTheDocument();
    });
    const btn = await screen.findByTestId("export-portfolio-csv");
    await userEvent.click(btn);
    expect(onExport).toHaveBeenCalledTimes(1);
    const args = onExport.mock.calls[0][0];
    expect(args.kind).toBe("portfolio");
    expect(args.format).toBe("csv");
    expect(args.filename).toMatch(/^dealgate-portfolio-\d{4}-\d{2}-\d{2}\.csv$/);
  });

  it("Portfolio tab export PDF calls the handler with kind=portfolio and format=pdf", async () => {
    stubEverything();
    const onExport = renderReports();
    await waitFor(() => {
      expect(screen.getByTestId("tab-portfolio")).toBeInTheDocument();
    });
    const btn = await screen.findByTestId("export-portfolio-pdf");
    await userEvent.click(btn);
    expect(onExport).toHaveBeenCalledTimes(1);
    const args = onExport.mock.calls[0][0];
    expect(args.kind).toBe("portfolio");
    expect(args.format).toBe("pdf");
  });

  it("Margin tab export CSV routes to the margin kind", async () => {
    stubEverything();
    const onExport = renderReports();
    await waitFor(() => {
      expect(screen.getByTestId("tab-margin")).toBeInTheDocument();
    });
    await userEvent.click(screen.getByTestId("tab-margin"));
    const btn = await screen.findByTestId("export-margin-csv");
    await userEvent.click(btn);
    expect(onExport).toHaveBeenCalledTimes(1);
    expect(onExport.mock.calls[0][0].kind).toBe("margin");
  });

  it("Approval turnaround tab degrades to 'No verified source' honestly", async () => {
    stubEverything();
    renderReports();
    await waitFor(() => {
      expect(screen.getByTestId("tab-turnaround")).toBeInTheDocument();
    });
    await userEvent.click(screen.getByTestId("tab-turnaround"));
    expect(await screen.findByText(/No verified source/i)).toBeInTheDocument();
  });
});
