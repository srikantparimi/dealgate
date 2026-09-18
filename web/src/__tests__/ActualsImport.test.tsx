import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import * as authModule from "../auth/AuthProvider";
import { ActualsImportPage, parseCsvText } from "../pages/ActualsImport";

function stubAuth(groups: string[] = ["Finance"]) {
  vi.spyOn(authModule, "useAuth").mockReturnValue({
    user: {
      sub: "user-id",
      email: "finance@smartek21.com",
      name: "Finance",
      groups,
      role: groups[0] ?? "User",
    },
    isAuthenticated: true,
    tokenReady: true,
    login: vi.fn(),
    logout: vi.fn(),
  });
}

const SAMPLE_CSV =
  "sow_ref,resource_line_id,period_month,actual_hours,actual_cost,actual_revenue\n" +
  "SOW-A,11111111-1111-1111-1111-111111111111,2026-01,160,19200.00,32000.00\n" +
  "SOW-A,22222222-2222-2222-2222-222222222222,2026-01,160,4800.00,12800.00\n";

function makeCsvFile(content = SAMPLE_CSV, name = "actuals.csv"): File {
  return new File([content], name, { type: "text/csv" });
}

describe("parseCsvText", () => {
  it("parses required columns", () => {
    const rows = parseCsvText(SAMPLE_CSV);
    expect(rows).toHaveLength(2);
    expect(rows[0]?.sow_ref).toBe("SOW-A");
    expect(rows[0]?.actual_cost).toBe("19200.00");
    expect(rows[0]?.id).toBe(2); // data row starts at row 2 (header = 1)
    expect(rows[0]?.status).toBe("ok");
  });

  it("throws on missing required column", () => {
    const bad =
      "sow_ref,resource_line_id,period_month,actual_hours,actual_revenue\n" +
      "SOW-A,x,2026-01,10,200\n";
    expect(() => parseCsvText(bad)).toThrowError(/actual_cost/);
  });

  it("flags rows with missing actual_cost as error", () => {
    const missingCost =
      "sow_ref,resource_line_id,period_month,actual_hours,actual_cost,actual_revenue\n" +
      "SOW-A,x,2026-01,10,,200\n";
    const rows = parseCsvText(missingCost);
    expect(rows[0]?.status).toBe("error");
    expect(rows[0]?.message).toMatch(/actual_cost/);
  });
});

describe("ActualsImportPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    stubAuth();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the dropzone and empty-state hint", () => {
    render(
      <MemoryRouter initialEntries={["/actuals/import"]}>
        <ActualsImportPage />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("button", { name: /Drop the actuals CSV here/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/No file yet/i)).toBeInTheDocument();
    expect(screen.getByText(/sow_ref, resource_line_id/i)).toBeInTheDocument();
  });

  it("previews rows after a file is dropped, then submits", async () => {
    const spy = vi.spyOn(apiClient, "importActualsCsv").mockResolvedValue({
      id: "batch-1",
      uploaded_by: "user-id",
      status: "committed",
      row_count: 2,
      errors: null,
    });

    render(
      <MemoryRouter initialEntries={["/actuals/import"]}>
        <ActualsImportPage />
      </MemoryRouter>,
    );

    const input = document.querySelector(
      'input[aria-label="Actuals CSV"]',
    ) as HTMLInputElement;
    const file = makeCsvFile();
    // jsdom doesn't wire File.text() to string-backed File data by default;
    // patch it so the client-side preview parser runs.
    Object.defineProperty(file, "text", {
      value: async () => SAMPLE_CSV,
    });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText(/actuals\.csv/)).toBeInTheDocument();
      expect(screen.getByText(/2 rows/)).toBeInTheDocument();
      // First data row's sow_ref renders in the preview grid.
      expect(screen.getAllByText("SOW-A").length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByRole("button", { name: /Import CSV/i }));

    await waitFor(() => {
      expect(spy).toHaveBeenCalledTimes(1);
      expect(screen.getByText(/Batch committed/i)).toBeInTheDocument();
      // "2 rows" now appears both in the preview count and the batch chip.
      expect(screen.getAllByText(/2 rows/i).length).toBeGreaterThan(0);
    });
  });

  it("shows server row errors on 422 rejection", async () => {
    const { ApiError } = apiClient;
    vi.spyOn(apiClient, "importActualsCsv").mockRejectedValue(
      new ApiError(422, {
        detail: {
          message: "actuals import failed validation",
          errors: [
            {
              row: 3,
              column: "resource_line_id",
              error: "unknown resource_line_id",
            },
          ],
        },
      }, "actuals import failed validation"),
    );

    render(
      <MemoryRouter initialEntries={["/actuals/import"]}>
        <ActualsImportPage />
      </MemoryRouter>,
    );

    const input = document.querySelector(
      'input[aria-label="Actuals CSV"]',
    ) as HTMLInputElement;
    const file = makeCsvFile();
    Object.defineProperty(file, "text", {
      value: async () => SAMPLE_CSV,
    });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText(/2 rows/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Import CSV/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/actuals import failed validation/i),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/unknown resource_line_id/i),
      ).toBeInTheDocument();
    });
  });
});
