import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api/forecast";
import { NextOpportunities } from "../../pages/v2/forecast/NextOpportunities";
import { ForecastPage } from "../../pages/v2/Forecast";

const plan: api.ForecastPlan = {
  id: "plan-a",
  version_id: "v1",
  version: 1,
  account_id: "account-a",
  account_name: "Company X",
  opportunity_id: null,
  source_status: "Local forecast only",
  owner_id: "owner-a",
  title: "Assessment follow-on",
  lifecycle: "needs_review",
  probability: "0.70",
  probability_source: "Owner estimate",
  assumptions: ["Client start unconfirmed"],
  scope_id: "scope-a",
  can_edit_assumptions: true,
  source_evidence: ["Assessment report page 4"],
  job: {
    id: "job-a",
    status: "failed",
    attempts: 2,
    next_attempt_at: "2026-10-02T00:00:00Z",
    last_error: "Missing currency",
  },
};
function mount(row = plan, onSaved = vi.fn()) {
  return render(
    <MemoryRouter>
      <NextOpportunities
        plans={{ items: [row], total: 51, page: 1, size: 50 }}
        onSaved={onSaved}
      />
    </MemoryRouter>,
  );
}
beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "reviseForecastAssumptions").mockResolvedValue({
    id: "plan-a",
    version_id: "v2",
    version: 2,
  });
});
describe("Next opportunities", () => {
  it("opens persisted commercial terms without changing the original draft on cancel", () => {
    const inputs = { component_id: "component", version: "1", source_id: "plan-a", source_version: "v1", workstream_id: "scope-a",
      profile_version: "1", policy_version: "policy", timezone: "UTC", currency: "USD", billing_cadence: null,
      cost_basis: null, costs_confirmed: false, profile: "fixed_assignment", source_evidence: [], staffing: [], costs: [],
      service_start: "2026-11-01", service_end: "2027-04-30", pricing: { total_fee: "420000", allocations: [] } };
    mount({ ...plan, commercial_inputs: inputs });
    fireEvent.click(screen.getByRole("button", { name: "Edit commercial terms" }));
    expect(screen.getByLabelText("Service start")).toHaveValue("2026-11-01");
    expect(screen.getByLabelText("Contract fee")).toHaveValue("420000");
    fireEvent.change(screen.getByLabelText("Contract fee"), { target: { value: "480000" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel commercial edit" }));
    expect(inputs.pricing.total_fee).toBe("420000");
    fireEvent.click(screen.getByRole("button", { name: "Edit commercial terms" }));
    expect(screen.getByLabelText("Contract fee")).toHaveValue("420000");
  });
  it("names the lifecycle selector without including its option text in the label", () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Edit assumptions" }));
    expect(screen.getByLabelText("Planning status")).toHaveValue("needs_review");
    expect(screen.getByRole("combobox", { name: "Planning status" })).toHaveValue("needs_review");
  });
  it("opens the fourth view with the persisted account and financial filters", async () => {
    const period = {
      start: "2026-10-01",
      end_exclusive: "2027-01-01",
      revenue: "0",
      signed: "0",
      potential: "0",
      expected: "0",
    };
    vi.spyOn(api, "getForecastOutlook").mockResolvedValue({
      schema_version: "forecast-outlook-v1",
      as_of: "2026-10-01T00:00:00Z",
      timezone: "UTC",
      currency: "USD",
      scenario: "upside",
      future_quarters: 4,
      current_month: period,
      current_quarter: period,
      future: period,
      quarters: [],
      months: [],
      accounts: [],
      rows: [],
      excluded: [],
      unresolved_sources: [],
      pending_sources: [],
      source_watermark: "watermark",
      scope_label: "Selected total",
      source_count: 0,
      stale: false,
      source_coverage: "Authorized sources",
      legacy_sources_included: false,
      actuals_available: false,
      actuals_basis: "service_schedule",
    });
    vi.spyOn(api, "getForecastPlans").mockResolvedValue({
      items: [plan],
      total: 1,
      page: 2,
      size: 50,
    });
    render(
      <MemoryRouter
        initialEntries={[
          "/forecast?view=opportunities&account_id=account-a&scenario=upside&future_quarters=4&page=2",
        ]}
      >
        <ForecastPage />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("region", { name: "Next opportunities" }),
    ).toHaveTextContent("Assessment follow-on");
    expect(
      screen.getByRole("tab", { name: "Next opportunities" }),
    ).toHaveAttribute("aria-selected", "true");
    expect(api.getForecastPlans).toHaveBeenCalledWith(
      { account_id: "account-a", page: 2, size: 50 },
      expect.any(AbortSignal),
    );
    expect(api.getForecastOutlook).toHaveBeenCalledWith(
      {
        account_id: "account-a",
        scenario: "upside",
        future_quarters: 4,
        as_of: undefined,
      },
      expect.any(AbortSignal),
    );
  });
  it("shows persisted local identity, source evidence and failed worker state without inventing recommendations", () => {
    mount();
    expect(screen.getByText("Local forecast only")).toBeInTheDocument();
    expect(screen.getByText("Assessment report page 4")).toBeInTheDocument();
    expect(screen.getByText("Missing currency")).toBeInTheDocument();
    expect(screen.getByText(/1 of 51/)).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
  it("preserves authoritative deal links and hides controls for read-only users", () => {
    mount({
      ...plan,
      opportunity_id: "deal-a",
      source_status: "Linked CRM deal",
      can_edit_assumptions: false,
    });
    expect(
      screen.getByRole("link", { name: "Open linked deal" }),
    ).toHaveAttribute("href", "/deals/deal-a");
    expect(
      screen.queryByRole("button", { name: "Edit assumptions" }),
    ).not.toBeInTheDocument();
  });
  it("prefills source assumptions and submits only optimistic planning fields, then refreshes", async () => {
    const onSaved = vi.fn();
    mount(plan, onSaved);
    fireEvent.click(screen.getByRole("button", { name: "Edit assumptions" }));
    expect(screen.getByLabelText("Win probability (0 to 1)")).toHaveValue(
      "0.70",
    );
    expect(
      screen.getByRole("button", { name: "Save revision" }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Win probability (0 to 1)"), {
      target: { value: "0.65" },
    });
    fireEvent.change(screen.getByLabelText("Change reason"), {
      target: { value: "Reviewed client timing" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save revision" }));
    await waitFor(() =>
      expect(api.reviseForecastAssumptions).toHaveBeenCalledWith("plan-a", {
        expected_version_id: "v1",
        probability: "0.65",
        probability_source: "Owner estimate",
        assumptions: ["Client start unconfirmed"],
        lifecycle: "needs_review",
        change_reason: "Reviewed client timing",
      }),
    );
    expect(onSaved).toHaveBeenCalledTimes(1);
  });
  it("keeps unsaved edits and shows stale-version rejection", async () => {
    vi.mocked(api.reviseForecastAssumptions).mockRejectedValue(
      new Error("409: Plan version changed; refresh before saving"),
    );
    const onSaved = vi.fn();
    mount(plan, onSaved);
    fireEvent.click(screen.getByRole("button", { name: "Edit assumptions" }));
    fireEvent.change(screen.getByLabelText("Assumptions"), {
      target: { value: "Unsaved revised assumption" },
    });
    fireEvent.change(screen.getByLabelText("Change reason"), {
      target: { value: "Reviewed client timing" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save revision" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("409");
    expect(screen.getByLabelText("Assumptions")).toHaveValue(
      "Unsaved revised assumption",
    );
    expect(onSaved).not.toHaveBeenCalled();
  });
  it("shows an honest empty state", () => {
    render(
      <MemoryRouter>
        <NextOpportunities
          plans={{ items: [], total: 0, page: 1, size: 50 }}
          onSaved={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(
      screen.getByText("No planning opportunities in this scope."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Edit assumptions" }),
    ).not.toBeInTheDocument();
  });
});
