import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import * as authModule from "../auth/AuthProvider";
import { LegacyImportPage } from "../pages/LegacyImport";
import { LegacyReconciliationPage } from "../pages/LegacyReconciliation";

const BATCH_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";

function stubAuth(groups: string[] = ["Finance"]) {
  vi.spyOn(authModule, "useAuth").mockReturnValue({
    user: {
      sub: "user-id",
      email: "finance@smartek21.com",
      name: "Finance",
      groups,
      role: groups[0] ?? "User",
    },
    isAuthenticated: true,
    tokenReady: true,
    login: vi.fn(),
    logout: vi.fn(),
  });
}

describe("LegacyImportPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    stubAuth();
    vi.spyOn(apiClient, "createLegacyBatch").mockResolvedValue({
      id: BATCH_ID,
      uploaded_by: "user-id",
      status: "uploading",
      sow_count: 0,
      resource_line_count: 0,
      errors: null,
      approved_by: null,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the wizard with the SOW step by default", async () => {
    render(
      <MemoryRouter initialEntries={["/legacy/import"]}>
        <LegacyImportPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Drop legacy SOW PDFs/i }),
      ).toBeInTheDocument();
    });
    // The rollout rule reminder is in the subtitle.
    expect(
      screen.getByText(/approval not evidenced/i),
    ).toBeInTheDocument();
    // Empty-state hint for the staging table.
    expect(screen.getByText(/No files yet/i)).toBeInTheDocument();
  });

  it("shows both wizard steps in the header", async () => {
    render(
      <MemoryRouter initialEntries={["/legacy/import"]}>
        <LegacyImportPage />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText("Upload SOW PDFs")).toBeInTheDocument();
      expect(screen.getByText("Import Excel")).toBeInTheDocument();
    });
  });
});

describe("LegacyReconciliationPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    stubAuth();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders matched + unmatched + gm sections", async () => {
    vi.spyOn(apiClient, "getLegacyReconciliation").mockResolvedValue({
      batch_id: BATCH_ID,
      status: "reviewing",
      matched: [
        {
          sow_id: "sow-1",
          sow_ref: "SOW-A",
          filename: "a.pdf",
          gm_model_id: "gm-1",
          line_count: 3,
          gm_us: "0.4",
          gm_india: "0.5",
          below_floor: false,
          failing: [],
          complete: true,
        },
      ],
      unmatched_sows: [
        { sow_id: "sow-2", sow_ref: "SOW-B", filename: "b.pdf" },
      ],
      orphaned_resource_lines: [],
      project_gm: [
        {
          sow_ref: "SOW-A",
          revenue_us: "20000",
          revenue_india: "10500",
          cost_us: "12000",
          cost_india: "4000",
          gm_us: "0.4",
          gm_india: "0.619",
          below_floor: false,
          failing: [],
          complete: true,
        },
      ],
      below_floor: [],
    });

    render(
      <MemoryRouter initialEntries={[`/legacy/reconciliation/${BATCH_ID}`]}>
        <Routes>
          <Route
            path="/legacy/reconciliation/:batchId"
            element={<LegacyReconciliationPage />}
          />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/Per-project GM/i)).toBeInTheDocument();
    });
    // SOW-A appears in both the GM table and matched section — assert on any.
    expect(screen.getAllByText("SOW-A").length).toBeGreaterThan(0);
    expect(screen.getByText("SOW-B")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Approve reconciliation/i })).toBeInTheDocument();
  });

  it("hides the approve button for non-Finance users", async () => {
    stubAuth(["Sales"]);
    vi.spyOn(apiClient, "getLegacyReconciliation").mockResolvedValue({
      batch_id: BATCH_ID,
      status: "reviewing",
      matched: [],
      unmatched_sows: [],
      orphaned_resource_lines: [],
      project_gm: [],
      below_floor: [],
    });

    render(
      <MemoryRouter initialEntries={[`/legacy/reconciliation/${BATCH_ID}`]}>
        <Routes>
          <Route
            path="/legacy/reconciliation/:batchId"
            element={<LegacyReconciliationPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText(/Per-project GM/i)).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("button", { name: /Approve reconciliation/i }),
    ).not.toBeInTheDocument();
  });
});
