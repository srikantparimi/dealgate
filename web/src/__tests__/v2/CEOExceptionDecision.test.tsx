/**
 * S9 Wave 2 — CEO exception decision page acceptance tests.
 *
 * Focus areas:
 *   - Geography table renders BOTH components (US + India), never a
 *     single blended row.
 *   - The rationale textarea is the only human input.
 *   - Approve is disabled until a saved rationale of >= 1 sentence.
 *   - Conditional approval requires each condition to have an owner,
 *     due date and evidence.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../../api/client";
import { CEOExceptionDecisionPage } from "../../pages/v2/CEOExceptionDecision";

const EXCEPTION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const PACKAGE_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
const SOW_ID = "550e8400-e29b-41d4-a716-446655440000";

function baseException(
  overrides: Partial<apiClient.CeoException> = {},
): apiClient.CeoException {
  return {
    id: EXCEPTION_ID,
    package_id: PACKAGE_ID,
    brief_json: {
      client: { name: "Northstar Health", context: "Global healthcare." },
      scope: "Replace claims intake.",
      team_summary: "2 US + 4 India, 14 weeks.",
      revenue: { us: "90000", india: "55000", blended: "145000" },
      cost: { us: "65000", india: "30000", blended: "95000" },
      gm: {
        us: { value: "0.278", floor: "0.35", passes: false },
        india: { value: "0.4545", floor: "0.50", passes: false },
        blended: { value: "0.3448" },
      },
      price_uplift: { us: "6500", india: "2500" },
      gross_profit_shortfall_usd: "9000",
      alternatives: ["Shift PM to India"],
      finance_recommendation: "Approve with tighter conditions.",
      delivery_recommendation: "Delivery neutral.",
      rationale: null,
      sources: [],
      model: "stub.ceo_brief.v1",
      prompt_version: "ceo_brief.v1",
    },
    rationale_text: null,
    rationale_tidied_text: null,
    rationale_set_by: null,
    rationale_set_at: null,
    conditions_text: null,
    valid_until: null,
    decision: null,
    decided_by: null,
    decided_at: null,
    drafted_at: "2026-09-18T12:00:00Z",
    ...overrides,
  };
}

function stubList(items: apiClient.CeoException[]) {
  vi.spyOn(apiClient, "listCeoExceptions").mockResolvedValue({ items });
}

function stubGet(e: apiClient.CeoException) {
  vi.spyOn(apiClient, "getCeoException").mockResolvedValue(e);
}

function stubGetPackageMissing() {
  vi.spyOn(apiClient, "getApprovalPackage").mockRejectedValue(
    new apiClient.ApiError(404, {}, "not found"),
  );
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/sows/${SOW_ID}/exception`]}>
      <Routes>
        <Route
          path="/sows/:id/exception"
          element={<CEOExceptionDecisionPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("CEOExceptionDecisionPage (SOW-first)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the Finance panel with both geography components", async () => {
    stubList([baseException()]);
    stubGet(baseException());
    stubGetPackageMissing();

    renderPage();

    await screen.findByRole("heading", { name: /CEO margin exception/i });

    const panel = screen.getByRole("region", { name: "GM summary" });
    expect(within(panel).getByText("27.8%")).toBeInTheDocument();
    expect(within(panel).getByText("45.5%")).toBeInTheDocument();
    expect(within(panel).getAllByRole("meter")).toHaveLength(2);
    expect(within(panel).getByTestId("staffing-floor-summary")).toHaveTextContent("Fails · US, India");
  });

  it("keeps the rationale textarea as the only free-text human input", async () => {
    stubList([baseException()]);
    stubGet(baseException());
    stubGetPackageMissing();

    renderPage();

    await screen.findByTestId("ceo-rationale-input");
    // No other textarea rendered on the page — brief is pre-drafted.
    expect(screen.getAllByRole("textbox")).toEqual(
      expect.arrayContaining([screen.getByTestId("ceo-rationale-input")]),
    );
    // The rationale is a <textarea>, everything else that appears as
    // a textbox belongs to the conditions editor which is only shown
    // once "approve with conditions" is picked. Confirm no other
    // textarea (multiline) is present.
    const textareas = screen
      .getAllByRole("textbox")
      .filter((el) => el.tagName === "TEXTAREA");
    expect(textareas).toHaveLength(1);
    expect(textareas[0]).toBe(screen.getByTestId("ceo-rationale-input"));
  });

  it("disables approve until a full-sentence rationale is saved", async () => {
    stubList([baseException()]);
    stubGet(baseException());
    stubGetPackageMissing();
    const user = userEvent.setup();

    renderPage();

    const submit = await screen.findByTestId("ceo-decision-submit");
    expect(submit).toBeDisabled();

    // A short, non-sentence rationale keeps the button disabled and the
    // Save rationale button too.
    const input = screen.getByTestId("ceo-rationale-input");
    await user.type(input, "short");
    const saveBtn = screen.getByRole("button", { name: /save rationale/i });
    expect(saveBtn).toBeDisabled();
    expect(submit).toBeDisabled();

    // Type a full-sentence rationale. `patchCeoRationale` returns the
    // updated exception so the page can flip rationaleSaved to true.
    await user.clear(input);
    await user.type(
      input,
      "This exception unlocks a $2M downstream managed services renewal.",
    );
    expect(saveBtn).not.toBeDisabled();

    vi.spyOn(apiClient, "patchCeoRationale").mockResolvedValue(
      baseException({
        rationale_text:
          "This exception unlocks a $2M downstream managed services renewal.",
      }),
    );
    await user.click(saveBtn);
    await waitFor(() => expect(submit).not.toBeDisabled());
  });

  it("condition editor requires owner + due + evidence before approve-with-conditions is enabled", async () => {
    stubList([baseException()]);
    stubGet(
      baseException({
        rationale_text: "Strategic renewal that offsets the shortfall.",
      }),
    );
    stubGetPackageMissing();
    const user = userEvent.setup();

    renderPage();

    // Rationale is already saved on load.
    await screen.findByTestId("ceo-decision-submit");
    // Switch to approve-with-conditions.
    await user.click(
      screen.getByLabelText(/approve with conditions/i),
    );

    const submit = screen.getByTestId("ceo-decision-submit");
    expect(submit).toBeDisabled();

    // Add a condition but leave fields empty.
    await user.click(screen.getByRole("button", { name: /add condition/i }));
    expect(submit).toBeDisabled();

    const row = screen.getByTestId("condition-row-c1");
    // Fill only owner + due → still disabled because evidence is empty.
    await user.type(within(row).getByLabelText(/^owner/i), "R. Patel");
    await user.type(
      within(row).getByLabelText(/^due date/i),
      "2026-12-31",
    );
    expect(submit).toBeDisabled();

    // Add evidence — now submit is enabled.
    await user.type(
      within(row).getByLabelText(/^evidence/i),
      "https://intranet/renewal-signal-northstar",
    );
    expect(submit).not.toBeDisabled();
  });

  it("shows an empty state when no pending exception exists for this SOW", async () => {
    stubList([]);
    renderPage();
    await screen.findByText(/No pending CEO exception/i);
  });
});
