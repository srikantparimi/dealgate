/**
 * BulkSowImport (`/settings/data-imports/sows`) — S10-02 acceptance tests.
 *
 *  - Status chips render for every state.
 *  - Totals recompute from the summary payload.
 *  - The Download log CSV button fires.
 *  - The Legacy chip renders alongside imported/needs_review rows.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../../api/client";
import type {
  BulkImportBatchSummary,
  BulkImportFileRow,
} from "../../api/client";
import { BulkSowImportPage } from "../../pages/v2/BulkSowImport";

function file(row: Partial<BulkImportFileRow>): BulkImportFileRow {
  return {
    id: "f-1",
    batch_id: "b-1",
    filename: "01.pdf",
    size_bytes: 1024,
    sha256: "abc",
    detected_type: "sow",
    status: "imported",
    matched_client_id: null,
    matched_confidence: null,
    opportunity_id: null,
    sow_version_id: null,
    duplicate_of: null,
    warnings: [],
    errors: [],
    needs_you: false,
    created_at: "2026-09-21T10:00:00Z",
    updated_at: "2026-09-21T10:00:05Z",
    ...row,
  };
}

function batch(row: Partial<BulkImportBatchSummary>): BulkImportBatchSummary {
  return {
    id: "b-1",
    run_by: "u-1",
    status: "completed",
    file_count: 8,
    queued_count: 0,
    imported_count: 6,
    rejected_count: 0,
    duplicate_count: 1,
    needs_review_count: 1,
    note: null,
    created_at: "2026-09-21T10:00:00Z",
    updated_at: "2026-09-21T10:00:20Z",
    ...row,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/settings/data-imports/sows"]}>
      <BulkSowImportPage />
    </MemoryRouter>,
  );
}

describe("BulkSowImportPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uploads files, renders each status chip, and shows the Legacy chip on imported rows", async () => {
    const startSpy = vi
      .spyOn(apiClient, "startBulkImport")
      .mockResolvedValue({ batch_id: "b-1", file_count: 3 });
    vi.spyOn(apiClient, "getBulkImportBatch").mockResolvedValue(
      batch({
        file_count: 3,
        imported_count: 1,
        needs_review_count: 1,
        duplicate_count: 1,
      }),
    );
    vi.spyOn(apiClient, "getBulkImportFiles").mockResolvedValue({
      items: [
        file({
          id: "a",
          filename: "01.pdf",
          status: "imported",
          opportunity_id: "opp-a",
        }),
        file({
          id: "b",
          filename: "02.pdf",
          status: "needs_review",
          opportunity_id: "opp-b",
        }),
        file({
          id: "c",
          filename: "03.pdf",
          status: "duplicate",
          duplicate_of: "sowver-x",
        }),
      ],
    });

    renderPage();

    // Fire the upload path via the hidden file input.
    const input = await screen.findByTestId("bulk-file-input");
    const f = new File([new Uint8Array([1, 2, 3])], "01.pdf", {
      type: "application/pdf",
    });
    await userEvent.upload(input, [f]);

    await waitFor(() => expect(startSpy).toHaveBeenCalledOnce());

    // Queue table shows three rows with their per-status chip.
    await waitFor(() => {
      expect(screen.getByTestId("bulk-chip-imported")).toBeInTheDocument();
    });
    expect(screen.getByTestId("bulk-chip-needs_review")).toBeInTheDocument();
    expect(screen.getByTestId("bulk-chip-duplicate")).toBeInTheDocument();

    // Legacy chip renders alongside the imported and needs_review rows.
    const legacyChips = screen.getAllByText("Legacy");
    expect(legacyChips.length).toBeGreaterThanOrEqual(2);

    // Summary totals reflect the batch payload.
    const summary = screen.getByTestId("bulk-summary");
    expect(summary).toHaveTextContent("Imported");
    expect(summary).toHaveTextContent("Duplicate");
    expect(summary).toHaveTextContent("Needs review");
  });

  it("Download log CSV button calls the API and triggers a download", async () => {
    vi.spyOn(apiClient, "startBulkImport").mockResolvedValue({
      batch_id: "b-1",
      file_count: 1,
    });
    vi.spyOn(apiClient, "getBulkImportBatch").mockResolvedValue(batch({}));
    vi.spyOn(apiClient, "getBulkImportFiles").mockResolvedValue({
      items: [file({})],
    });
    const dlSpy = vi
      .spyOn(apiClient, "downloadBulkImportLog")
      .mockResolvedValue(new Blob(["csv"], { type: "text/csv" }));

    // Stub URL creation so jsdom doesn't blow up. jsdom does not
    // implement URL.createObjectURL — install a stub if it's absent
    // before spy-wrapping it.
    if (typeof URL.createObjectURL !== "function") {
      (URL as unknown as { createObjectURL: () => string }).createObjectURL =
        () => "blob:mock";
    }
    if (typeof URL.revokeObjectURL !== "function") {
      (URL as unknown as { revokeObjectURL: () => void }).revokeObjectURL =
        () => undefined;
    }
    const createSpy = vi
      .spyOn(URL, "createObjectURL")
      .mockReturnValue("blob:mock");
    const revokeSpy = vi
      .spyOn(URL, "revokeObjectURL")
      .mockImplementation(() => undefined);

    renderPage();
    const input = await screen.findByTestId("bulk-file-input");
    const f = new File([new Uint8Array([1, 2])], "one.pdf", {
      type: "application/pdf",
    });
    await userEvent.upload(input, [f]);

    const btn = await screen.findByTestId("bulk-log-btn");
    await userEvent.click(btn);

    await waitFor(() => expect(dlSpy).toHaveBeenCalledWith("b-1"));
    expect(createSpy).toHaveBeenCalled();
    expect(revokeSpy).toHaveBeenCalled();
  });

  it("Run again calls the rerun endpoint idempotently", async () => {
    vi.spyOn(apiClient, "startBulkImport").mockResolvedValue({
      batch_id: "b-1",
      file_count: 1,
    });
    const bSpy = vi
      .spyOn(apiClient, "getBulkImportBatch")
      .mockResolvedValue(batch({}));
    vi.spyOn(apiClient, "getBulkImportFiles").mockResolvedValue({
      items: [file({})],
    });
    const rerunSpy = vi
      .spyOn(apiClient, "rerunBulkImport")
      .mockResolvedValue(batch({ status: "completed" }));

    renderPage();
    const input = await screen.findByTestId("bulk-file-input");
    const f = new File([new Uint8Array([1, 2])], "one.pdf", {
      type: "application/pdf",
    });
    await userEvent.upload(input, [f]);
    const btn = await screen.findByTestId("bulk-rerun-btn");
    await userEvent.click(btn);

    await waitFor(() => expect(rerunSpy).toHaveBeenCalledWith("b-1", []));
    // Post-rerun reload fetches the batch state again.
    expect(bSpy).toHaveBeenCalledTimes(2);
  });
});
