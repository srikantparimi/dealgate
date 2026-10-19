// S24-AG1 F4/F5 · the undo dialog (count from the server, undo as a job, never an invented number) and
// the HubSpot hints dialog (not stored yet, values with client counts, the saved mapping with the
// server's dry-run count, apply, and read-only for everyone but SystemAdmin).
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as agreementsApi from "../../api/agreements";
import type { Batch, HubspotValues } from "../../api/agreements";
import { ApiError } from "../../api/client";
import { HubspotHintsDialog, type HubspotHintsDialogProps } from "../../pages/v2/agreements/HubspotHintsDialog";
import { BATCH_POLL, UndoBatchDialog, type UndoBatchDialogProps } from "../../pages/v2/agreements/UndoBatchDialog";
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

function batch(overrides: Partial<Batch> = {}): Batch {
  return {
    id: "AG-0001",
    status: "done",
    kinds: ["NDA", "MSA"],
    created_by: "Srikanth Parimi",
    created_at: "2026-10-15T19:00:00Z",
    target_count: 85,
    done_count: 85,
    attached_count: 157,
    skipped_count: 6,
    ...overrides,
  };
}

const dialog = () => within(screen.getByRole("dialog"));

beforeEach(() => {
  vi.restoreAllMocks();
  BATCH_POLL.ms = 5;
});
afterEach(() => {
  vi.restoreAllMocks();
  BATCH_POLL.ms = 1500;
});

describe("undo a batch", () => {
  function renderUndo(overrides: Partial<UndoBatchDialogProps> = {}) {
    const props: UndoBatchDialogProps = {
      open: true,
      label: "AG-0001",
      onOpenChange: vi.fn(),
      onChanged: vi.fn(),
      ...overrides,
    };
    render(
      <Providers>
        <UndoBatchDialog {...props} />
      </Providers>,
    );
    return props;
  }

  it("states the server's count, runs the undo as a job and reports what it removed", async () => {
    vi.spyOn(agreementsApi, "getBatch")
      .mockResolvedValueOnce(batch({ undo_would_remove: 157 }))
      .mockResolvedValueOnce(batch({ status: "undoing" }))
      .mockResolvedValue(batch({ status: "undone", undone_count: 155, undone_by: "Srikanth Parimi" }));
    const undo = vi.spyOn(agreementsApi, "undoBatch").mockResolvedValue(batch({ status: "undoing" }));
    const props = renderUndo();
    expect(dialog().getByText("Undo")).toBeInTheDocument();
    expect(dialog().getByRole("heading", { name: "Undo batch AG-0001" })).toBeInTheDocument();
    const text = await dialog().findByText(/This removes the/);
    expect(text.textContent).toBe(
      "This removes the 157 standard attachments made by batch AG-0001. It does not touch client copies, marks, or anything attached another way. The standard files and the cutover date stay.",
    );
    fireEvent.click(dialog().getByRole("button", { name: "Undo batch" }));
    expect(undo).toHaveBeenCalledWith("AG-0001");
    expect(await dialog().findByText("Removing the standard attachments made by batch AG-0001…")).toBeInTheDocument();
    expect(await screen.findByText("Batch AG-0001 undone: 155 attachments removed.")).toBeInTheDocument();
    expect(props.onChanged).toHaveBeenCalledTimes(1);
    expect(props.onOpenChange).toHaveBeenCalledWith(false);
  });

  it("never invents the number when the server does not send it", async () => {
    vi.spyOn(agreementsApi, "getBatch").mockResolvedValue(batch());
    renderUndo();
    const text = await dialog().findByText(/This removes the/);
    expect(text.textContent).toContain(
      "This removes the standard attachments made by batch AG-0001 that are still in place.",
    );
    expect(text.textContent).not.toMatch(/\d+ standard attachments/);
  });

  it("an undone batch says who undid it and offers no undo", async () => {
    vi.spyOn(agreementsApi, "getBatch").mockResolvedValue(
      batch({ status: "undone", undone_by: "Srikanth Parimi", undone_at: "2026-10-15T21:00:00Z" }),
    );
    renderUndo();
    expect(await dialog().findByText("Batch AG-0001 was undone by Srikanth Parimi on Oct 15, 2026.")).toBeInTheDocument();
    expect(dialog().queryByRole("button", { name: "Undo batch" })).toBeNull();
  });

  it("a refused undo shows the server's reason, then where the batch stands", async () => {
    vi.spyOn(agreementsApi, "getBatch")
      .mockResolvedValueOnce(batch({ undo_would_remove: 3 }))
      .mockResolvedValue(batch({ status: "undone", undone_by: "Legal user" }));
    vi.spyOn(agreementsApi, "undoBatch").mockRejectedValue(
      new ApiError(409, { detail: "Batch AG-0001 is already undone." }, "Batch AG-0001 is already undone."),
    );
    renderUndo();
    fireEvent.click(await dialog().findByRole("button", { name: "Undo batch" }));
    expect(await dialog().findByText("Batch AG-0001 was undone by Legal user.")).toBeInTheDocument();
  });
});

describe("HubSpot hints", () => {
  const STORED: HubspotValues = {
    stored: true,
    items: [
      { value: "Signed MSA", clients: 28, action: "ignore" },
      { value: "None", clients: 1, action: "ignore" },
    ],
  };

  const STORED_WITH_COUNTS: HubspotValues = {
    stored: true,
    items: [
      { value: "Signed MSA", clients: 28, action: "ignore", would_mark: 24 },
      { value: "None", clients: 1, action: "ignore", would_mark: 1 },
    ],
  };

  function renderHints(overrides: Partial<HubspotHintsDialogProps> = {}) {
    const props: HubspotHintsDialogProps = {
      open: true,
      isAdmin: true,
      onOpenChange: vi.fn(),
      onChanged: vi.fn(),
      ...overrides,
    };
    render(
      <Providers>
        <HubspotHintsDialog {...props} />
      </Providers>,
    );
    return props;
  }

  it("before the sync stores msa_type: says so truthfully and offers no mapping", async () => {
    vi.spyOn(agreementsApi, "getHubspotValues").mockResolvedValue({ stored: false, items: [] });
    const apply = vi.spyOn(agreementsApi, "applyHubspotMapping");
    renderHints();
    expect(dialog().getByText("Source: HubSpot")).toBeInTheDocument();
    expect(dialog().getByRole("heading", { name: "HubSpot hints" })).toBeInTheDocument();
    const first = await dialog().findByText(/has a property called/);
    expect(first.textContent).toBe(
      "HubSpot's deal record has a property called msa_type. The nightly sync stores its raw value, and the values it finds appear here for you to map. No value has been stored yet.",
    );
    expect(
      dialog().getByText(
        "Nothing is marked automatically until you map a value to “Covered”. DealGate's own record always wins, and marks made here stay even if HubSpot is switched off one day.",
      ),
    ).toBeInTheDocument();
    expect(dialog().queryByRole("combobox")).toBeNull();
    expect(dialog().queryByText(/Prototype/)).toBeNull();
    expect(apply).not.toHaveBeenCalled();
  });

  it("SystemAdmin maps a value: nothing is saved until Apply; the count comes from the server's would_mark", async () => {
    vi.spyOn(agreementsApi, "getHubspotValues").mockResolvedValue(STORED_WITH_COUNTS);
    const save = vi.spyOn(agreementsApi, "saveHubspotMapping").mockResolvedValue({
      stored: true,
      items: [
        { value: "Signed MSA", clients: 28, action: "covered", would_mark: 24 },
        { value: "None", clients: 1, action: "ignore", would_mark: 1 },
      ],
    });
    const apply = vi
      .spyOn(agreementsApi, "applyHubspotMapping")
      .mockResolvedValueOnce({ dry_run: false, would_mark: 24, marked: 24 });
    const props = renderHints();
    expect(await dialog().findByText("0 clients would be marked.")).toBeInTheDocument();
    expect(dialog().getByText("28 clients")).toBeInTheDocument();
    expect(dialog().getByText("1 client")).toBeInTheDocument();
    const select = dialog().getByRole("combobox", { name: /“Signed MSA”/ });
    expect(Array.from((select as HTMLSelectElement).options).map((o) => o.text)).toEqual(["Ignore", "Mark MSA covered"]);
    fireEvent.change(select, { target: { value: "covered" } });
    expect(await dialog().findByText("24 clients would be marked.")).toBeInTheDocument();
    // Choosing is not a commitment: the nightly sync applies only a SAVED mapping.
    expect(save).not.toHaveBeenCalled();
    expect(apply).not.toHaveBeenCalled();
    fireEvent.click(dialog().getByRole("button", { name: "Apply mapping" }));
    await waitFor(() =>
      expect(save).toHaveBeenCalledWith([
        { value: "Signed MSA", action: "covered" },
        { value: "None", action: "ignore" },
      ]),
    );
    await waitFor(() => expect(apply).toHaveBeenCalledWith(false));
    expect(await screen.findByText("MSA marked covered for 24 clients.")).toBeInTheDocument();
    expect(props.onChanged).toHaveBeenCalledTimes(1);
    expect(props.onOpenChange).toHaveBeenCalledWith(false);
  });

  it("a refused apply says why and changes nothing on the page", async () => {
    vi.spyOn(agreementsApi, "getHubspotValues").mockResolvedValue(STORED_WITH_COUNTS);
    const apply = vi.spyOn(agreementsApi, "applyHubspotMapping");
    vi.spyOn(agreementsApi, "saveHubspotMapping").mockRejectedValue(
      new ApiError(403, { detail: "Only SystemAdmin can save the mapping." }, "Only SystemAdmin can save the mapping."),
    );
    const props = renderHints();
    const select = await dialog().findByRole("combobox", { name: /“Signed MSA”/ });
    fireEvent.change(select, { target: { value: "covered" } });
    fireEvent.click(dialog().getByRole("button", { name: "Apply mapping" }));
    expect(await dialog().findByRole("alert")).toHaveTextContent("Only SystemAdmin can save the mapping.");
    expect(apply).not.toHaveBeenCalled();
    expect(props.onChanged).not.toHaveBeenCalled();
  });

  it("without the server's per-value count the line says nothing rather than invent a number", async () => {
    vi.spyOn(agreementsApi, "getHubspotValues").mockResolvedValue(STORED);
    renderHints();
    const select = await dialog().findByRole("combobox", { name: /“Signed MSA”/ });
    fireEvent.change(select, { target: { value: "covered" } });
    expect(dialog().queryByText(/would be marked/)).toBeNull();
  });

  it("everyone else reads: the choices are disabled and Apply is locked with the reason", async () => {
    vi.spyOn(agreementsApi, "getHubspotValues").mockResolvedValue(STORED);
    const apply = vi.spyOn(agreementsApi, "applyHubspotMapping");
    renderHints({ isAdmin: false });
    const select = await dialog().findByRole("combobox", { name: /“Signed MSA”/ });
    expect(select).toBeDisabled();
    const button = dialog().getByRole("button", { name: /^Apply mapping/ });
    expect(button).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(button);
    expect(await screen.findByText("Only SystemAdmin can do this.")).toBeInTheDocument();
    expect(apply).not.toHaveBeenCalled();
  });
});
