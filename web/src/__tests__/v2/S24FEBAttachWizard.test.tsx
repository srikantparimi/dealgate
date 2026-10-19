// S24-AG1 F4 · "Attach standard copies": the three steps backed by the server — the standard copies
// (with an upload in place), the dry run with its counts and tickable list, the typed confirm with the
// server's own count, the job with polled progress, the done state, a reopen that follows a running
// batch, one idempotency key per opening, and the 409 / 422 answers.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as agreementsApi from "../../api/agreements";
import type {
  AgreementKind,
  AgreementsWorkspace,
  Batch,
  BatchPreview,
  BatchTarget,
  StandardDocuments,
  StandardVersion,
} from "../../api/agreements";
import { ApiError } from "../../api/client";
import { AttachWizard, type AttachWizardProps } from "../../pages/v2/agreements/AttachWizard";
import { BATCH_POLL } from "../../pages/v2/agreements/UndoBatchDialog";
import { Toaster } from "../../ui-v2/primitives/toaster";
import { TooltipProvider } from "../../ui-v2/primitives/tooltip";

function Providers({ children }: { children: ReactNode }) {
  return (
    <MemoryRouter>
      <TooltipProvider>
        <Toaster>{children}</Toaster>
      </TooltipProvider>
    </MemoryRouter>
  );
}

function standardVersion(kind: AgreementKind): StandardVersion {
  return {
    kind,
    version: 1,
    file_name: `SmarTek21_Standard_${kind}.pdf`,
    file_size: 214000,
    uploaded_by: "Srikanth Parimi",
    uploaded_at: "2026-10-15T18:00:00Z",
    attached_clients: 0,
  };
}

const BOTH: StandardDocuments = { NDA: standardVersion("NDA"), MSA: standardVersion("MSA") };
const id = (n: number) => `c0000000-0000-4000-8000-${String(n).padStart(12, "0")}`;

function target(n: number, name: string, extra: Partial<BatchTarget> = {}): BatchTarget {
  return { client_id: id(n), name, relationship: "net_new", included: true, reason: "", ...extra };
}

const TARGETS: BatchTarget[] = [
  target(1, "Willow Dental"),
  target(2, "Highland Energy"),
  target(3, "Fairview Freight"),
  target(4, "E2E Verify Client 0412", { relationship: "existing", included: false, reason: "test_data" }),
  target(5, "Dune Farms", { relationship: "existing", included: false, reason: "stage_1_only" }),
  target(6, "Orchard Health", { relationship: "existing", included: false, reason: "stage_1_only" }),
];

function preview(overrides: Partial<BatchPreview> = {}): BatchPreview {
  return {
    kinds: ["NDA", "MSA"],
    will_receive: 3,
    net_new_included: 3,
    already_hold: 85,
    net_new_untouched: 135,
    targets: TARGETS,
    ...overrides,
  };
}

function batch(overrides: Partial<Batch> & { attached_clients?: number } = {}): Batch {
  return {
    id: "AG-0001",
    status: "running",
    kinds: ["NDA", "MSA"],
    created_by: "Srikanth Parimi",
    created_at: "2026-10-15T19:00:00Z",
    target_count: 3,
    done_count: 0,
    attached_count: 0,
    skipped_count: 0,
    ...overrides,
  } as Batch;
}

function renderWizard(overrides: Partial<AttachWizardProps> = {}) {
  const props: AttachWizardProps = { open: true, onOpenChange: vi.fn(), onChanged: vi.fn(), ...overrides };
  render(
    <Providers>
      <AttachWizard {...props} />
    </Providers>,
  );
  return props;
}

const dialog = () => within(screen.getByRole("dialog"));

beforeEach(() => {
  vi.restoreAllMocks();
  BATCH_POLL.ms = 5;
  vi.spyOn(agreementsApi, "listBatches").mockResolvedValue({ items: [] });
  vi.spyOn(agreementsApi, "getStandardDocuments").mockResolvedValue(BOTH);
  vi.spyOn(agreementsApi, "getAgreementsWorkspace").mockResolvedValue({
    cutover: { set: true, date: "2026-10-15" },
  } as AgreementsWorkspace);
});
afterEach(() => {
  vi.restoreAllMocks();
  BATCH_POLL.ms = 1500;
});

describe("step 1 · standard copies", () => {
  it("tonight: both Not uploaded, nothing ticked, and a standard copy uploads in place", async () => {
    vi.mocked(agreementsApi.getStandardDocuments)
      .mockResolvedValueOnce({ NDA: null, MSA: null })
      .mockResolvedValue({ NDA: standardVersion("NDA"), MSA: null });
    const upload = vi.spyOn(agreementsApi, "uploadStandard").mockResolvedValue(standardVersion("NDA"));
    const props = renderWizard();
    expect(await dialog().findByText("Attach your standard copies to existing clients in one step. Nothing is attached until you confirm on the last step.")).toBeInTheDocument();
    expect(dialog().getByText("One-time backfill")).toBeInTheDocument();
    expect(dialog().getByRole("heading", { name: "Attach standard copies" })).toBeInTheDocument();
    expect(dialog().getByText("1 · Standard copies")).toHaveAttribute("aria-current", "step");
    expect(dialog().getAllByText("Not uploaded")).toHaveLength(2);
    expect(dialog().getByRole("checkbox", { name: "Attach the standard NDA" })).not.toBeChecked();
    expect(dialog().getByRole("button", { name: "Review who gets them" })).toBeDisabled();

    fireEvent.click(dialog().getByRole("button", { name: "Upload standard NDA" }));
    expect(dialog().getByRole("heading", { name: "Upload standard NDA" })).toBeInTheDocument();
    expect(dialog().getByText("Standard copy", { selector: "p" })).toBeInTheDocument();
    expect(dialog().getByLabelText("What is this?")).toBeDisabled();
    fireEvent.click(dialog().getByRole("button", { name: "Back to attach" }));
    expect(dialog().getByRole("heading", { name: "Attach standard copies" })).toBeInTheDocument();

    fireEvent.click(dialog().getByRole("button", { name: "Upload standard NDA" }));
    fireEvent.change(dialog().getByLabelText("Choose a file"), {
      target: { files: [new File(["%PDF-1.7"], "SmarTek21_Standard_NDA.pdf")] },
    });
    await dialog().findByText("Will be stored as");
    fireEvent.click(dialog().getByRole("button", { name: "Upload" }));
    await waitFor(() => expect(upload).toHaveBeenCalledWith("NDA", expect.any(File), expect.any(Function)));
    expect(await dialog().findByText("v1")).toBeInTheDocument();
    expect(dialog().getByText("SmarTek21_Standard_NDA.pdf · uploaded Oct 15, 2026 by Srikanth Parimi")).toBeInTheDocument();
    expect(dialog().getByRole("checkbox", { name: "Attach the standard NDA" })).toBeChecked();
    expect(dialog().getByRole("button", { name: "Review who gets them" })).toBeEnabled();
    expect(props.onChanged).toHaveBeenCalledTimes(1);
  });
});

describe("steps 2 and 3 · dry run, confirm and run", () => {
  it("lists the targets with their reasons, counts live, confirms with the server's number and runs the job", async () => {
    const dry = vi
      .spyOn(agreementsApi, "previewBatch")
      .mockResolvedValueOnce(preview())
      .mockResolvedValueOnce(preview({ will_receive: 3, net_new_included: 2, net_new_untouched: 136 }));
    const start = vi.spyOn(agreementsApi, "startBatch").mockResolvedValue(batch());
    vi.spyOn(agreementsApi, "getBatch")
      .mockResolvedValueOnce(batch({ done_count: 2 }))
      .mockResolvedValue(batch({ status: "done", done_count: 3, attached_count: 6, attached_clients: 3 }));
    const props = renderWizard();

    fireEvent.click(await dialog().findByRole("button", { name: "Review who gets them" }));
    expect(dialog().getByText("2 · Review")).toHaveAttribute("aria-current", "step");
    expect(await dialog().findByText("This is a dry run. No client changes yet.")).toBeInTheDocument();
    await dialog().findByText("Willow Dental");
    expect(dry).toHaveBeenCalledWith({ kinds: ["NDA", "MSA"], include_net_new_past_stage_1: true });
    const count = (label: string) => dialog().getByText(label).nextElementSibling?.textContent;
    expect(count("Clients that will receive copies")).toBe("3");
    expect(count("of which net-new clients in the pipeline past stage 1")).toBe("3");
    expect(count("Clients already holding the chosen documents")).toBe("85");
    expect(count("Net-new clients not included (stage 1 or no active deal)")).toBe("135");
    expect(dialog().getAllByText("Net new · in pipeline")).toHaveLength(3);
    expect(dialog().getByText("Test data")).toBeInTheDocument();
    expect(dialog().getAllByText("Deals only in stage 1")).toHaveLength(2);
    expect(dialog().getByRole("checkbox", { name: "Willow Dental" })).toBeChecked();
    expect(dialog().getByRole("checkbox", { name: "Dune Farms" })).not.toBeChecked();

    fireEvent.click(dialog().getByRole("checkbox", { name: "Willow Dental" }));
    fireEvent.click(dialog().getByRole("checkbox", { name: "Dune Farms" }));
    expect(count("Clients that will receive copies")).toBe("3");
    expect(count("of which net-new clients in the pipeline past stage 1")).toBe("2");
    expect(count("Net-new clients not included (stage 1 or no active deal)")).toBe("136");

    fireEvent.click(dialog().getByRole("button", { name: "Continue" }));
    expect(await dialog().findByText("3 · Confirm and run")).toHaveAttribute("aria-current", "step");
    expect(dry).toHaveBeenLastCalledWith({
      kinds: ["NDA", "MSA"],
      include_net_new_past_stage_1: true,
      include_client_ids: [id(5)],
      exclude_client_ids: [id(1)],
    });
    const sentence = dialog().getByText(/You are about to attach/);
    expect(sentence.textContent).toBe(
      "You are about to attach NDA and MSA to 3 clients (1 existing, 2 net new in the pipeline). A client that already has one keeps it. Net-new clients that receive a copy stay net new and show “Standard copy”; replace it from the client panel when they need their own version.",
    );
    const typed = dialog().getByLabelText("Type ATTACH 3 to confirm");
    const run = dialog().getByRole("button", { name: "Attach now" });
    expect(run).toBeDisabled();
    fireEvent.change(typed, { target: { value: "ATTACH 2" } });
    expect(run).toBeDisabled();
    fireEvent.change(typed, { target: { value: "ATTACH 3" } });
    expect(run).toBeEnabled();
    fireEvent.click(run);
    fireEvent.click(run);

    expect(await dialog().findByText("Attaching in groups of 25. You can leave this open; it keeps running.")).toBeInTheDocument();
    expect(start).toHaveBeenCalledTimes(1);
    const sent = start.mock.calls[0]![0];
    expect(sent).toMatchObject({
      kinds: ["NDA", "MSA"],
      include_net_new_past_stage_1: true,
      include_client_ids: [id(5)],
      exclude_client_ids: [id(1)],
      confirm: "ATTACH 3",
    });
    expect(sent.idempotency_key).toMatch(/^[0-9a-f-]{36}$/);

    expect(
      await dialog().findByText(
        "Batch AG-0001 attached NDA and MSA to 3 clients. Every attachment is credited to Srikanth Parimi and recorded in the audit log.",
        { exact: false },
      ),
    ).toBeInTheDocument();
    expect(
      await dialog().findByText(
        "Existing and net new are now fixed as of Oct 15, 2026. You can undo this batch from the page header. Undo removes only what this batch attached.",
      ),
    ).toBeInTheDocument();
    expect(props.onChanged).toHaveBeenCalledTimes(1);
    // The kit's × is also named Close; this is the prototype's text button.
    const close = dialog()
      .getAllByRole("button", { name: "Close" })
      .find((button) => button.textContent === "Close")!;
    fireEvent.click(close);
    expect(props.onOpenChange).toHaveBeenCalledWith(false);
  });

  it("a 422 shows the server's reason and refreshes the count to confirm; a retry reuses the same key", async () => {
    vi.spyOn(agreementsApi, "previewBatch")
      .mockResolvedValueOnce(preview())
      .mockResolvedValueOnce(preview())
      .mockResolvedValueOnce(preview({ will_receive: 4, net_new_included: 4 }));
    const start = vi
      .spyOn(agreementsApi, "startBatch")
      .mockRejectedValueOnce(new ApiError(422, { detail: "Type ATTACH 4: the count changed." }, "Type ATTACH 4: the count changed."))
      .mockResolvedValueOnce(batch({ status: "done", attached_clients: 4, target_count: 4, done_count: 4 }));
    renderWizard();
    fireEvent.click(await dialog().findByRole("button", { name: "Review who gets them" }));
    await dialog().findByText("Willow Dental");
    fireEvent.click(dialog().getByRole("button", { name: "Continue" }));
    fireEvent.change(await dialog().findByLabelText("Type ATTACH 3 to confirm"), { target: { value: "ATTACH 3" } });
    fireEvent.click(dialog().getByRole("button", { name: "Attach now" }));
    expect(await dialog().findByRole("alert")).toHaveTextContent("Type ATTACH 4: the count changed.");
    const typed = await dialog().findByLabelText("Type ATTACH 4 to confirm");
    expect(typed).toHaveValue("");
    fireEvent.change(typed, { target: { value: "ATTACH 4" } });
    fireEvent.click(dialog().getByRole("button", { name: "Attach now" }));
    expect(await dialog().findByText(/Batch AG-0001 attached NDA and MSA to 4 clients\./)).toBeInTheDocument();
    expect(start.mock.calls[1]![0].idempotency_key).toBe(start.mock.calls[0]![0].idempotency_key);
    expect(start.mock.calls[1]![0].confirm).toBe("ATTACH 4");
  });

  it("a 409 follows the batch that is already running instead of starting a second one", async () => {
    vi.spyOn(agreementsApi, "previewBatch").mockResolvedValue(preview());
    vi.spyOn(agreementsApi, "startBatch").mockRejectedValue(
      new ApiError(409, { detail: "Batch AG-0002 is running." }, "Batch AG-0002 is running."),
    );
    renderWizard();
    vi.mocked(agreementsApi.listBatches).mockResolvedValue({
      items: [batch({ id: "AG-0002", status: "running", target_count: 157, done_count: 30 })],
    });
    vi.spyOn(agreementsApi, "getBatch").mockResolvedValue(batch({ id: "AG-0002", target_count: 157, done_count: 30 }));
    fireEvent.click(await dialog().findByRole("button", { name: "Review who gets them" }));
    await dialog().findByText("Willow Dental");
    fireEvent.click(dialog().getByRole("button", { name: "Continue" }));
    fireEvent.change(await dialog().findByLabelText("Type ATTACH 3 to confirm"), { target: { value: "ATTACH 3" } });
    fireEvent.click(dialog().getByRole("button", { name: "Attach now" }));
    const bar = await dialog().findByRole("progressbar", { name: "Attach progress" });
    expect(bar).toHaveAttribute("aria-valuenow", "19");
    expect(bar).toHaveAttribute("aria-valuetext", "19% · 30 of 157 clients");
  });

  it("each step moves keyboard focus to the dialog title, never leaving it on a control that is gone", async () => {
    vi.spyOn(agreementsApi, "previewBatch").mockResolvedValue(preview());
    renderWizard();
    const review = await dialog().findByRole("button", { name: "Review who gets them" });
    review.focus();
    fireEvent.click(review);
    await waitFor(() =>
      expect(document.activeElement).toBe(dialog().getByRole("heading", { name: "Attach standard copies" })),
    );
    await dialog().findByText("Willow Dental");
    fireEvent.click(dialog().getByRole("button", { name: "Continue" }));
    await dialog().findByLabelText("Type ATTACH 3 to confirm");
    expect(document.activeElement).toBe(dialog().getByRole("heading", { name: "Attach standard copies" }));
  });

  it("the dry run works before a standard is uploaded, but the run waits for the upload", async () => {
    vi.mocked(agreementsApi.getStandardDocuments).mockResolvedValue({ NDA: null, MSA: standardVersion("MSA") });
    vi.spyOn(agreementsApi, "previewBatch").mockResolvedValue(preview({ kinds: ["NDA", "MSA"] }));
    const start = vi.spyOn(agreementsApi, "startBatch");
    renderWizard();
    fireEvent.click(await dialog().findByRole("checkbox", { name: "Attach the standard NDA" }));
    fireEvent.click(dialog().getByRole("button", { name: "Review who gets them" }));
    await dialog().findByText("Willow Dental");
    fireEvent.click(dialog().getByRole("button", { name: "Continue" }));
    expect(
      await dialog().findByText("The standard NDA is not uploaded yet. Upload it in step 1 before you attach."),
    ).toBeInTheDocument();
    expect(dialog().getByLabelText("Type ATTACH 3 to confirm")).toBeDisabled();
    expect(dialog().getByRole("button", { name: "Attach now" })).toBeDisabled();
    expect(start).not.toHaveBeenCalled();
  });
});

describe("reopening", () => {
  it("shows the running batch's progress and never starts a second one", async () => {
    vi.mocked(agreementsApi.listBatches).mockResolvedValue({
      items: [batch({ id: "AG-0002", status: "running", target_count: 157, done_count: 30 })],
    });
    const poll = vi
      .spyOn(agreementsApi, "getBatch")
      .mockResolvedValueOnce(batch({ id: "AG-0002", target_count: 157, done_count: 100 }))
      .mockResolvedValue(batch({ id: "AG-0002", status: "done", target_count: 157, done_count: 157, attached_clients: 150 }));
    const preview = vi.spyOn(agreementsApi, "previewBatch");
    const start = vi.spyOn(agreementsApi, "startBatch");
    renderWizard();
    expect(await dialog().findByText("Attaching in groups of 25. You can leave this open; it keeps running.")).toBeInTheDocument();
    expect(dialog().getByRole("progressbar", { name: "Attach progress" })).toHaveAttribute("aria-valuenow", "19");
    expect(await dialog().findByText(/Batch AG-0002 attached NDA and MSA to 150 clients\./)).toBeInTheDocument();
    expect(poll).toHaveBeenCalledWith("AG-0002", expect.anything());
    expect(preview).not.toHaveBeenCalled();
    expect(start).not.toHaveBeenCalled();
  });

  it("names a failed batch and offers to review again with a new key", async () => {
    vi.mocked(agreementsApi.listBatches).mockResolvedValue({
      items: [batch({ id: "AG-0003", status: "running", target_count: 100, done_count: 50 })],
    });
    vi.spyOn(agreementsApi, "getBatch").mockResolvedValue(
      batch({
        id: "AG-0003",
        status: "failed",
        target_count: 100,
        done_count: 50,
        error: "The batch stopped after 50 of 100 clients. Run it again to finish; clients that already hold a copy are skipped.",
      }),
    );
    vi.spyOn(agreementsApi, "previewBatch").mockResolvedValue(preview());
    renderWizard();
    // The server's sentence on its own: no wrapper, no doubled period, no exception name (review finding).
    expect(await dialog().findByRole("alert")).toHaveTextContent(
      /^The batch stopped after 50 of 100 clients\. Run it again to finish; clients that already hold a copy are skipped\.$/,
    );
    expect(dialog().getByText("The copies batch AG-0003 attached stay. Review again to finish the rest.")).toBeInTheDocument();
    fireEvent.click(dialog().getByRole("button", { name: "Review again" }));
    expect(await dialog().findByText("Willow Dental")).toBeInTheDocument();
  });
});
