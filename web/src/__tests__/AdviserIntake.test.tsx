import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import * as authModule from "../auth/AuthProvider";
import { AdviserIntakePage } from "../pages/AdviserIntake";

const OWNER = "11111111-1111-1111-1111-111111111111";

const estimate: apiClient.AdviserEstimate = {
  kind: "estimate",
  id: "22222222-2222-2222-2222-222222222222",
  submitted_at: "2026-09-18T12:00:00Z",
  submitted_by: OWNER,
  label: "Indicative estimate, requires Delivery and Finance validation",
  scope: "Replace bespoke quoting tool with a modern app.",
  confidence: "medium",
  reasons: ["Team shape is typical.", "Hours reflect a 12-week baseline."],
  team: [
    {
      role: "Solution Architect",
      seniority: "Senior",
      location: "US",
      hours: "120",
      allocation_pct: "0.5",
      cost_low: "7200",
      cost_base: "9000",
      cost_high: "10800",
      is_sentinel: false,
    },
    {
      role: "Engineer",
      seniority: "Senior",
      location: "India",
      hours: "480",
      allocation_pct: "1",
      cost_low: "19200",
      cost_base: "24000",
      cost_high: "28800",
      is_sentinel: false,
    },
    {
      role: "Engineer",
      seniority: "Mid",
      location: "India",
      hours: "480",
      allocation_pct: "1",
      cost_low: "12000",
      cost_base: "15360",
      cost_high: "19200",
      is_sentinel: false,
    },
  ],
  cost_low: "38400",
  cost_base: "48360",
  cost_high: "58800",
  options: [
    {
      key: "us_only",
      label: "US-only",
      cost_low: "7200",
      cost_base: "9000",
      cost_high: "10800",
      min_price: "0",
      floor_applied: "0.35",
      eligible: false,
    },
    {
      key: "india_only",
      label: "India-only",
      cost_low: "31200",
      cost_base: "39360",
      cost_high: "48000",
      min_price: "0",
      floor_applied: "0.5",
      eligible: false,
    },
    {
      key: "mixed",
      label: "Mixed",
      cost_low: "38400",
      cost_base: "48360",
      cost_high: "58800",
      min_price: "96720",
      floor_applied: "0.5",
      eligible: true,
    },
  ],
  sources: [],
  model: "stub.adviser.v1",
  prompt_version: "adviser.v1",
  inputs: { client_name: "Acme" },
  rate_card_version_id: null,
  has_sentinel_costs: false,
  reviewer_id: null,
  reviewed_at: null,
};

const questions: apiClient.AdviserQuestions = {
  kind: "questions",
  questions: [
    "What business outcome does the client want in the first 90 days?",
    "Which existing systems must this integrate with?",
  ],
  note: "Not enough signal to draft a team.",
  label: "Indicative estimate, requires Delivery and Finance validation",
  model: "stub.adviser.v1",
  prompt_version: "adviser.v1",
  sources: [],
};

function stubAuth(groups: string[] = ["Marketing"]) {
  vi.spyOn(authModule, "useAuth").mockReturnValue({
    user: {
      sub: OWNER,
      email: "owner@smartek21.com",
      name: "Owner",
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
    <MemoryRouter initialEntries={["/adviser/new"]}>
      <AdviserIntakePage />
    </MemoryRouter>,
  );
}

describe("AdviserIntake", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    stubAuth();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the intake form with the required label", () => {
    renderPage();
    expect(screen.getByLabelText("Client name")).toBeInTheDocument();
    expect(screen.getByLabelText("Problem statement")).toBeInTheDocument();
    // The mandatory label is shown verbatim (§15 risk mitigation).
    expect(screen.getAllByText(
      "Indicative estimate, requires Delivery and Finance validation",
    ).length).toBeGreaterThan(0);
  });

  it("renders an estimate card on the happy path", async () => {
    const create = vi
      .spyOn(apiClient, "createAdviserEstimate")
      .mockResolvedValue(estimate);
    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Client name"), "Acme");
    await user.type(
      screen.getByLabelText("Problem statement"),
      "Replace a bespoke quoting tool with a modern app across three regions.",
    );
    await user.click(screen.getByRole("button", { name: /draft estimate/i }));

    await waitFor(() => {
      expect(create).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByTestId("adviser-estimate")).toBeInTheDocument();
    // Team table renders (uses aria-label="Proposed team"). Cost card
    // renders one of the base numbers we passed in.
    expect(screen.getByRole("table", { name: /proposed team/i })).toBeInTheDocument();
    expect(screen.getByText(/^\$48,360$/)).toBeInTheDocument();
    // "Send to Presales" button is present; NO "Export PDF" button.
    expect(
      screen.getByRole("button", { name: /send to presales/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /export pdf/i }),
    ).not.toBeInTheDocument();
  });

  it("renders clarifying questions when the API returns a thin intake response", async () => {
    vi.spyOn(apiClient, "createAdviserEstimate").mockResolvedValue(questions);
    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Client name"), "Mystery Co");
    await user.type(screen.getByLabelText("Problem statement"), "Help.");
    await user.click(screen.getByRole("button", { name: /draft estimate/i }));

    expect(await screen.findByTestId("adviser-questions")).toBeInTheDocument();
    expect(
      screen.getByText(/What business outcome/i),
    ).toBeInTheDocument();
    // Estimate card must NOT render on the questions path.
    expect(screen.queryByTestId("adviser-estimate")).not.toBeInTheDocument();
  });
});
