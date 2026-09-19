/**
 * DeliveryModelBuilder — schema-driven form + live preview + save.
 *
 * Backend owns all math (blueprint §2). These tests mock the API client and
 * assert the page (a) mounts an empty grid + panel, (b) debounces a call
 * to previewDeliveryModel when the user edits a row, and (c) POSTs to
 * saveDeliveryModelVersion on click and surfaces the new version id.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import type {
  DeliveryLatestResponse,
  DeliveryPreviewResponse,
  DeliverySaveResponse,
} from "../api/client";
import { DeliveryModelBuilder } from "../pages/DeliveryModelBuilder";

const OPP_ID = "00000000-0000-0000-0000-000000000001";
const NEW_MODEL_ID = "11111111-1111-1111-1111-111111111111";

const emptyLatest: DeliveryLatestResponse = { gm_model: null };

function samplePreviewResponse(): DeliveryPreviewResponse {
  return {
    engagement_type: "fixed_price",
    computed: {
      revenue_us: "90000",
      cost_us: "65000",
      gm_us: "0.2778",
      revenue_india: "55000",
      cost_india: "30000",
      gm_india: "0.4545",
      gm_blended: "0.3448",
      geography: "Mixed",
      complete: true,
      missing: [],
      min_price_us: "100000",
      min_price_india: "60000",
      policy: {
        us_floor: "0.35",
        india_floor: "0.5",
        us_pass: false,
        india_pass: false,
        requires_ceo: true,
        failing: ["US", "India"],
      },
      computed_at: "2026-09-17T00:00:00Z",
    },
    warnings: { capacity: [], hr: [] },
  };
}

function sampleSaveResponse(): DeliverySaveResponse {
  return {
    gm_model: {
      id: NEW_MODEL_ID,
      opportunity_id: OPP_ID,
      sow_version_id: null,
      engagement_type: "fixed_price",
      delivery_pattern: null,
      contingency_pct: null,
      warranty_days: null,
      revenue_us: "90000",
      revenue_india: "55000",
      created_by: null,
      created_at: "2026-09-17T00:00:00Z",
      resource_lines: [],
      cost_lines: [],
      completeness_issues: [],
    },
    warnings: { capacity: [], hr: [] },
  };
}

describe("DeliveryModelBuilder", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.restoreAllMocks();
    vi.spyOn(apiClient, "getLatestDeliveryModel").mockResolvedValue(emptyLatest);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("renders empty state until a resource is added", async () => {
    render(<DeliveryModelBuilder opportunityId={OPP_ID} />);
    await waitFor(() => {
      expect(screen.getByLabelText("Engagement type")).toBeInTheDocument();
    });
    expect(screen.getByText(/Live result/i)).toBeInTheDocument();
  });

  it("adds a row and posts to previewDeliveryModel (debounced)", async () => {
    const preview = vi
      .spyOn(apiClient, "previewDeliveryModel")
      .mockResolvedValue(samplePreviewResponse());
    render(<DeliveryModelBuilder opportunityId={OPP_ID} />);
    await waitFor(() =>
      expect(screen.getByLabelText("Engagement type")).toBeInTheDocument(),
    );

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(screen.getByTestId("add-us-btn"));
    await act(async () => {
      vi.advanceTimersByTime(400);
    });
    await waitFor(() => expect(preview).toHaveBeenCalled());
    // Result panel renders the returned GM values.
    await waitFor(() => {
      expect(screen.getByTestId("gm-us").textContent).toContain("27.78%");
    });
    expect(screen.getByTestId("gm-india").textContent).toContain("45.45%");
    expect(screen.getByTestId("ceo-required")).toBeInTheDocument();
  });

  it("renders capacity + HR warnings inline under the row", async () => {
    vi.spyOn(apiClient, "previewDeliveryModel").mockResolvedValue({
      ...samplePreviewResponse(),
      warnings: {
        capacity: [
          {
            index: 0,
            severity: "amber",
            code: "capacity_conflict",
            message: "Alice would be allocated 200%",
          },
        ],
        hr: [
          {
            index: 0,
            severity: "red",
            code: "hr_lead_time",
            message: "starts in 10 day(s); HR needs 45",
          },
        ],
      },
    });
    render(<DeliveryModelBuilder opportunityId={OPP_ID} />);
    await waitFor(() =>
      expect(screen.getByLabelText("Engagement type")).toBeInTheDocument(),
    );

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(screen.getByTestId("add-us-btn"));
    await act(async () => {
      vi.advanceTimersByTime(400);
    });
    await waitFor(() =>
      expect(screen.getByTestId("warnings-row-0")).toBeInTheDocument(),
    );
    const warningsCell = screen.getByTestId("warnings-row-0");
    expect(warningsCell.textContent).toContain("Alice");
    expect(warningsCell.textContent).toContain("HR needs 45");
  });

  it("save calls saveDeliveryModelVersion and shows the new version id", async () => {
    vi.spyOn(apiClient, "previewDeliveryModel").mockResolvedValue(samplePreviewResponse());
    const save = vi
      .spyOn(apiClient, "saveDeliveryModelVersion")
      .mockResolvedValue(sampleSaveResponse());
    render(<DeliveryModelBuilder opportunityId={OPP_ID} />);
    await waitFor(() =>
      expect(screen.getByLabelText("Engagement type")).toBeInTheDocument(),
    );

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(screen.getByTestId("add-us-btn"));
    await act(async () => {
      vi.advanceTimersByTime(400);
    });

    await user.click(screen.getByTestId("save-btn"));
    await waitFor(() => expect(save).toHaveBeenCalled());
    expect(save.mock.calls[0][0]).toBe(OPP_ID);
    await waitFor(() =>
      expect(screen.getByTestId("save-toast")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("save-toast").textContent).toContain(
      NEW_MODEL_ID.slice(0, 8),
    );
  });

  // --- S7 wave 2: WBS phases + reusable templates -----------------------

  it("renders the phases section and adds a phase via + Add phase", async () => {
    render(<DeliveryModelBuilder opportunityId={OPP_ID} />);
    await waitFor(() =>
      expect(screen.getByTestId("phases-section")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("phases-empty")).toBeInTheDocument();

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(screen.getByTestId("add-phase-btn"));
    await waitFor(() =>
      expect(screen.getByTestId("phase-block-0")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("phase-name-0")).toHaveValue("Phase 1");
    // Add second phase — the up/down buttons enable.
    await user.click(screen.getByTestId("add-phase-btn"));
    await waitFor(() =>
      expect(screen.getByTestId("phase-block-1")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("phase-down-0")).not.toBeDisabled();
    expect(screen.getByTestId("phase-up-1")).not.toBeDisabled();
  });

  it("reorders phases via arrow buttons (local swap)", async () => {
    render(<DeliveryModelBuilder opportunityId={OPP_ID} />);
    await waitFor(() =>
      expect(screen.getByTestId("phases-section")).toBeInTheDocument(),
    );
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(screen.getByTestId("add-phase-btn"));
    await user.click(screen.getByTestId("add-phase-btn"));
    // Rename the second one so we can identify the swap.
    const secondName = screen.getByTestId("phase-name-1");
    await user.clear(secondName);
    await user.type(secondName, "Build");

    await user.click(screen.getByTestId("phase-up-1"));
    // After swap, position 0 should now be "Build".
    await waitFor(() =>
      expect(screen.getByTestId("phase-name-0")).toHaveValue("Build"),
    );
  });

  it("Save as template opens the modal and posts on submit", async () => {
    vi.spyOn(apiClient, "previewDeliveryModel").mockResolvedValue(
      samplePreviewResponse(),
    );
    vi.spyOn(apiClient, "saveDeliveryModelVersion").mockResolvedValue(
      sampleSaveResponse(),
    );
    const saveTpl = vi
      .spyOn(apiClient, "saveDeliveryTemplate")
      .mockResolvedValue({
        template: {
          id: "aaaa1111-1111-1111-1111-111111111111",
          name: "Std FP",
          engagement_type: "fixed_price",
          created_by: null,
          created_at: null,
          updated_at: null,
          active: true,
          phase_count: 0,
          resource_line_count: 0,
          cost_line_count: 0,
        },
      });
    render(<DeliveryModelBuilder opportunityId={OPP_ID} />);
    await waitFor(() =>
      expect(screen.getByTestId("save-template-btn")).toBeInTheDocument(),
    );
    // Button starts disabled — no saved version yet.
    expect(screen.getByTestId("save-template-btn")).toBeDisabled();

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    // Save first, then the template button enables.
    await user.click(screen.getByTestId("add-us-btn"));
    await act(async () => {
      vi.advanceTimersByTime(400);
    });
    await user.click(screen.getByTestId("save-btn"));
    await waitFor(() =>
      expect(screen.getByTestId("save-toast")).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByTestId("save-template-btn")).not.toBeDisabled(),
    );

    await user.click(screen.getByTestId("save-template-btn"));
    await waitFor(() =>
      expect(screen.getByTestId("save-template-modal")).toBeInTheDocument(),
    );
    const nameInput = screen.getByTestId("template-name-input");
    await user.type(nameInput, "Std FP");
    await user.click(screen.getByTestId("template-save-btn"));

    await waitFor(() => expect(saveTpl).toHaveBeenCalled());
    expect(saveTpl.mock.calls[0][0]).toEqual({
      gm_model_id: NEW_MODEL_ID,
      name: "Std FP",
    });
  });

  it("Load template opens the picker and seeds on click", async () => {
    const list = vi
      .spyOn(apiClient, "listDeliveryTemplates")
      .mockResolvedValue({
        items: [
          {
            id: "bbbb2222-2222-2222-2222-222222222222",
            name: "Discovery + Build",
            engagement_type: "fixed_price",
            created_by: null,
            created_at: null,
            updated_at: null,
            active: true,
            phase_count: 2,
            resource_line_count: 3,
            cost_line_count: 0,
          },
        ],
      });
    const seed = vi
      .spyOn(apiClient, "seedDeliveryModelFromTemplate")
      .mockResolvedValue({
        gm_model: {
          id: "cccc3333-3333-3333-3333-333333333333",
          opportunity_id: OPP_ID,
          sow_version_id: null,
          engagement_type: "fixed_price",
          delivery_pattern: null,
          contingency_pct: null,
          warranty_days: null,
          revenue_us: "0",
          revenue_india: "0",
          created_by: null,
          created_at: "2026-09-17T00:00:00Z",
          phases: [
            {
              id: "p-1",
              name: "Discovery",
              order: 0,
              sow_deliverable_ref: null,
              description: null,
            },
          ],
          phase_summary: [],
          resource_lines: [],
          cost_lines: [],
          completeness_issues: [],
        },
      });
    render(<DeliveryModelBuilder opportunityId={OPP_ID} />);
    await waitFor(() =>
      expect(screen.getByTestId("load-template-btn")).toBeInTheDocument(),
    );

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(screen.getByTestId("load-template-btn"));
    await waitFor(() => expect(list).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.getByTestId("load-template-modal")).toBeInTheDocument(),
    );

    const useBtn = await screen.findByTestId(
      `template-pick-bbbb2222-2222-2222-2222-222222222222`,
    );
    await user.click(useBtn);
    await waitFor(() => expect(seed).toHaveBeenCalled());
    // Phase from the seed response landed in the Builder.
    await waitFor(() =>
      expect(screen.getByTestId("phase-name-0")).toHaveValue("Discovery"),
    );
  });

  it("export button downloads the xlsx blob after a save", async () => {
    vi.spyOn(apiClient, "previewDeliveryModel").mockResolvedValue(samplePreviewResponse());
    vi.spyOn(apiClient, "saveDeliveryModelVersion").mockResolvedValue(
      sampleSaveResponse(),
    );
    const blob = new Blob(["xlsx-bytes"], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const exportSpy = vi
      .spyOn(apiClient, "exportDeliveryModelXlsx")
      .mockResolvedValue(blob);

    // jsdom lacks these — install so the download path completes.
    const createObjectURL = vi.fn().mockReturnValue("blob:mock");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: createObjectURL,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: revokeObjectURL,
    });
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});

    render(<DeliveryModelBuilder opportunityId={OPP_ID} />);
    await waitFor(() =>
      expect(screen.getByLabelText("Engagement type")).toBeInTheDocument(),
    );
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(screen.getByTestId("add-us-btn"));
    await act(async () => {
      vi.advanceTimersByTime(400);
    });
    await user.click(screen.getByTestId("save-btn"));
    await waitFor(() =>
      expect(screen.getByTestId("save-toast")).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId("export-btn"));
    await waitFor(() => expect(exportSpy).toHaveBeenCalledWith(NEW_MODEL_ID));
    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(clickSpy).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalled();
  });
});
