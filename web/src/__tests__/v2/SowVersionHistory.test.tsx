/**
 * SOW version history (S10-06).
 *
 * The rule under test: delete and discard are different endings for
 * different situations, and the server decides which applies. A version that
 * has been through approval is part of a decision record and can only be
 * discarded (CLAUDE.md rule 4).
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  SowVersionHistory,
  versionLabel,
  versionTone,
} from "../../pages/v2/sow-workspace/SowVersionHistory";
import * as api from "../../api/client";
import type { SowVersionRow } from "../../api/client";

const OPP = "11111111-1111-1111-1111-111111111111";

function row(over: Partial<SowVersionRow> = {}): SowVersionRow {
  return {
    id: "aaaaaaaa-0000-0000-0000-000000000001",
    version_no: 1,
    uploaded_at: "2026-09-19T10:00:00Z",
    extract_status: "complete",
    execution_state: "draft",
    is_current: true,
    superseded_by: null,
    discarded_at: null,
    discard_reason: null,
    file_name: "sow.docx",
    ever_submitted: false,
    can_delete: true,
    can_discard: false,
    ...over,
  };
}

beforeEach(() => vi.restoreAllMocks());

describe("versionLabel / versionTone", () => {
  it("distinguishes current, superseded and discarded", () => {
    expect(versionLabel(row())).toBe("current");
    expect(versionLabel(row({ is_current: false }))).toBe("superseded");
    expect(versionLabel(row({ discarded_at: "2026-09-20T00:00:00Z" }))).toBe(
      "discarded",
    );
    expect(versionTone(row())).toBe("ok");
    expect(versionTone(row({ discarded_at: "x" }))).toBe("neutral");
  });
});

describe("SowVersionHistory", () => {
  it("offers Delete before submission and Discard after", async () => {
    const load = vi.fn().mockResolvedValue({
      sow_id: "s1",
      versions: [
        row({ version_no: 2, id: "v2" }),
        row({
          version_no: 1,
          id: "v1",
          is_current: false,
          ever_submitted: true,
          can_delete: false,
          can_discard: true,
        }),
      ],
    });

    render(<SowVersionHistory opportunityId={OPP} load={load as never} />);

    // v2 was never submitted → deletable.
    expect(await screen.findByTestId("delete-2")).toBeInTheDocument();
    expect(screen.queryByTestId("discard-2")).not.toBeInTheDocument();

    // v1 has been through approval → discard only. Deleting it would remove
    // the document an approver actually signed off on.
    expect(screen.getByTestId("discard-1")).toBeInTheDocument();
    expect(screen.queryByTestId("delete-1")).not.toBeInTheDocument();
  });

  it("confirms before deleting, and does nothing if cancelled", async () => {
    const load = vi
      .fn()
      .mockResolvedValue({ sow_id: "s1", versions: [row({ version_no: 2 })] });
    const del = vi.spyOn(api, "deleteSowVersion").mockResolvedValue({
      deleted: true,
    });
    vi.spyOn(window, "prompt").mockReturnValue(null); // cancelled

    const user = userEvent.setup();
    render(<SowVersionHistory opportunityId={OPP} load={load as never} />);
    await user.click(await screen.findByTestId("delete-2"));

    expect(del).not.toHaveBeenCalled();
  });

  it("deletes with the reason the user gave", async () => {
    const load = vi
      .fn()
      .mockResolvedValue({ sow_id: "s1", versions: [row({ version_no: 2 })] });
    const del = vi
      .spyOn(api, "deleteSowVersion")
      .mockResolvedValue({ deleted: true });
    vi.spyOn(window, "prompt").mockReturnValue("wrong file");

    const user = userEvent.setup();
    render(<SowVersionHistory opportunityId={OPP} load={load as never} />);
    await user.click(await screen.findByTestId("delete-2"));

    await waitFor(() =>
      expect(del).toHaveBeenCalledWith(expect.any(String), "wrong file"),
    );
  });

  it("refuses to discard without a reason", async () => {
    const load = vi.fn().mockResolvedValue({
      sow_id: "s1",
      versions: [
        row({ version_no: 1, ever_submitted: true, can_delete: false, can_discard: true }),
      ],
    });
    const discard = vi.spyOn(api, "discardSowVersion");
    vi.spyOn(window, "prompt").mockReturnValue("   "); // whitespace only

    const user = userEvent.setup();
    render(<SowVersionHistory opportunityId={OPP} load={load as never} />);
    await user.click(await screen.findByTestId("discard-1"));

    // A discarded SOW leaves every board; months later the reason is the only
    // explanation anyone has.
    expect(discard).not.toHaveBeenCalled();
  });

  it("uploads a revision and reloads the list", async () => {
    const load = vi
      .fn()
      .mockResolvedValue({ sow_id: "s1", versions: [row()] });
    const revise = vi.spyOn(api, "createSowRevision").mockResolvedValue({
      sow_version_id: "new",
      version_no: 2,
      supersedes: "old",
    } as never);

    const user = userEvent.setup();
    render(<SowVersionHistory opportunityId={OPP} load={load as never} />);

    await user.upload(
      await screen.findByTestId("version-file-input"),
      new File(["x"], "revised.docx", {
        type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      }),
    );

    await waitFor(() => expect(revise).toHaveBeenCalled());
    // Reloaded so the new version shows without a manual refresh.
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
  });

  it("surfaces a rejected revision instead of failing silently", async () => {
    const load = vi
      .fn()
      .mockResolvedValue({ sow_id: "s1", versions: [row()] });
    vi.spyOn(api, "createSowRevision").mockRejectedValue(
      new api.ApiError(409, null, "these bytes are already version 1"),
    );

    const user = userEvent.setup();
    render(<SowVersionHistory opportunityId={OPP} load={load as never} />);
    await user.upload(
      await screen.findByTestId("version-file-input"),
      new File(["x"], "same.docx", { type: "application/pdf" }),
    );

    expect(await screen.findByTestId("version-error")).toHaveTextContent(
      "already version 1",
    );
  });
});
