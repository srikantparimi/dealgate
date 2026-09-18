import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import * as authModule from "../auth/AuthProvider";
import { CEOExceptionBriefPage } from "../pages/CEOExceptionBrief";

const EXCEPTION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const OWNER_SUB = "11111111-1111-1111-1111-111111111111";
const CEO_SUB = "22222222-2222-2222-2222-222222222222";

function baseException(
  overrides: Partial<apiClient.CeoException> = {},
): apiClient.CeoException {
  return {
    id: EXCEPTION_ID,
    package_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    brief_json: {
      client: { name: "Acme Widgets", context: "Global manufacturer." },
      scope: "Replace quoting tool.",
      team_summary: "2 US + 4 India, 12 weeks.",
      revenue: { us: "100000", india: "50000", blended: "150000" },
      cost: { us: "70000", india: "20000", blended: "90000" },
      gm: {
        us: { value: "0.30", floor: "0.35", passes: false },
        india: { value: "0.60", floor: "0.50", passes: true },
        blended: { value: "0.40" },
      },
      price_uplift: { us: "5000", india: "0" },
      gross_profit_shortfall_usd: "5000",
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

function stubAuth(sub: string, groups: string[]) {
  vi.spyOn(authModule, "useAuth").mockReturnValue({
    user: {
      sub,
      email: `${sub}@smartek21.com`,
      name: "User",
      groups,
      role: groups[0] ?? "User",
    },
    isAuthenticated: true,
    tokenReady: true,
    login: vi.fn(),
    logout: vi.fn(),
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/ceo-exceptions/${EXCEPTION_ID}`]}>
      <Routes>
        <Route
          path="/ceo-exceptions/:id"
          element={<CEOExceptionBriefPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("CEOExceptionBrief", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the brief with client, scope, GM statuses and shortfall", async () => {
    stubAuth(OWNER_SUB, ["Sales"]);
    vi.spyOn(apiClient, "getCeoException").mockResolvedValue(baseException());
    renderPage();

    expect(
      await screen.findByRole("heading", { name: /CEO exception brief/i }),
    ).toBeInTheDocument();
    // Client + scope panels
    expect(screen.getByTestId("ceo-brief-client")).toHaveTextContent(
      "Global manufacturer",
    );
    // GM rows have PASS / FAIL chips
    const gmTable = screen.getByRole("table", { name: /gross margin/i });
    expect(gmTable).toHaveTextContent("FAIL");
    expect(gmTable).toHaveTextContent("PASS");
    // Shortfall + uplift
    expect(screen.getByText(/Gross-profit shortfall/i)).toBeInTheDocument();
    expect(screen.getAllByText(/\$5,000/).length).toBeGreaterThan(0);
  });

  it("shows an editable rationale for an owner when it is not set yet", async () => {
    stubAuth(OWNER_SUB, ["Sales"]);
    vi.spyOn(apiClient, "getCeoException").mockResolvedValue(baseException());
    const patch = vi
      .spyOn(apiClient, "patchCeoRationale")
      .mockResolvedValue(
        baseException({
          rationale_text: "Strategic customer.",
          rationale_set_by: OWNER_SUB,
        }),
      );

    renderPage();
    const input = await screen.findByTestId("ceo-rationale-input");
    const user = userEvent.setup();
    await user.type(input, "Strategic customer.");
    await user.click(screen.getByRole("button", { name: /save rationale/i }));
    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    expect(patch).toHaveBeenCalledWith(EXCEPTION_ID, {
      rationale_text: "Strategic customer.",
      tidy: false,
    });
  });

  it("hides decision buttons from non-CEO callers", async () => {
    stubAuth(OWNER_SUB, ["Sales"]);
    vi.spyOn(apiClient, "getCeoException").mockResolvedValue(baseException());
    renderPage();
    await screen.findByRole("heading", { name: /CEO exception brief/i });
    expect(screen.queryByTestId("ceo-decision-panel")).not.toBeInTheDocument();
  });

  it("shows decision buttons for the CEO and blocks approve without a rationale", async () => {
    stubAuth(CEO_SUB, ["CEO"]);
    vi.spyOn(apiClient, "getCeoException").mockResolvedValue(baseException());
    renderPage();
    await screen.findByRole("heading", { name: /CEO exception brief/i });
    expect(screen.getByTestId("ceo-decision-panel")).toBeInTheDocument();
    const approveBtn = screen.getByRole("button", { name: /^approve$/i });
    // Missing rationale disables approve — the copy is spelled out too.
    expect(approveBtn).toBeDisabled();
    expect(
      screen.getByText(/A saved rationale is required before you can approve/i),
    ).toBeInTheDocument();
  });

  it("allows the CEO to approve once a rationale is on file", async () => {
    stubAuth(CEO_SUB, ["CEO"]);
    vi.spyOn(apiClient, "getCeoException").mockResolvedValue(
      baseException({ rationale_text: "Strategic customer." }),
    );
    const decision = vi
      .spyOn(apiClient, "postCeoDecision")
      .mockResolvedValue(
        baseException({
          rationale_text: "Strategic customer.",
          decision: "approve",
          conditions_text: null,
          valid_until: null,
        }),
      );
    renderPage();
    await screen.findByTestId("ceo-decision-panel");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^approve$/i }));
    await waitFor(() => expect(decision).toHaveBeenCalledTimes(1));
    expect(decision.mock.calls[0]?.[1].decision).toBe("approve");
  });
});
