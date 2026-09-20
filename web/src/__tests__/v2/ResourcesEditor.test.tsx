/**
 * Resources editor (S10-08).
 *
 * The rule: the signature decides what an edit costs, not the screen.
 * Unsigned, a plan is a proposal — edit freely, tell nobody. Signed, the
 * margin was part of a decision, so the change is dated, justified, and the
 * approvers are told with both numbers.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  ResourcesEditor,
  stateToRows,
} from "../../pages/v2/sow-workspace/ResourcesEditor";
import * as api from "../../api/client";
import type { SowResourcesState } from "../../api/client";

const OPP = "11111111-1111-1111-1111-111111111111";

function state(over: Partial<SowResourcesState> = {}): SowResourcesState {
  return {
    opportunity_id: OPP,
    gm_model_id: "gm-1",
    engagement_type: "fixed_price",
    is_signed: false,
    editable: true,
    requires_notice_on_change: false,
    resources: [
      {
        role: "Consultant",
        seniority: "Senior",
        location: "US",
        person_name: null,
        utilization_pct: "50",
        hours_billable: "160",
        hourly_bill_rate: "0",
        hourly_cost: "95",
        start_date: "2026-08-25",
        end_date: "2026-09-30",
      },
    ],
    margin: { gm_model_id: "gm-1", gm_blended: "0.42", us_pass: true, india_pass: true },
    ...over,
  };
}

beforeEach(() => vi.restoreAllMocks());

describe("stateToRows", () => {
  it("shows utilization as the percentage it was entered as", () => {
    // The library stores 0.5; a reader should see 50.
    expect(stateToRows(state())[0].allocation_pct).toBe("50");
  });

  it("gives an empty grid a starter row rather than nothing to type into", () => {
    expect(stateToRows(state({ resources: [] }))).toHaveLength(1);
  });
});

describe("ResourcesEditor", () => {
  it("edits freely and quietly before signature", async () => {
    const load = vi.fn().mockResolvedValue(state());
    render(<ResourcesEditor opportunityId={OPP} load={load as never} />);

    expect(await screen.findByText(/not signed yet/i)).toBeInTheDocument();
    // No date or reason demanded, and the button does not threaten a notice.
    expect(screen.queryByLabelText("effective-from")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId("save-resources")).toHaveTextContent("Save"),
    );
    expect(screen.getByTestId("save-resources")).toBeEnabled();
  });

  it("will not save a signed change without a date and a reason", async () => {
    const load = vi
      .fn()
      .mockResolvedValue(state({ is_signed: true, requires_notice_on_change: true }));
    const put = vi.spyOn(api, "putSowResources");

    const user = userEvent.setup();
    render(<ResourcesEditor opportunityId={OPP} load={load as never} />);

    expect(await screen.findByText(/every approver is told/i)).toBeInTheDocument();
    const save = screen.getByTestId("save-resources");
    expect(save).toHaveTextContent("Save & notify");
    // "The staffing changed" with no date or reason is not a notice anyone
    // can act on.
    expect(save).toBeDisabled();

    await user.type(screen.getByLabelText("effective-from"), "2026-10-01");
    expect(screen.getByTestId("save-resources")).toBeDisabled();

    await user.type(screen.getByLabelText("change-reason"), "Consultant rolled off");
    await waitFor(() =>
      expect(screen.getByTestId("save-resources")).toBeEnabled(),
    );
    expect(put).not.toHaveBeenCalled();
  });

  it("reports who was notified and how the margin moved", async () => {
    const load = vi
      .fn()
      .mockResolvedValue(state({ is_signed: true, requires_notice_on_change: true }));
    vi.spyOn(api, "putSowResources").mockResolvedValue({
      gm_model_id: "gm-2",
      previous_gm_model_id: "gm-1",
      requires_notice: true,
      effective_from: "2026-10-01",
      notified: ["delivery", "hr", "finance", "legal"],
      margin_before: { gm_model_id: "gm-1", gm_blended: "0.42" },
      margin_after: { gm_model_id: "gm-2", gm_blended: "0.31" },
    });

    const user = userEvent.setup();
    render(<ResourcesEditor opportunityId={OPP} load={load as never} />);

    await user.type(await screen.findByLabelText("effective-from"), "2026-10-01");
    await user.type(screen.getByLabelText("change-reason"), "Scope moved");
    await user.click(screen.getByTestId("save-resources"));

    const notice = await screen.findByTestId("resources-notice");
    expect(notice).toHaveTextContent("4 approver function(s) notified");
    // Both numbers, so the reader does not have to go and find out whether
    // it mattered.
    expect(notice).toHaveTextContent("42.0%");
    expect(notice).toHaveTextContent("31.0%");
  });

  it("asks for cost, not a bill rate, on a fixed fee", async () => {
    const load = vi.fn().mockResolvedValue(state({ resources: [] }));
    render(<ResourcesEditor opportunityId={OPP} load={load as never} />);
    expect(
      await screen.findByText(/needs hours, a cost rate and dates/i),
    ).toBeInTheDocument();
  });

  it("surfaces a rejected save instead of failing silently", async () => {
    const load = vi.fn().mockResolvedValue(state());
    vi.spyOn(api, "putSowResources").mockRejectedValue(
      new api.ApiError(422, null, "resource_lines must not be empty"),
    );
    const user = userEvent.setup();
    render(<ResourcesEditor opportunityId={OPP} load={load as never} />);
    await user.click(await screen.findByTestId("save-resources"));
    expect(await screen.findByTestId("resources-error")).toHaveTextContent(
      "must not be empty",
    );
  });
});
