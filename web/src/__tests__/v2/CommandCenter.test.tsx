/**
 * Command center — Sprint 8 Wave 2 acceptance tests (spec §5 + §23).
 *
 * These are the flagship-page smoke tests. Every network call is mocked
 * so the tests are deterministic; the page is exercised as a black box
 * through the DOM. Rules exercised:
 *
 * - Executive banner renders the editorial title verbatim and the hero
 *   CTA links to /sows (spec §5 item 1).
 * - Four Metrics with the exact labels called out in the agent brief.
 * - A CEO-exception payload renders the priority-signal card and its
 *   href points at /sows/:package_id/exception (spec §5 item 2 +
 *   agent-brief routing rule).
 * - Pipeline table exposes separate NDA and MSA column headers
 *   (spec §5 item 3 + §7 — never a combined "Contracts" checkbox).
 * - Approval preview renders three lane headers (spec §5 item 4).
 * - Delivery economics surfaces both US and India floor labels
 *   (spec §5 item 5).
 * - Loading, error and empty states are honest, not fake zeros
 *   (spec §4 state copy).
 */

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../../api/client";
import type {
  AgreementListResponse,
  ApprovalPackageListResponse,
  CeoDashboard,
  ClientListResponse,
  DealListResponse,
  FinanceDashboard,
  RenewalListResponse,
  SalesDashboard,
} from "../../api/client";
import { CommandCenterPage } from "../../pages/v2/CommandCenter";

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

// -----------------------------------------------------------------------------
// Fixture builders — pared-down but shape-accurate.
// -----------------------------------------------------------------------------

function emptyDeals(): DealListResponse {
  return { items: [], page: 1, size: 25, total: 0 };
}
function emptyClients(): ClientListResponse {
  return { items: [], page: 1, size: 25, total: 0 };
}
function emptyAgreements(): AgreementListResponse {
  return { items: [], allowed_states: [] };
}
function emptyRenewals(): RenewalListResponse {
  return { items: [], page: 1, size: 25, total: 0 };
}
function emptyPackages(): ApprovalPackageListResponse {
  return { items: [], page: 1, size: 10, total: 0 };
}
function emptyCeo(): CeoDashboard {
  return {
    pipeline_value: "1250000",
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
function emptySales(): SalesDashboard {
  return {
    my_deals: [],
    next_client_actions: [],
    missing_contracts: [],
    adviser_estimates: [],
    approval_statuses: [],
  };
}

function stubEverything(overrides: {
  ceo?: CeoDashboard | Error;
  sales?: SalesDashboard;
  finance?: FinanceDashboard;
  deals?: DealListResponse;
  clients?: ClientListResponse;
  agreements?: AgreementListResponse;
  renewals?: RenewalListResponse;
  packages?: ApprovalPackageListResponse;
  ceoPackages?: ApprovalPackageListResponse;
} = {}) {
  const ceo = overrides.ceo;
  if (ceo instanceof Error) {
    vi.spyOn(apiClient, "getCeoDashboard").mockRejectedValue(ceo);
  } else {
    vi.spyOn(apiClient, "getCeoDashboard").mockResolvedValue(ceo ?? emptyCeo());
  }
  vi.spyOn(apiClient, "getSalesDashboard").mockResolvedValue(
    overrides.sales ?? emptySales(),
  );
  vi.spyOn(apiClient, "getFinanceDashboard").mockResolvedValue(
    overrides.finance ?? emptyFinance(),
  );
  vi.spyOn(apiClient, "getDeals").mockResolvedValue(
    overrides.deals ?? emptyDeals(),
  );
  vi.spyOn(apiClient, "listClients").mockResolvedValue(
    overrides.clients ?? emptyClients(),
  );
  vi.spyOn(apiClient, "listAgreements").mockResolvedValue(
    overrides.agreements ?? emptyAgreements(),
  );
  vi.spyOn(apiClient, "listRenewals").mockResolvedValue(
    overrides.renewals ?? emptyRenewals(),
  );
  vi.spyOn(apiClient, "listApprovalPackages").mockImplementation((q) => {
    if (q?.status === "pending_ceo_exception") {
      return Promise.resolve(overrides.ceoPackages ?? emptyPackages());
    }
    return Promise.resolve(overrides.packages ?? emptyPackages());
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/command"]}>
      <Routes>
        <Route path="/command" element={<CommandCenterPage />} />
        <Route path="/sows" element={<div>SOWs page</div>} />
        <Route
          path="/sows/:id/exception"
          element={<div>Exception decision</div>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("CommandCenterPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAuthMock.mockReset();
    setUser(["CEO"]);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the executive banner title and hero CTA linking to /sows", async () => {
    stubEverything();
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /Every commitment\. In view\./i }),
      ).toBeInTheDocument();
    });
    const cta = screen.getByRole("link", { name: /Open approval pipeline/i });
    expect(cta).toBeInTheDocument();
    expect(cta.getAttribute("href")).toBe("/sows");
  });

  it("renders the four executive Metrics with the expected labels", async () => {
    stubEverything();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/Open pipeline/i)).toBeInTheDocument();
    });
    expect(
      screen.getByText(/SOW packages in progress/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Clients with agreement gaps/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/CEO decisions pending/i)).toBeInTheDocument();
  });

  it("renders a CEO-exception priority signal that navigates to /sows/:pkg/exception", async () => {
    const pkgId = "00000000-0000-0000-0000-000000000abc";
    const excId = "00000000-0000-0000-0000-000000000ex1";
    stubEverything({
      ceo: {
        ...emptyCeo(),
        ceo_exceptions_pending: [
          {
            id: excId,
            package_id: pkgId,
            drafted_at: "2026-09-15T10:00:00Z",
            has_rationale: true,
          },
        ],
      },
    });
    renderPage();

    const signal = await screen.findByTestId("signal-ceo-exception");
    expect(signal).toBeInTheDocument();
    // Whole card is a link — the anchor href is the source of truth.
    expect(signal.getAttribute("href")).toBe(`/sows/${pkgId}/exception`);
    expect(signal.textContent).toMatch(/CEO exception/i);
  });

  it("renders a pipeline table with separate NDA and MSA column headers", async () => {
    stubEverything({
      clients: {
        items: [
          {
            id: "c1",
            name: "Acme Corp",
            hubspot_company_id: null,
            coverage_state: "gap",
            opportunity_count: 1,
            owner_ids: [],
            owners: [],
            sources: [],
          },
        ],
        page: 1,
        size: 25,
        total: 1,
      },
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Acme Corp")).toBeInTheDocument();
    });
    // Distinct NDA and MSA columns — never a combined "Contracts" cell.
    expect(
      screen.getByRole("columnheader", { name: /^NDA$/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: /^MSA$/i }),
    ).toBeInTheDocument();
  });

  it("renders three SOW approval lane headers", async () => {
    stubEverything();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/Scope & GM/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Functional review/i)).toBeInTheDocument();
    // "CEO exception" appears in the banner and the lane header; grabbing
    // the lane's aria-label narrows it down.
    expect(
      screen.getByRole("region", { name: /^CEO exception$/i }),
    ).toBeInTheDocument();
  });

  it("delivery economics surfaces the approved / forecast / floor legend", async () => {
    stubEverything();
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByRole("region", { name: /Delivery economics/i }),
      ).toBeInTheDocument();
    });
    // The prototype legend labels the three series so the eye can decode
    // the two bars + floor line without hovering.
    expect(screen.getByText(/Approved GM/i)).toBeInTheDocument();
    expect(screen.getByText(/Forecast final GM/i)).toBeInTheDocument();
    expect(screen.getByText(/Policy floor/i)).toBeInTheDocument();
  });

  it("renders skeletons while the page is loading", () => {
    // Return promises that never resolve to lock the loading state.
    const never = new Promise(() => undefined);
    vi.spyOn(apiClient, "getCeoDashboard").mockReturnValue(never as never);
    vi.spyOn(apiClient, "getSalesDashboard").mockReturnValue(never as never);
    vi.spyOn(apiClient, "getFinanceDashboard").mockReturnValue(never as never);
    vi.spyOn(apiClient, "getDeals").mockReturnValue(never as never);
    vi.spyOn(apiClient, "listClients").mockReturnValue(never as never);
    vi.spyOn(apiClient, "listAgreements").mockReturnValue(never as never);
    vi.spyOn(apiClient, "listRenewals").mockReturnValue(never as never);
    vi.spyOn(apiClient, "listApprovalPackages").mockReturnValue(never as never);
    renderPage();
    // No banner heading is present yet because loader is pending.
    expect(
      screen.queryByRole("heading", { name: /Every commitment/i }),
    ).not.toBeInTheDocument();
  });

  it("keeps the board up when one module fails, and says which", async () => {
    // This used to assert the opposite — that any non-403 failure rendered a
    // full-page ErrorState. All ten calls share one Promise.all, so a single
    // broken endpoint blanked nine healthy ones: when GET /deals started
    // 500ing on SOW-first opportunities, the whole command centre went dark.
    // The file's own header promises "errors in one module never hide
    // healthy ones"; now it is true.
    vi.spyOn(apiClient, "getFinanceDashboard").mockRejectedValue(
      new Error("boom"),
    );
    vi.spyOn(apiClient, "getCeoDashboard").mockResolvedValue(emptyCeo());
    vi.spyOn(apiClient, "getSalesDashboard").mockResolvedValue(emptySales());
    vi.spyOn(apiClient, "getDeals").mockResolvedValue(emptyDeals());
    vi.spyOn(apiClient, "listClients").mockResolvedValue(emptyClients());
    vi.spyOn(apiClient, "listAgreements").mockResolvedValue(emptyAgreements());
    vi.spyOn(apiClient, "listRenewals").mockResolvedValue(emptyRenewals());
    vi.spyOn(apiClient, "listApprovalPackages").mockResolvedValue(
      emptyPackages(),
    );
    renderPage();

    // The page renders.
    await waitFor(() => {
      expect(
        screen.queryByText(/We couldn't load the command center/i),
      ).not.toBeInTheDocument();
    });

    // And the gap is declared rather than passing as "nothing to do here".
    const banner = await screen.findByTestId("partial-failures");
    expect(banner).toHaveTextContent("1 section(s) could not be loaded");
    expect(banner).toHaveTextContent("Finance dashboard");
    expect(banner).toHaveTextContent("boom");
  });

  it("renders 'Unavailable' when Pipeline value is missing (non-CEO role)", async () => {
    // Non-CEO role must never call /dashboards/ceo (agent brief).
    setUser(["Sales"]);
    const ceoSpy = vi.spyOn(apiClient, "getCeoDashboard");
    stubEverything();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/Open pipeline/i)).toBeInTheDocument();
    });
    // Metric value degrades honestly.
    const pipelineTile = screen.getByText(/Open pipeline/i).closest("a");
    expect(pipelineTile?.textContent ?? "").toMatch(/Unavailable/);
    expect(ceoSpy).not.toHaveBeenCalled();
  });

  it("shows an honest priority-signals empty state when nothing is urgent", async () => {
    stubEverything();
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByText(
          /No exceptions, MSA signatures or renewals are urgent right now/i,
        ),
      ).toBeInTheDocument();
    });
  });
});
