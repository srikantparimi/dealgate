import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import type { RenewalRow } from "../api/client";
import { RenewalBoardPage } from "../pages/RenewalBoard";

const OPP = "11111111-1111-1111-1111-111111111111";
const RENEWAL_OPEN = "22222222-2222-2222-2222-222222222222";
const RENEWAL_AT_RISK = "33333333-3333-3333-3333-333333333333";
const RENEWAL_CLOSED = "44444444-4444-4444-4444-444444444444";
const RENEWAL_CHURN = "55555555-5555-5555-5555-555555555555";

function baseRow(overrides: Partial<RenewalRow>): RenewalRow {
  return {
    id: RENEWAL_OPEN,
    opportunity_id: OPP,
    term_end: "2026-12-01",
    trigger_date: "2026-10-02",
    status: "open",
    outcome_summary: null,
    replacement_sow_version_id: null,
    opened_at: "2026-09-17T10:00:00",
    updated_at: "2026-09-17T10:00:00",
    days_until_end: 75,
    hubspot_deal_id: "H-DEAL-1",
    owner_id: OPP,
    client_id: null,
    ...overrides,
  };
}

function stubList(items: RenewalRow[]) {
  vi.spyOn(apiClient, "listRenewals").mockImplementation(async (query) => {
    const status = query?.status;
    const filtered = status ? items.filter((r) => r.status === status) : items;
    return { items: filtered, page: 1, size: 200, total: filtered.length };
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/renewals"]}>
      <RenewalBoardPage />
    </MemoryRouter>,
  );
}

describe("RenewalBoard", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders all four columns with row counts", async () => {
    stubList([
      baseRow({ id: RENEWAL_OPEN, days_until_end: 75 }),
      baseRow({
        id: RENEWAL_AT_RISK,
        days_until_end: 14,
        term_end: "2026-10-01",
        hubspot_deal_id: "H-DEAL-2",
      }),
      baseRow({
        id: RENEWAL_CLOSED,
        status: "closed",
        hubspot_deal_id: "H-DEAL-3",
      }),
      baseRow({
        id: RENEWAL_CHURN,
        status: "churn",
        hubspot_deal_id: "H-DEAL-4",
      }),
    ]);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("renewal-columns")).toBeInTheDocument();
    });

    expect(screen.getByTestId("count-open")).toHaveTextContent("1");
    expect(screen.getByTestId("count-at_risk")).toHaveTextContent("1");
    expect(screen.getByTestId("count-closed")).toHaveTextContent("1");
    expect(screen.getByTestId("count-churn")).toHaveTextContent("1");

    // Rows land in the right buckets.
    const openCol = screen.getByTestId("col-open");
    expect(within(openCol).getByText("H-DEAL-1")).toBeInTheDocument();
    const atRiskCol = screen.getByTestId("col-at_risk");
    expect(within(atRiskCol).getByText("H-DEAL-2")).toBeInTheDocument();
    const closedCol = screen.getByTestId("col-closed");
    expect(within(closedCol).getByText("H-DEAL-3")).toBeInTheDocument();
    const churnCol = screen.getByTestId("col-churn");
    expect(within(churnCol).getByText("H-DEAL-4")).toBeInTheDocument();
  });

  it("opens the edit drawer on row click and saves outcome_summary", async () => {
    const row = baseRow({ days_until_end: 75 });
    stubList([row]);
    const getSpy = vi
      .spyOn(apiClient, "getRenewal")
      .mockResolvedValue(row);
    const patchSpy = vi
      .spyOn(apiClient, "patchRenewal")
      .mockResolvedValue({ ...row, outcome_summary: "Extended 12mo" });

    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId(`row-${RENEWAL_OPEN}`)).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByTestId(`row-${RENEWAL_OPEN}`));

    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith(RENEWAL_OPEN);
    });

    const textarea = await screen.findByTestId("outcome-summary");
    await user.clear(textarea);
    await user.type(textarea, "Extended 12mo");
    await user.selectOptions(screen.getByTestId("status-select"), "extended");
    await user.click(screen.getByTestId("save-renewal"));

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledTimes(1);
    });
    const [id, body] = patchSpy.mock.calls[0];
    expect(id).toBe(RENEWAL_OPEN);
    expect(body).toEqual({
      outcome_summary: "Extended 12mo",
      status: "extended",
    });
  });

  it("shows an empty state when no renewals exist", async () => {
    stubList([]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/No renewals yet/i)).toBeInTheDocument();
    });
  });
});
