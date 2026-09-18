/**
 * SignedSOWReview — S5 E8 dropzone + diff + release panel.
 *
 * Story-critical assertions:
 *
 *   - Renders the dropzone when no upload exists yet.
 *   - Renders the diff table once an upload is present; a mismatched
 *     row carries ``data-match="no"`` so the red-highlight styling in
 *     the panel keys off a stable attribute.
 *   - The release button stays disabled until ``verify_status`` flips
 *     to ``"verified"``, and enabled once it does.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import type { SignedSowUpload } from "../api/client";
import { SignedSOWReview } from "../pages/SignedSOWReview";

const PACKAGE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";

function makeUpload(
  overrides: Partial<SignedSowUpload> = {},
): SignedSowUpload {
  return {
    id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    package_id: PACKAGE_ID,
    file_s3_key: "sow/pkg/signed.pdf",
    file_hash: "sha256:cafe",
    uploaded_by: "cccccccc-cccc-cccc-cccc-cccccccccccc",
    uploaded_at: "2026-09-18T10:00:00Z",
    verify_status: "pending",
    diff_json: null,
    verified_at: null,
    released_at: null,
    ...overrides,
  };
}

describe("SignedSOWReview", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the dropzone when no upload exists", async () => {
    vi.spyOn(apiClient, "getSignedSowUpload").mockResolvedValue(null);
    render(<SignedSOWReview packageId={PACKAGE_ID} canWrite />);
    await waitFor(() => {
      expect(
        screen.getByRole("button", {
          name: /drop the signed sow here/i,
        }),
      ).toBeInTheDocument();
    });
  });

  it("renders the diff table with mismatch flag on blocked price", async () => {
    const upload = makeUpload({
      verify_status: "blocked",
      diff_json: {
        match: false,
        fields: [
          {
            field: "price",
            approved: "250000.00",
            extracted: "999999.00",
            match: false,
          },
          {
            field: "term_start",
            approved: "2026-10-01",
            extracted: "2026-10-01",
            match: true,
          },
          {
            field: "term_end",
            approved: "2027-03-31",
            extracted: "2027-03-31",
            match: true,
          },
          {
            field: "scope_summary",
            approved: "A",
            extracted: "A",
            match: true,
            similarity: 1.0,
            threshold: 0.9,
          },
        ],
      },
    });
    vi.spyOn(apiClient, "getSignedSowUpload").mockResolvedValue(upload);
    render(<SignedSOWReview packageId={PACKAGE_ID} canWrite />);

    await waitFor(() => {
      expect(screen.getByTestId("signed-sow-diff-table")).toBeInTheDocument();
    });
    const priceRow = screen.getByTestId("diff-row-price");
    expect(priceRow.getAttribute("data-match")).toBe("no");
    const termRow = screen.getByTestId("diff-row-term_start");
    expect(termRow.getAttribute("data-match")).toBe("yes");

    // Release button disabled while status is blocked.
    const release = screen.getByTestId("signed-sow-release-btn");
    expect(release).toBeDisabled();
  });

  it("enables the release button once verify triggers a verified state", async () => {
    const pending = makeUpload({ verify_status: "pending" });
    const verified = makeUpload({
      verify_status: "verified",
      verified_at: "2026-09-18T10:05:00Z",
      diff_json: {
        match: true,
        fields: [
          {
            field: "price",
            approved: "250000.00",
            extracted: "250000.00",
            match: true,
          },
          {
            field: "term_start",
            approved: "2026-10-01",
            extracted: "2026-10-01",
            match: true,
          },
          {
            field: "term_end",
            approved: "2027-03-31",
            extracted: "2027-03-31",
            match: true,
          },
          {
            field: "scope_summary",
            approved: "A",
            extracted: "A",
            match: true,
            similarity: 1,
            threshold: 0.9,
          },
        ],
      },
    });
    vi.spyOn(apiClient, "getSignedSowUpload").mockResolvedValue(pending);
    const verifySpy = vi
      .spyOn(apiClient, "verifySignedSow")
      .mockResolvedValue(verified);

    render(<SignedSOWReview packageId={PACKAGE_ID} canWrite />);
    await waitFor(() => {
      expect(screen.getByTestId("signed-sow-verify-btn")).toBeInTheDocument();
    });
    expect(screen.getByTestId("signed-sow-release-btn")).toBeDisabled();

    const user = userEvent.setup();
    await user.click(screen.getByTestId("signed-sow-verify-btn"));
    await waitFor(() => {
      expect(verifySpy).toHaveBeenCalledWith(PACKAGE_ID);
    });
    await waitFor(() => {
      expect(screen.getByTestId("signed-sow-release-btn")).not.toBeDisabled();
    });
  });
});
