/**
 * MarginLab (`/margin-lab`) — Sprint 8 Wave 3 acceptance tests
 * (spec §9 + R14).
 *
 * The tests exercise:
 *
 * - Approved baseline / Current draft / Scenarios selector renders as
 *   tabs on the mode selector.
 * - "Draft · Not approved for commitment" chip is present when the
 *   editable draft mode is active.
 * - Per-geography floor tests render pass/fail badges from the server
 *   (no browser math — MarginCell / MarginBadge just render).
 * - The Export xlsx button calls `exportGmXlsx` (server-owned formula).
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../../api/client";
import type {
  PolicyListResponse,
  RateCardListResponse,
  SandboxResponse,
  SandboxSchema,
} from "../../api/client";
import { MarginLabPage } from "../../pages/v2/MarginLab";

function schema(): SandboxSchema {
  return {
    engagement_type: "staff_aug",
    fields: [
      {
        name: "hours",
        label: "Hours",
        kind: "decimal",
        required: true,
        help: "0",
      },
      {
        name: "bill_rate",
        label: "Bill rate",
        kind: "decimal",
        required: true,
        help: "0",
      },
    ],
  };
}

function rateCards(): RateCardListResponse {
  return {
    items: [
      {
        id: "00000000-0000-0000-0000-000000000rc1",
        effective_from: "2026-01-01",
        published_at: "2026-01-01T00:00:00Z",
        published_by: null,
        notes: null,
        row_count: 5,
        is_active: true,
      },
    ],
    active_id: "00000000-0000-0000-0000-000000000rc1",
  };
}

function policies(): PolicyListResponse {
  return {
    items: [],
    active: {
      id: "00000000-0000-0000-0000-000000000po1",
      effective_from: "2026-01-01",
      us_floor: "0.3500",
      india_floor: "0.5000",
      fx_convention: "fixed_at_sow_date",
      is_default: false,
    },
    allowed_fx_conventions: ["fixed_at_sow_date", "monthly_average"],
  };
}

function sandbox(overrides: Partial<SandboxResponse> = {}): SandboxResponse {
  return {
    engagement_type: "staff_aug",
    revenue_us: "100000",
    cost_us: "60000",
    gm_us: "0.4000",
    revenue_india: "50000",
    cost_india: "20000",
    gm_india: "0.6000",
    gm_blended: "0.4667",
    geography: "Mixed",
    complete: true,
    missing: [],
    policy: {
      us_floor: "0.3500",
      india_floor: "0.5000",
      us_pass: true,
      india_pass: true,
      requires_ceo: false,
      failing: [],
      source: "active",
    },
    min_price_us: "92000",
    min_price_india: "40000",
    policy_version_id: "00000000-0000-0000-0000-000000000po1",
    rate_card_version_id: "00000000-0000-0000-0000-000000000rc1",
    computed_at: "2026-06-10T10:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/margin-lab"]}>
      <MarginLabPage />
    </MemoryRouter>,
  );
}

describe("MarginLabPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, "getGmSchema").mockResolvedValue(schema());
    vi.spyOn(apiClient, "listRateCards").mockResolvedValue(rateCards());
    vi.spyOn(apiClient, "listPolicies").mockResolvedValue(policies());
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the baseline / draft / scenarios selector", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: /Approved baseline/i })).toBeInTheDocument(),
    );
    expect(screen.getByRole("tab", { name: /Current draft/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Scenarios/i })).toBeInTheDocument();
  });

  it("shows the 'Draft · Not approved for commitment' chip in Draft mode", async () => {
    renderPage();
    const chip = await screen.findByTestId("margin-draft-chip");
    expect(chip.textContent ?? "").toMatch(
      /Draft · Not approved for commitment/i,
    );
  });

  it("renders per-geography floor tests from the server response", async () => {
    const user = userEvent.setup();
    vi.spyOn(apiClient, "computeGm").mockResolvedValue(
      sandbox({
        policy: {
          us_floor: "0.3500",
          india_floor: "0.5000",
          us_pass: false,
          india_pass: true,
          requires_ceo: true,
          failing: ["us"],
          source: "active",
        },
      }),
    );

    renderPage();

    // Wait for the schema, then fill and compute.
    await waitFor(() => expect(screen.getByLabelText(/^Hours/i)).toBeInTheDocument());
    await user.type(screen.getByLabelText(/^Hours/i), "1000");
    await user.type(screen.getByLabelText(/^Bill rate/i), "200");
    await user.click(screen.getByRole("button", { name: /Compute margin/i }));

    // The two policy rows are labelled with test-ids per geography.
    await waitFor(() =>
      expect(screen.getByTestId("policy-row-us-floor")).toBeInTheDocument(),
    );
    const us = screen.getByTestId("policy-row-us-floor");
    const india = screen.getByTestId("policy-row-india-floor");
    expect(us.textContent ?? "").toMatch(/Fail/);
    expect(india.textContent ?? "").toMatch(/Pass/);
    // Overall banner says CEO exception required (never green).
    expect(screen.getByText(/CEO exception required/i)).toBeInTheDocument();
  });

  it("Export xlsx button calls exportGmXlsx", async () => {
    const user = userEvent.setup();
    const exportSpy = vi
      .spyOn(apiClient, "exportGmXlsx")
      .mockResolvedValue(new Blob(["xlsx"], { type: "application/octet-stream" }));

    // Stub the DOM download plumbing so the click does not crash jsdom.
    const originalCreate = URL.createObjectURL;
    const originalRevoke = URL.revokeObjectURL;
    (URL as unknown as { createObjectURL: (b: Blob) => string }).createObjectURL =
      () => "blob:mock";
    (URL as unknown as { revokeObjectURL: (u: string) => void }).revokeObjectURL =
      () => undefined;

    try {
      renderPage();
      await waitFor(() =>
        expect(screen.getByLabelText(/Export scenario to xlsx/i)).toBeInTheDocument(),
      );
      await user.click(screen.getByLabelText(/Export scenario to xlsx/i));
      await waitFor(() => expect(exportSpy).toHaveBeenCalledTimes(1));
      const call = exportSpy.mock.calls[0][0];
      expect(call.engagement_type).toBe("staff_aug");
    } finally {
      (URL as unknown as { createObjectURL: (b: Blob) => string }).createObjectURL =
        originalCreate;
      (URL as unknown as { revokeObjectURL: (u: string) => void }).revokeObjectURL =
        originalRevoke;
    }
  });
});
