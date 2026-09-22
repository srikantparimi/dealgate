/**
 * Staffing gate (S10-05).
 *
 * The behaviour under test is a governance rule, not a nicety: a gross margin
 * is only as good as the staffing plan under it. `auto_staffing` used to
 * invent that plan — three default roles at a zero bill rate over an invented
 * date window — and a GM was computed from it silently. This screen is where
 * a person supplies the real plan instead.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import {
  StaffingGatePage,
  emptyRow,
  isFixedFee,
  rowIsComplete,
  toResourceLines,
  formatPct,
} from "../../pages/v2/sow-staffing/StaffingGate";
import * as api from "../../api/client";

const OPP = "11111111-1111-1111-1111-111111111111";

function renderGate() {
  return render(
    <MemoryRouter initialEntries={[`/sows/${OPP}/staffing`]}>
      <Routes>
        <Route path="/sows/:id/staffing" element={<StaffingGatePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "getDirectCostCategories").mockResolvedValue({ categories: ["Travel", "Software/licenses"] });
  vi.spyOn(api, "getSowStaffing").mockResolvedValue({ resources: [], cost_lines: [], margin: {} } as never);
  vi.spyOn(api, "getSowConfirmation").mockResolvedValue({
    engagement: { primary: { type: "fixed_price", confidence: 0.9 } },
    sow_version: { extracted_fields: { price: { value: "$50,000.00" } } },
  } as never);
});

describe("rowIsComplete — what a row needs depends on the engagement", () => {
  it("omits protected costs and keeps row identity for restricted staffing writes", () => {
    const row = { ...emptyRow(), id: "resource-1", role: "Engineer", seniority: "Senior", hourly_bill_rate: "250", hourly_cost: "120", hours_billable: "80", start_date: "2026-09-01", end_date: "2026-09-30" };
    const [line] = toResourceLines([row], "tm", false);
    expect(line.id).toBe("resource-1");
    expect(line).not.toHaveProperty("hourly_cost");
    expect(line).not.toHaveProperty("validated_by");
  });

  it("wants COST on a fixed fee, not a bill rate", () => {
    // A fixed fee earns the agreed price whatever the hours are, so the bill
    // rate never enters the margin. Requiring it would ask for a number
    // nobody has on a contract where nobody bills by the hour — which is
    // what made the reported "GM not calculating" bug possible.
    const base = {
      ...emptyRow(),
      role: "Consultant",
      seniority: "Senior",
      hours_billable: "160",
      start_date: "2026-08-25",
      end_date: "2026-09-30",
    };
    expect(isFixedFee("fixed_price")).toBe(true);
    expect(isFixedFee("assessment")).toBe(true);
    expect(isFixedFee("tm")).toBe(false);

    // Bill rate alone is not enough on a fixed fee.
    expect(
      rowIsComplete({ ...base, hourly_bill_rate: "225" }, "fixed_price"),
    ).toBe(false);
    // Cost alone is.
    expect(rowIsComplete({ ...base, hourly_cost: "95" }, "fixed_price")).toBe(
      true,
    );

    // T&M is the other way round: revenue IS bill rate x hours.
    expect(rowIsComplete({ ...base, hourly_cost: "95" }, "tm")).toBe(false);
    expect(rowIsComplete({ ...base, hourly_bill_rate: "225" }, "tm")).toBe(true);
  });

  it("sends the cost rate when one was entered", () => {
    const r = {
      ...emptyRow(),
      role: "Consultant",
      seniority: "Senior",
      hours_billable: "160",
      hourly_cost: "95",
      start_date: "2026-08-25",
      end_date: "2026-09-30",
    };
    const [line] = toResourceLines([r], "fixed_price");
    expect(line.hourly_cost).toBe("95");
  });

  it("rejects a row with no hours, no rate or no dates", () => {
    expect(rowIsComplete(emptyRow())).toBe(false);
    const partial = {
      ...emptyRow(),
      role: "Consultant",
      seniority: "Senior",
      hours_billable: "160",
    };
    // No rate and no dates — cannot be costed or capacity-checked.
    expect(rowIsComplete(partial)).toBe(false);
    expect(rowIsComplete({ ...partial, hourly_bill_rate: "225" })).toBe(false);
    expect(
      rowIsComplete({
        ...partial,
        hourly_bill_rate: "225",
        start_date: "2026-08-25",
        end_date: "2026-09-30",
      }),
    ).toBe(true);
  });

  it("excludes incomplete rows from the payload entirely", () => {
    const rows = [
      emptyRow(),
      {
        ...emptyRow(),
        role: "Architect",
        seniority: "Principal",
        hours_billable: "120",
        hourly_bill_rate: "260",
        start_date: "2026-08-25",
        end_date: "2026-09-30",
      },
    ];
    const lines = toResourceLines(rows);
    expect(lines).toHaveLength(1);
    expect(lines[0].role).toBe("Architect");
    // Loaded cost is never set from this screen — it comes from HR cost
    // bands server-side. Bill rates and cost rates are different tables.
    expect(lines[0].hourly_cost).toBeNull();
  });
});

describe("StaffingGatePage", () => {
  it("uses canonical staffing for cost-only previews and leaves saved resources intact", async () => {
    const original: api.DeliveryResourceLineInput[] = [{ role: "Engineer", seniority: "Senior", location: "US", person_name: "Assigned engineer", allocation_pct: "1", hours_billable: "80", hourly_bill_rate: "0", hourly_cost: "120", validated_by: "hr-1", start_date: "2026-09-01", end_date: "2026-09-30" }, { role: "Pending", seniority: "Senior", location: "US", person_name: null, allocation_pct: "1", hours_billable: "80", hourly_bill_rate: "0", hourly_cost: null, validated_by: null, start_date: "2026-09-01", end_date: "2026-09-30" }];
    vi.mocked(api.getSowStaffing).mockResolvedValue({ gm_model_id: "existing-gm", engagement_type: "fixed_price", resources: original.map((line) => ({ ...line, utilization_pct: "100" })), resource_lines: original, cost_lines: [], margin: {}, total_price: "50000" } as never);
    const preview = vi.spyOn(api, "previewDeliveryModel").mockResolvedValue({ computed: { complete: false }, warnings: {} } as never);
    const save = vi.spyOn(api, "putSowStaffing").mockResolvedValue({ gm_model_id: "next-gm" } as never);
    renderGate();
    fireEvent.click(await screen.findByRole("button", { name: "Add cost" }));
    fireEvent.change(screen.getByLabelText("Cost value 1"), { target: { value: "1000" } });
    await waitFor(() => expect(preview).toHaveBeenCalled());
    expect(preview.mock.calls.at(-1)?.[0].inputs.resource_lines).toEqual(original);
    fireEvent.click(screen.getByTestId("save-staffing"));
    await waitFor(() => expect(save).toHaveBeenCalled());
    expect(save.mock.calls[0][1]).not.toHaveProperty("resource_lines");
    expect(save.mock.calls[0][1].cost_lines?.[0].amount).toBe("1000");
  });

  it("preserves precise staffing inputs through hydration and saving", async () => {
    vi.mocked(api.getSowStaffing).mockResolvedValue({ gm_model_id: "existing-gm", resources: [{ id: "resource-1", role: "Engineer", seniority: "Senior", location: "US", person_name: null, utilization_pct: "100.0000", hours_billable: "80.1250", hourly_bill_rate: "0.0000", hourly_cost: "120.1234", start_date: "2026-09-01", end_date: "2026-09-30" }], cost_lines: [], margin: {}, total_price: "50000" } as never);
    const save = vi.spyOn(api, "putSowStaffing").mockResolvedValue({ gm_model_id: "new-gm" } as never);
    renderGate();
    expect(await screen.findByDisplayValue("120.1234")).toBeInTheDocument();
    expect(screen.getByLabelText("hours-0")).toHaveValue("80.125");
    fireEvent.change(screen.getByLabelText("role-0"), { target: { value: "Engineer II" } });
    fireEvent.click(screen.getByTestId("save-staffing"));
    await waitFor(() => expect(save).toHaveBeenCalled());
    expect(save.mock.calls[0][1].resource_lines?.[0]).toMatchObject({ id: "resource-1", hourly_cost: "120.1234", hours_billable: "80.125" });
  });

  it("says why nothing was proposed, and what a fixed fee actually needs", async () => {
    renderGate();
    // The mocked SOW is a fixed fee, so the guidance has to say that the
    // margin turns on cost — telling someone to enter a bill rate on a fixed
    // fee is what made the reported "GM not calculating" bug possible.
    expect(
      await screen.findByText(/the margin turns on cost/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/no complete rows yet/i)).toBeInTheDocument();
    expect(screen.getByText(/does not affect the margin/i)).toBeInTheDocument();
  });

  it("will not let you continue without a costed row", async () => {
    renderGate();
    const save = await screen.findByTestId("save-staffing");
    expect(save).toBeDisabled();
  });

  it("enables save and previews the margin once a row is costed", async () => {
    const preview = vi
      .spyOn(api, "previewDeliveryModel")
      .mockResolvedValue({
        engagement_type: "fixed_price",
        computed: { gm_blended: "0.42", gm_us: "0.47", gm_india: null },
        warnings: { capacity: [], hr: [] },
      } as never);

    const user = userEvent.setup();
    renderGate();

    await user.type(await screen.findByLabelText("role-0"), "Consultant");
    await user.type(screen.getByLabelText("seniority-0"), "Senior");
    await user.type(screen.getByLabelText("hours-0"), "160");
    // Fixed fee → cost is what completes the row.
    await user.type(screen.getByLabelText("cost-0"), "95");
    await user.type(screen.getByLabelText("start-0"), "2026-08-25");
    await user.type(screen.getByLabelText("end-0"), "2026-09-30");

    await waitFor(() => expect(screen.getByTestId("save-staffing")).toBeEnabled());
    await waitFor(() => expect(preview).toHaveBeenCalled());

    // The fee travels with the preview — a fixed-fee margin is meaningless
    // without it.
    const sent = preview.mock.calls.at(-1)?.[0] as never as {
      inputs: { total_price?: string; resource_lines: unknown[] };
    };
    expect(sent.inputs.total_price).toBe("50000.00");
    expect(sent.inputs.resource_lines).toHaveLength(1);

    expect(await screen.findByText("42.0%")).toBeInTheDocument();
    expect(screen.getByText("47.0%")).toBeInTheDocument();
    // India has no lines, so its margin is absent — not zero.
    expect(screen.getByText("Not applicable — no India resources")).toBeInTheDocument();
  });

  it("loads rows from an uploaded sheet without saving them", async () => {
    const importSpy = vi
      .spyOn(api, "importStaffingSheet")
      .mockResolvedValue({
        row_count: 2,
        source: "sheet_upload",
        resource_lines: [
          {
            role: "Architect",
            seniority: "Principal",
            location: "US",
            allocation_pct: "1",
            hours_billable: "120",
            hourly_bill_rate: "260",
            start_date: "2026-08-25",
            end_date: "2026-09-30",
          },
          {
            role: "Engineer",
            seniority: "Senior",
            location: "India",
            allocation_pct: "1",
            hours_billable: "300",
            hourly_bill_rate: "85",
            start_date: "2026-08-25",
            end_date: "2026-09-30",
          },
        ],
      });
    const saveSpy = vi.spyOn(api, "saveDeliveryModelVersion");
    vi.spyOn(api, "previewDeliveryModel").mockResolvedValue({
      computed: { gm_blended: "0.5" },
      warnings: { capacity: [], hr: [] },
    } as never);

    const user = userEvent.setup();
    renderGate();

    const input = await screen.findByTestId("sheet-input");
    await user.upload(
      input,
      new File(["x"], "staffing.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }),
    );

    await waitFor(() => expect(importSpy).toHaveBeenCalled());
    expect(await screen.findByDisplayValue("Architect")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Engineer")).toBeInTheDocument();
    // Uploading must not commit a cost basis on its own.
    expect(saveSpy).not.toHaveBeenCalled();
  });

  it("lists every bad row from a rejected sheet at once", async () => {
    vi.spyOn(api, "importStaffingSheet").mockRejectedValue(
      new api.ApiError(
        422,
        {
          detail: {
            message: "2 row(s) could not be read",
            errors: [
              { row: 2, field: "location", message: "must be one of US, India" },
              { row: 3, field: "hours_billable", message: "must be greater than 0" },
            ],
          },
        },
        "2 row(s) could not be read",
      ),
    );

    const user = userEvent.setup();
    renderGate();
    await user.upload(
      await screen.findByTestId("sheet-input"),
      new File(["x"], "bad.xlsx", { type: "application/vnd.ms-excel" }),
    );

    const list = await screen.findByTestId("sheet-errors");
    expect(list).toHaveTextContent("Row 2");
    expect(list).toHaveTextContent("Row 3");
  });
});

describe("formatPct", () => {
  it("renders a ratio as a percentage and copes with nulls", () => {
    expect(formatPct("0.425")).toBe("42.5%");
    expect(formatPct(null)).toBe("—");
    expect(formatPct("nonsense")).toBe("—");
  });
});
