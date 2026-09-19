/**
 * S10-01 — SowStudio upload path acceptance tests.
 *
 * Anchors:
 *
 * - The `Upload & derive` button enables the moment a file is attached
 *   (no client selection is required — that is the point).
 * - A non-SOW response (HTTP 422 with ``detected_type``) renders a red
 *   banner + a "Upload a different file" button. No navigation.
 * - The picker modal renders the top-3 candidates + "Create new" and
 *   picking one navigates to the confirmation URL.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../../api/client";
import { ApiError } from "../../api/client";
import { SowStudioPage } from "../../pages/v2/SowStudio";

const OPP = "00000000-0000-0000-0000-0000000000aa";
const JOB = "00000000-0000-0000-0000-0000000000j1";
const CLIENT_A = "00000000-0000-0000-0000-000000000c01";
const CLIENT_B = "00000000-0000-0000-0000-000000000c02";

function makeFile(name = "sow.pdf"): File {
  return new File([new Uint8Array([1, 2, 3])], name, {
    type: "application/pdf",
  });
}

function renderStudio(initial = "/sows/new") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/sows/new" element={<SowStudioPage />} />
        <Route
          path="/sows/:id/approvals"
          element={<div data-testid="approvals-landing">Approvals</div>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SowStudio — upload path", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("enables the submit button the moment the file is attached", async () => {
    renderStudio();
    const submit = screen.getByTestId("upload-submit") as HTMLButtonElement;
    expect(submit).toBeDisabled();

    const fileInput = screen.getByTestId("upload-file-input") as HTMLInputElement;
    await userEvent.upload(fileInput, makeFile());

    expect(screen.getByTestId("upload-file-staged")).toBeInTheDocument();
    expect(submit).not.toBeDisabled();
    // The compact note is present — no client input on the page.
    expect(screen.getByTestId("upload-client-note")).toHaveTextContent(
      /Client is read from the SOW/i,
    );
    expect(screen.queryByLabelText(/^Client$/i)).toBeNull();
  });

  it("renders the non-SOW banner on 422 and does not navigate", async () => {
    vi.spyOn(apiClient, "uploadSow").mockRejectedValue(
      new ApiError(
        422,
        {
          detail: {
            detected_type: "resume",
            message: "This file does not look like a SOW. Detected: resume.",
          },
        },
        "This file does not look like a SOW. Detected: resume.",
      ),
    );

    renderStudio();
    const fileInput = screen.getByTestId("upload-file-input") as HTMLInputElement;
    await userEvent.upload(fileInput, makeFile("resume.pdf"));
    await userEvent.click(screen.getByTestId("upload-submit"));

    await waitFor(() => {
      expect(screen.getByTestId("upload-rejected-banner")).toBeInTheDocument();
    });
    expect(
      screen.getByTestId("upload-rejected-banner").textContent,
    ).toMatch(/does not look like a SOW/i);
    expect(screen.getByTestId("upload-rejected-retry")).toBeInTheDocument();
    // No navigation — approvals landing route did not activate.
    expect(screen.queryByTestId("approvals-landing")).toBeNull();
  });

  it("renders the picker with 3 candidates + create-new and picking one navigates", async () => {
    // Kick off with a job already in `needs_pick` so the URL puts us on
    // the pipeline branch. The poll returns the needs_pick payload;
    // pickSowJobClient returns a `done` job so the flow navigates.
    vi.spyOn(apiClient, "getSowJob").mockResolvedValue({
      id: JOB,
      status: "needs_pick",
      resolution: "needs_pick",
      error: null,
      opportunity_id: null,
      sow_version_id: null,
      file_hash: "hash",
      s3_key: "sow/x.pdf",
      needs_pick: {
        signals: { legal_name: "Northstar Analytics" },
        candidates: [
          { client_id: CLIENT_A, name: "Northstar Analytics Inc", score: 0.9 },
          { client_id: CLIENT_B, name: "Northstar Corp", score: 0.87 },
          {
            client_id: "00000000-0000-0000-0000-000000000c03",
            name: "Northstar LLC",
            score: 0.85,
          },
        ],
        create_new: {
          legal_name: "Northstar Analytics",
          domain: "northstar.example",
          address_lines: [],
        },
      },
    });

    const pickSpy = vi
      .spyOn(apiClient, "pickSowJobClient")
      .mockResolvedValue({
        id: JOB,
        status: "done",
        resolution: "matched",
        error: null,
        opportunity_id: OPP,
        sow_version_id: "00000000-0000-0000-0000-000000000ff1",
        file_hash: "hash",
        s3_key: "sow/x.pdf",
        needs_pick: null,
      });

    // The confirmation load fires once we navigate to opportunityId; mock
    // it minimally so ConfirmationFlow doesn't 500 in the test.
    vi.spyOn(apiClient, "getSowConfirmation").mockResolvedValue({
      sow_version: {
        id: "00000000-0000-0000-0000-000000000ff1",
        extract_status: "complete",
        engagement_type_suggested: "staff_aug",
        extracted_fields: null,
      },
      engagement: {
        primary: { type: "staff_aug", confidence: 1 },
        secondary: null,
        rule_matched: "manual_pick",
        auto_confirm: true,
      },
      staffing: { lines: [], notes: [], warnings: [], sources: [] },
      gm_model: null,
      floors: { us_pass: true, india_pass: true, requires_ceo: false, failing: [] },
      approvers: {
        delivery: { user_id: null, source: "unset", business_unit: null },
        hr: { user_id: null, source: "unset", business_unit: null },
        finance: { user_id: null, source: "unset", business_unit: null },
        legal: { user_id: null, source: "unset", business_unit: null },
      },
      projected_tasks: [],
      needs_you: [],
      ceo_gate: { will_trigger: false },
    });

    renderStudio(`/sows/new?jobId=${JOB}`);

    // Modal renders + 3 candidates + create-new option.
    await waitFor(() => {
      expect(screen.getByTestId("client-picker-modal")).toBeInTheDocument();
    });
    expect(screen.getByTestId(`picker-candidate-${CLIENT_A}`)).toBeInTheDocument();
    expect(screen.getByTestId(`picker-candidate-${CLIENT_B}`)).toBeInTheDocument();
    expect(screen.getByTestId("picker-create-new")).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("picker-submit"));

    await waitFor(() => {
      expect(pickSpy).toHaveBeenCalledWith(JOB, { client_id: CLIENT_A });
    });
  });
});
