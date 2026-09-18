/**
 * GM sandbox — schema-driven form, live compute, xlsx download.
 *
 * The page must round-trip everything through the API; no math in the
 * browser (CLAUDE.md rule 2). These tests mock the API client and assert
 * the page (a) renders fields the API's schema advertises, (b) hits
 * computeGm when inputs change, and (c) triggers a download on export.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import type {
  SandboxResponse,
  SandboxSchema,
} from "../api/client";
import { GMSandboxPage } from "../pages/GMSandbox";

const fixedPriceSchema: SandboxSchema = {
  engagement_type: "fixed_price",
  fields: [
    { name: "total_price", label: "Total price", kind: "money", required: true, help: "" },
    { name: "revenue_us", label: "US revenue allocation", kind: "money", required: true, help: "" },
    {
      name: "revenue_india",
      label: "India revenue allocation",
      kind: "money",
      required: true,
      help: "",
    },
    { name: "resources", label: "Delivery plan — resources", kind: "resources", required: false, help: "" },
  ],
};

const staffAugSchema: SandboxSchema = {
  engagement_type: "staff_aug",
  fields: [
    { name: "resources", label: "Resources", kind: "resources", required: true, help: "" },
    {
      name: "replacement_obligation",
      label: "Replacement obligation",
      kind: "bool",
      required: false,
      help: "",
    },
  ],
};

const sampleResponse: SandboxResponse = {
  engagement_type: "fixed_price",
  revenue_us: "90000",
  cost_us: "65000",
  gm_us: "0.277777777777777777777777778",
  revenue_india: "55000",
  cost_india: "30000",
  gm_india: "0.4545454545454545454545454545",
  gm_blended: "0.3448275862068965517241379310",
  geography: "Mixed",
  complete: true,
  missing: [],
  policy: {
    us_floor: "0.35",
    india_floor: "0.50",
    us_pass: false,
    india_pass: false,
    requires_ceo: true,
    failing: ["US", "India"],
    source: "defaults",
  },
  min_price_us: "100000",
  min_price_india: "60000",
  policy_version_id: null,
  rate_card_version_id: null,
  computed_at: "2026-09-17T00:00:00Z",
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/gm/sandbox"]}>
      <GMSandboxPage />
    </MemoryRouter>,
  );
}

describe("GMSandbox", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("renders schema-driven form fields for fixed_price", async () => {
    vi.spyOn(apiClient, "getGmSchema").mockResolvedValue(fixedPriceSchema);
    vi.spyOn(apiClient, "computeGm").mockResolvedValue(sampleResponse);
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText("Total price")).toBeInTheDocument();
    });
    expect(screen.getByLabelText("US revenue allocation")).toBeInTheDocument();
    expect(screen.getByLabelText("India revenue allocation")).toBeInTheDocument();
  });

  it("changes fields when engagement switches to staff_aug", async () => {
    const schemaSpy = vi.spyOn(apiClient, "getGmSchema");
    schemaSpy.mockResolvedValueOnce(fixedPriceSchema);
    schemaSpy.mockResolvedValueOnce(staffAugSchema);
    vi.spyOn(apiClient, "computeGm").mockResolvedValue(sampleResponse);
    renderPage();
    await waitFor(() =>
      expect(screen.getByLabelText("Total price")).toBeInTheDocument(),
    );

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.selectOptions(screen.getByLabelText("Engagement type"), "staff_aug");

    await waitFor(() =>
      expect(schemaSpy).toHaveBeenCalledWith("staff_aug"),
    );
    await waitFor(() =>
      expect(screen.getByLabelText("Replacement obligation")).toBeInTheDocument(),
    );
    // Fixed-price-only field is gone.
    expect(screen.queryByLabelText("Total price")).toBeNull();
  });

  it("posts to computeGm and shows the returned GM", async () => {
    vi.spyOn(apiClient, "getGmSchema").mockResolvedValue(fixedPriceSchema);
    const computeSpy = vi.spyOn(apiClient, "computeGm").mockResolvedValue(sampleResponse);
    renderPage();
    await waitFor(() =>
      expect(screen.getByLabelText("Total price")).toBeInTheDocument(),
    );

    // Advance the debounce timer so the initial compute fires.
    await act(async () => {
      vi.advanceTimersByTime(300);
    });
    await waitFor(() => expect(computeSpy).toHaveBeenCalled());

    // The response's GM values render as percentages in the panel.
    await waitFor(() => {
      const usGm = screen.getByTestId("gm-us");
      expect(usGm.textContent).toContain("27.78%");
    });
    expect(screen.getByTestId("gm-india").textContent).toContain("45.45%");
    expect(screen.getByTestId("gm-blended").textContent).toContain("34.48%");
    // Floor pass/fail chips show fail on both.
    expect(screen.getByTestId("ceo-required")).toBeInTheDocument();
  });

  it("re-computes on input change (debounced)", async () => {
    vi.spyOn(apiClient, "getGmSchema").mockResolvedValue(fixedPriceSchema);
    const computeSpy = vi.spyOn(apiClient, "computeGm").mockResolvedValue(sampleResponse);
    renderPage();
    await waitFor(() =>
      expect(screen.getByLabelText("Total price")).toBeInTheDocument(),
    );
    await act(async () => {
      vi.advanceTimersByTime(300);
    });
    await waitFor(() => expect(computeSpy).toHaveBeenCalled());
    const callsAfterInitial = computeSpy.mock.calls.length;

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.type(screen.getByTestId("input-total_price"), "1");
    await act(async () => {
      vi.advanceTimersByTime(300);
    });
    await waitFor(() => {
      expect(computeSpy.mock.calls.length).toBeGreaterThan(callsAfterInitial);
    });
    // Latest call carries the new total_price in the inputs.
    const lastCall = computeSpy.mock.calls[computeSpy.mock.calls.length - 1][0];
    expect(lastCall.engagement_type).toBe("fixed_price");
    expect((lastCall.inputs as Record<string, unknown>).total_price).toBe("1");
  });

  it("sample button fills the §7 discounted case and computes it", async () => {
    vi.spyOn(apiClient, "getGmSchema").mockResolvedValue(fixedPriceSchema);
    const computeSpy = vi.spyOn(apiClient, "computeGm").mockResolvedValue(sampleResponse);
    renderPage();
    await waitFor(() =>
      expect(screen.getByLabelText("Total price")).toBeInTheDocument(),
    );

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(screen.getByTestId("sample-btn"));
    await act(async () => {
      vi.advanceTimersByTime(300);
    });

    await waitFor(() => {
      expect(
        (screen.getByLabelText("Total price") as HTMLInputElement).value,
      ).toBe("145000");
    });
    expect(
      (screen.getByLabelText("US revenue allocation") as HTMLInputElement).value,
    ).toBe("90000");
    // The compute call fired with the §7 payload.
    await waitFor(() => {
      const lastCall = computeSpy.mock.calls[computeSpy.mock.calls.length - 1][0];
      const inputs = lastCall.inputs as Record<string, unknown>;
      expect(inputs.revenue_us).toBe("90000");
      expect(inputs.revenue_india).toBe("55000");
    });
  });

  it("export button downloads the xlsx blob", async () => {
    vi.spyOn(apiClient, "getGmSchema").mockResolvedValue(fixedPriceSchema);
    vi.spyOn(apiClient, "computeGm").mockResolvedValue(sampleResponse);
    const blob = new Blob(["xlsx-bytes"], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const exportSpy = vi.spyOn(apiClient, "exportGmXlsx").mockResolvedValue(blob);

    // jsdom lacks these — install them so the download path completes.
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
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    renderPage();
    await waitFor(() =>
      expect(screen.getByLabelText("Total price")).toBeInTheDocument(),
    );
    await act(async () => {
      vi.advanceTimersByTime(300);
    });
    await waitFor(() => expect(screen.getByTestId("result-panel")).toBeInTheDocument());

    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(screen.getByTestId("export-btn"));

    await waitFor(() => expect(exportSpy).toHaveBeenCalled());
    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(clickSpy).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalled();
  });

  it("shows the incomplete banner when API reports missing inputs", async () => {
    vi.spyOn(apiClient, "getGmSchema").mockResolvedValue(fixedPriceSchema);
    vi.spyOn(apiClient, "computeGm").mockResolvedValue({
      ...sampleResponse,
      complete: false,
      missing: ["resources[0].hourly_cost"],
      gm_us: null,
    });
    renderPage();
    await waitFor(() =>
      expect(screen.getByLabelText("Total price")).toBeInTheDocument(),
    );
    await act(async () => {
      vi.advanceTimersByTime(300);
    });
    await waitFor(() =>
      expect(screen.getByTestId("incomplete-banner")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("gm-us").textContent).toContain("—");
  });
});
