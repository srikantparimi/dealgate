/**
 * Settings & controls — Sprint 8 Wave 3 acceptance tests (spec §18).
 *
 * The shell owns the secondary vertical nav; every subsection is a real
 * route. These tests exercise the shell as a black box:
 *
 *   - The nav lists every allowed section for a SystemAdmin.
 *   - Sections the role cannot see are hidden.
 *   - `/settings` (no section) renders the General panel.
 *   - `/settings/rates` renders the rate-card tabs (Current/Scheduled/Archived).
 *   - `/settings/policy` renders the summary + Current/Pending/History tabs.
 *   - `/settings/audit` reuses the existing legacy AuditPage.
 *   - `/settings/system-health` renders the four spec §18 tabs.
 *   - A URL for a section the user is not authorised for renders the honest
 *     "You don't have access…" empty state (spec §4).
 *
 * Network calls are stubbed so the shell renders deterministically.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../../api/client";
import type {
  ActivePolicy,
  AuditListResponse,
  PolicyListResponse,
  PolicyVersionRow,
  RateCardListResponse,
  RateCardVersionSummary,
  UserListResponse,
  UserRow,
  VerifyAuditResponse,
  AdminReplayListResponse,
  AdminReplayHubspotRow,
  AdminReplayIntegrationEventRow,
  AdminReplayNotificationRow,
} from "../../api/client";
import { SettingsShellPage } from "../../pages/v2/SettingsShell";

// -----------------------------------------------------------------------------
// Auth mock so we can flip roles between tests.
// -----------------------------------------------------------------------------

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
// Fixtures — pared-down but shape-accurate.
// -----------------------------------------------------------------------------

function activePolicy(): ActivePolicy {
  return {
    id: null,
    effective_from: null,
    us_floor: "0.3500",
    india_floor: "0.5000",
    fx_convention: "fixed_at_sow_date",
    is_default: true,
  };
}

function emptyPolicies(): PolicyListResponse {
  return {
    items: [] as PolicyVersionRow[],
    active: activePolicy(),
    allowed_fx_conventions: ["fixed_at_sow_date", "monthly_average"],
  };
}

function emptyRateCards(): RateCardListResponse {
  return { items: [] as RateCardVersionSummary[], active_id: null };
}

function emptyUsers(): UserListResponse {
  return {
    items: [] as UserRow[],
    page: 1,
    size: 25,
    total: 0,
    allowed_groups: ["SystemAdmin", "Finance"],
  };
}

function emptyAudit(): AuditListResponse {
  return { items: [], page: 1, size: 25, total: 0 };
}

function emptyReplay<T>(): AdminReplayListResponse<T> {
  return { items: [] as T[], page: 1, size: 25, total: 0 };
}

function stubAllEndpoints() {
  vi.spyOn(apiClient, "getDirectCostCategories").mockResolvedValue({ categories: ["Travel", "Other"] });
  vi.spyOn(apiClient, "listPolicies").mockResolvedValue(emptyPolicies());
  vi.spyOn(apiClient, "listRateCards").mockResolvedValue(emptyRateCards());
  vi.spyOn(apiClient, "listUsers").mockResolvedValue(emptyUsers());
  vi.spyOn(apiClient, "listAudit").mockResolvedValue(emptyAudit());
  vi.spyOn(apiClient, "verifyAudit").mockResolvedValue({
    ok: true,
    first_broken_row: null,
    checked: 0,
    message: "ok",
  } satisfies VerifyAuditResponse);
  vi.spyOn(apiClient, "listAdminReplayHubspotWriteback").mockResolvedValue(
    emptyReplay<AdminReplayHubspotRow>(),
  );
  vi.spyOn(apiClient, "listAdminReplayNotifications").mockResolvedValue(
    emptyReplay<AdminReplayNotificationRow>(),
  );
  vi.spyOn(apiClient, "listAdminReplayIntegrationEvents").mockResolvedValue(
    emptyReplay<AdminReplayIntegrationEventRow>(),
  );
}

function renderAt(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/settings" element={<SettingsShellPage />} />
        <Route path="/settings/:section" element={<SettingsShellPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

// -----------------------------------------------------------------------------

describe("SettingsShellPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAuthMock.mockReset();
    setUser(["SystemAdmin"]);
    stubAllEndpoints();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lists every section in the secondary nav for a SystemAdmin", async () => {
    renderAt("/settings");
    const nav = await screen.findByRole("navigation", {
      name: /Settings sections/i,
    });
    expect(nav).toBeInTheDocument();
    // All eight canonical sections must be reachable.
    for (const label of [
      "General",
      "Rate cards",
      "Margin policy",
      "People & access",
      "Integrations",
      "Data imports",
      "Audit log",
      "System health",
    ]) {
      // The label appears in the nav; some also appear in section headers.
      // Use getAllByText so a duplicate is fine (nav + heading).
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
  });

  it("hides sections that the user's role cannot see", async () => {
    // Sales has no overlap with any Settings requireAny list except… none.
    // Nav should be empty for a role with no admin overlap.
    setUser(["Sales"]);
    renderAt("/settings");
    const nav = await screen.findByRole("navigation", {
      name: /Settings sections/i,
    });
    // "People & access" requires SystemAdmin — not visible to Sales.
    expect(
      nav.textContent?.includes("People & access") ?? false,
    ).toBe(false);
    // Integrations, System health also SystemAdmin-only.
    expect(nav.textContent?.includes("Integrations") ?? false).toBe(false);
    expect(nav.textContent?.includes("System health") ?? false).toBe(false);
  });

  it("defaults to General when no :section is present", async () => {
    renderAt("/settings");
    // The General subsection carries a distinctive workspace-name field.
    await waitFor(() => {
      expect(screen.getByText(/Workspace name/i)).toBeInTheDocument();
    });
    // Governed vs display-preference distinction is spec §18 required copy.
    expect(
      screen.getAllByText(/Display preference|Applies to future records/i)
        .length,
    ).toBeGreaterThan(0);
  });

  it("renders the Rate cards subsection at /settings/rates", async () => {
    renderAt("/settings/rates");
    await waitFor(() => {
      expect(
        screen.getByRole("tab", { name: /Current/i }),
      ).toBeInTheDocument();
    });
    // All three spec tabs are present.
    expect(screen.getByRole("tab", { name: /Scheduled/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Archived/i })).toBeInTheDocument();
  });

  it("renders the Margin policy summary + tabs at /settings/policy", async () => {
    renderAt("/settings/policy");
    await waitFor(() => {
      expect(
        screen.getByRole("tab", { name: /Current policy/i }),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByRole("tab", { name: /Pending changes/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /History/i })).toBeInTheDocument();
    // Active-policy summary card echoes US 35% / India 50% verbatim.
    expect(await screen.findByLabelText(/Active policy summary/i)).toBeInTheDocument();
  });

  it("reuses the existing audit viewer at /settings/audit", async () => {
    renderAt("/settings/audit");
    // The legacy AuditPage renders a "Verify chain" action and an "Audit log"
    // page header.
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Verify chain/i }),
      ).toBeInTheDocument();
    });
  });

  it("renders the four System health tabs at /settings/system-health", async () => {
    renderAt("/settings/system-health");
    await waitFor(() => {
      expect(
        screen.getByRole("tab", { name: /Overview/i }),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByRole("tab", { name: /Failed events/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: /Notification delivery/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: /Reconciliation/i }),
    ).toBeInTheDocument();
  });

  it("renders 'You don't have access' for a section the role cannot see", async () => {
    // Sales has zero admin overlap; navigating to /settings/people must
    // degrade to the empty state per spec §4, not throw or show data.
    setUser(["Sales"]);
    renderAt("/settings/people");
    await waitFor(() => {
      expect(
        screen.getByText(/You don't have access to this section/i),
      ).toBeInTheDocument();
    });
  });
});
