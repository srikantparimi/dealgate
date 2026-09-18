/**
 * WeeklyForecast — Delivery lead posts remaining hours per line each
 * week. We assert three story-critical behaviours:
 *
 *  - the resource lines render as an editable table;
 *  - clicking "Save" calls ``POST /forecast/{gmModelId}`` with every row;
 *  - the US GM StatusChip flips ok/block when the API returns a fresh GM.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import type {
  DeliveryGmModel,
  DeliveryLatestResponse,
  ForecastPeriod,
} from "../api/client";
import { WeeklyForecast } from "../pages/WeeklyForecast";

const GM_MODEL_ID = "11111111-1111-1111-1111-111111111111";
const OPP_ID = "22222222-2222-2222-2222-222222222222";
const RL_1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const RL_2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";


function buildGmModel(): DeliveryGmModel {
  return {
    id: GM_MODEL_ID,
    opportunity_id: OPP_ID,
    sow_version_id: null,
    engagement_type: "tm",
    delivery_pattern: "hybrid",
    contingency_pct: null,
    warranty_days: null,
    revenue_us: "600000",
    revenue_india: "200000",
    created_by: null,
    created_at: "2026-09-01T10:00:00Z",
    resource_lines: [
      {
        id: RL_1,
        role: "Engineer",
        seniority: "senior",
        location: "US",
        person_name: "Alice",
        allocation_pct: "1",
        start_date: "2026-03-01",
        end_date: "2026-12-31",
        hours_billable: "1000",
        hourly_bill_rate: "200",
        hourly_cost: "100",
        validated_by: null,
      },
      {
        id: RL_2,
        role: "Engineer",
        seniority: "senior",
        location: "India",
        person_name: "Bob",
        allocation_pct: "1",
        start_date: "2026-03-01",
        end_date: "2026-12-31",
        hours_billable: "1000",
        hourly_bill_rate: "100",
        hourly_cost: "40",
        validated_by: null,
      },
    ],
    cost_lines: [],
    completeness_issues: [],
  };
}


function buildLatest(overrides: Partial<ForecastPeriod> = {}): ForecastPeriod {
  return {
    id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
    gm_model_id: GM_MODEL_ID,
    week_ending: "2026-09-20",
    forecast_lines_json: [
      {
        resource_line_id: RL_1,
        role: "Engineer",
        seniority: "senior",
        location: "US",
        remaining_hours: "500",
        hourly_cost: "100",
        allocation_pct: "1",
      },
    ],
    forecast_revenue: "800000.00",
    forecast_cost_us: "50000.00",
    forecast_cost_india: "20000.00",
    forecast_gm_us: "0.9167",
    forecast_gm_india: "0.9000",
    updated_by: null,
    updated_at: "2026-09-17T12:00:00Z",
    ...overrides,
  };
}


function stubApi(latest: ForecastPeriod | null, history: ForecastPeriod[] = []) {
  vi.spyOn(apiClient, "getLatestDeliveryModel").mockResolvedValue({
    gm_model: buildGmModel(),
  } as DeliveryLatestResponse);
  vi.spyOn(apiClient, "getLatestForecast").mockResolvedValue(latest);
  vi.spyOn(apiClient, "getForecastHistory").mockResolvedValue({
    items: history,
  });
}


describe("WeeklyForecast", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders resource lines with editable remaining hours", async () => {
    stubApi(null);
    render(<WeeklyForecast gmModelId={GM_MODEL_ID} opportunityId={OPP_ID} />);

    await waitFor(() => {
      expect(screen.getByTestId(`remaining-${RL_1}`)).toBeInTheDocument();
      expect(screen.getByTestId(`remaining-${RL_2}`)).toBeInTheDocument();
    });
    expect(screen.getByText(/Alice/)).toBeInTheDocument();
    expect(screen.getByText(/Bob/)).toBeInTheDocument();
  });

  it("saves by calling POST /forecast/{gmModelId} with all lines", async () => {
    stubApi(null);
    const postSpy = vi
      .spyOn(apiClient, "postForecast")
      .mockResolvedValue(buildLatest());

    render(<WeeklyForecast gmModelId={GM_MODEL_ID} opportunityId={OPP_ID} />);

    const user = userEvent.setup();
    const input = await screen.findByTestId(`remaining-${RL_1}`);
    await user.clear(input);
    await user.type(input, "500");

    const input2 = screen.getByTestId(`remaining-${RL_2}`);
    await user.clear(input2);
    await user.type(input2, "400");

    await user.click(screen.getByTestId("save-forecast-btn"));

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledTimes(1);
    });
    const [id, lines] = postSpy.mock.calls[0];
    expect(id).toBe(GM_MODEL_ID);
    expect(lines).toEqual([
      { resource_line_id: RL_1, remaining_hours: "500" },
      { resource_line_id: RL_2, remaining_hours: "400" },
    ]);
  });

  it("StatusChip flips ok/block on GM change", async () => {
    // Start with a passing US GM (91.7%).
    stubApi(buildLatest());
    render(<WeeklyForecast gmModelId={GM_MODEL_ID} opportunityId={OPP_ID} />);

    await waitFor(() => {
      expect(screen.getByTestId("gm-us-chip")).toBeInTheDocument();
    });
    // ok tone → green background (#d1fae5) on the inner StatusChip span.
    const chipOk = screen.getByTestId("gm-us-chip").querySelector("span");
    expect(chipOk).not.toBeNull();
    expect(chipOk).toHaveStyle({ background: "rgb(209, 250, 229)" });
    expect(chipOk).toHaveTextContent(/91\.7%/);

    // Simulate a save that returns a below-floor GM.
    vi.spyOn(apiClient, "postForecast").mockResolvedValue(
      buildLatest({
        forecast_cost_us: "550000.00",
        forecast_gm_us: "0.0833",
      }),
    );

    const user = userEvent.setup();
    await user.click(screen.getByTestId("save-forecast-btn"));

    await waitFor(() => {
      const chip = screen
        .getByTestId("gm-us-chip")
        .querySelector("span");
      expect(chip).not.toBeNull();
      expect(chip).toHaveTextContent(/8\.3%/);
      // block tone → red background (#fee2e2).
      expect(chip).toHaveStyle({ background: "rgb(254, 226, 226)" });
    });
    expect(screen.getByTestId("recovery-toast")).toBeInTheDocument();
  });
});
