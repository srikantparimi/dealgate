// S24-AG1 F2 · the upload dialog: the prototype's fields and copy, the browser checks with the server's
// messages, "Will be stored as", the replace / new-version / standard-version notices, real byte progress
// then an honest "Saving…", the client picker keyed by id, the wizard return, escaping, Escape and focus.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState, type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as agreementsApi from "../../api/agreements";
import type {
  AgreementKind,
  AgreementsWorkspace,
  ClientAgreements,
  ClientRow,
  DocCard,
  DocState,
  StandardVersion,
  UploadProgress,
} from "../../api/agreements";
import { ApiError } from "../../api/client";
import { MSG_EMPTY, MSG_NOT_PDF, MSG_TOO_LARGE, MSG_TYPE } from "../../pages/v2/agreements/fileRules";
import { UploadDialog, type UploadDialogProps } from "../../pages/v2/agreements/UploadDialog";
import { Toaster } from "../../ui-v2/primitives/toaster";
import { TooltipProvider } from "../../ui-v2/primitives/tooltip";

const CLIENT_ID = "c0000000-0000-4000-8000-0000000000c1";

function Providers({ children }: { children: ReactNode }) {
  return (
    <MemoryRouter>
      <TooltipProvider>
        <Toaster>{children}</Toaster>
      </TooltipProvider>
    </MemoryRouter>
  );
}

function doc(kind: AgreementKind, state: DocState, extra: Partial<DocCard> = {}): DocCard {
  return { kind, state, history: [], ...extra };
}

function holdings(overrides: Partial<ClientAgreements> = {}): ClientAgreements {
  return {
    client_id: CLIENT_ID,
    name: "Cedar Freight",
    relationship: "net_new",
    relationship_basis: "none",
    requirement: "required",
    needs_attention: false,
    possible_duplicates: [],
    deals: { open: 1, won: 0, lost: 1, furthest_open_stage: 4 },
    nda: doc("NDA", "standard", { source: "standard", standard_version: 1, batch_id: "AG-0001" }),
    msa: doc("MSA", "client", { source: "client", version_no: 1 }),
    can_write: true,
    ...overrides,
  };
}

function standardVersion(kind: AgreementKind, version: number): StandardVersion {
  return {
    kind,
    version,
    file_name: `SmarTek21_Standard_${kind}.pdf`,
    file_size: 214000,
    uploaded_by: "Srikanth Parimi",
    uploaded_at: "2026-10-15T18:00:00Z",
    attached_clients: 0,
  };
}

function pdf(name: string, body = "%PDF-1.7\n1 0 obj\n"): File {
  return new File([body], name, { type: "application/pdf" });
}

function renderDialog(overrides: Partial<UploadDialogProps> = {}) {
  const props: UploadDialogProps = {
    open: true,
    target: { mode: "client", clientId: CLIENT_ID, clientName: "Cedar Freight", kind: "NDA", lockTarget: true },
    canWrite: true,
    onOpenChange: vi.fn(),
    onUploaded: vi.fn(),
    ...overrides,
  };
  render(
    <Providers>
      <UploadDialog {...props} />
    </Providers>,
  );
  return props;
}

function chooseFile(file: File) {
  fireEvent.change(screen.getByLabelText("Choose a file"), { target: { files: [file] } });
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(agreementsApi, "getClientAgreements").mockResolvedValue(holdings());
  vi.spyOn(agreementsApi, "getStandardDocuments").mockResolvedValue({ NDA: null, MSA: null });
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("client copy", () => {
  it("over a standard copy: the replace notice, the stored name, byte progress, Saving…, then the toast", async () => {
    let progress: UploadProgress | undefined;
    let finish!: (card: DocCard) => void;
    const upload = vi.spyOn(agreementsApi, "uploadClientCopy").mockImplementation((_id, _kind, _file, _note, onProgress) => {
      progress = onProgress;
      return new Promise<DocCard>((resolve) => {
        finish = resolve;
      });
    });
    const props = renderDialog();
    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByText("Upload", { selector: "p" })).toBeInTheDocument();
    expect(dialog.getByRole("heading", { name: "Upload a document" })).toBeInTheDocument();
    expect(dialog.getByLabelText("Document type")).toHaveValue("NDA");
    expect(dialog.getByLabelText("What is this?")).toBeDisabled();
    expect(dialog.getByLabelText("Client")).toHaveValue("Cedar Freight");
    expect(dialog.getByLabelText("Client")).toHaveAttribute("readonly");
    expect(dialog.getByLabelText("Note about this version (optional)")).toHaveAttribute("maxlength", "200");
    expect(dialog.getByLabelText("Note about this version (optional)")).toHaveAttribute(
      "placeholder",
      "For example: updated payment terms",
    );
    expect(
      await dialog.findByText(
        "This client holds the standard NDA. Your upload replaces it for this client only. The standard copy stays for everyone else.",
      ),
    ).toBeInTheDocument();
    expect(dialog.getByText("PDF or Word (.docx), up to 25 MB")).toBeInTheDocument();
    expect(dialog.getByRole("button", { name: "Upload" })).toBeDisabled();

    const file = pdf("Cedar NDA.pdf.pdf");
    chooseFile(file);
    expect(await dialog.findByText("Cedar NDA.pdf")).toBeInTheDocument();
    expect(dialog.getByText("Will be stored as").textContent).toContain("Cedar NDA.pdf");
    fireEvent.change(dialog.getByLabelText("Note about this version (optional)"), {
      target: { value: "Updated payment terms" },
    });
    fireEvent.click(dialog.getByRole("button", { name: "Upload" }));

    expect(upload).toHaveBeenCalledWith(CLIENT_ID, "NDA", file, "Updated payment terms", expect.any(Function));
    act(() => progress!(5, 10));
    const bar = dialog.getByRole("progressbar", { name: "Upload progress" });
    expect(bar).toHaveAttribute("aria-valuenow", "50");
    expect(dialog.getByText("Uploading… 50%")).toBeInTheDocument();
    expect(dialog.getByRole("button", { name: "Cancel" })).toBeDisabled();
    act(() => progress!(10, 10));
    expect(dialog.getByText("Saving…")).toBeInTheDocument();
    expect(dialog.getByRole("progressbar", { name: "Upload progress" })).not.toHaveAttribute("aria-valuenow");

    await act(async () => finish(doc("NDA", "client")));
    expect(await screen.findByText("Client NDA saved for Cedar Freight.")).toBeInTheDocument();
    expect(props.onUploaded).toHaveBeenCalledWith({ mode: "client", kind: "NDA", clientId: CLIENT_ID });
    expect(props.onOpenChange).toHaveBeenCalledWith(false);
  });

  it("over a client copy says it adds a new version", async () => {
    renderDialog({
      target: { mode: "client", clientId: CLIENT_ID, clientName: "Cedar Freight", kind: "MSA", lockTarget: true },
    });
    expect(
      await screen.findByText("This adds a new version of this client's MSA. The earlier version stays in history."),
    ).toBeInTheDocument();
  });

  it("refuses each bad file in the browser with the server's message and keeps Upload disabled", async () => {
    renderDialog();
    const cases: [File, string][] = [
      [pdf("fake.pdf", "just text"), MSG_NOT_PDF],
      [pdf("notes.txt"), MSG_TYPE],
      [new File([], "empty.pdf"), MSG_EMPTY],
    ];
    for (const [file, message] of cases) {
      chooseFile(file);
      expect(await screen.findByRole("alert")).toHaveTextContent(message);
      expect(screen.getByRole("button", { name: "Upload" })).toBeDisabled();
    }
    const big = pdf("big.pdf");
    Object.defineProperty(big, "size", { value: 26 * 1024 * 1024 });
    chooseFile(big);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(MSG_TOO_LARGE));
    expect(screen.queryByText("Will be stored as")).toBeNull();
  });

  it("shows the server's refusal and lets the person try again", async () => {
    vi.spyOn(agreementsApi, "uploadClientCopy").mockRejectedValue(new ApiError(415, { detail: MSG_NOT_PDF }, MSG_NOT_PDF));
    const props = renderDialog();
    chooseFile(pdf("Cedar.pdf"));
    await screen.findByText("Will be stored as");
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(MSG_NOT_PDF);
    expect(screen.getByRole("button", { name: "Upload" })).toBeEnabled();
    expect(props.onUploaded).not.toHaveBeenCalled();
  });

  it("does not close on Escape while the file is being sent", async () => {
    vi.spyOn(agreementsApi, "uploadClientCopy").mockReturnValue(new Promise<DocCard>(() => undefined));
    const props = renderDialog();
    chooseFile(pdf("Cedar.pdf"));
    await screen.findByText("Will be stored as");
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(props.onOpenChange).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("renders a hostile file name as text", async () => {
    renderDialog();
    chooseFile(pdf("<img src=x onerror=alert(1)>.pdf"));
    expect(await screen.findByText("Will be stored as")).toBeInTheDocument();
    expect(screen.getByText(/<img src=x onerror=alert\(1\)>\.pdf/)).toBeInTheDocument();
    expect(screen.getByText("_img src_x onerror_alert_1_.pdf")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });
});

describe("client picker", () => {
  function row(id: string, name: string, unit: "ST21" | "IT Avalon" | "Retro Rabbit"): ClientRow {
    return {
      client_id: id,
      name,
      relationship: "existing",
      relationship_basis: "closed_won",
      requirement: "none",
      nda: { state: "existing_none" },
      msa: { state: "existing_none" },
      needs_attention: false,
      furthest_open_stage: 0,
      business_units: [{ name: unit, region: unit === "Retro Rabbit" ? "South Africa" : "US" }],
      deal_count: 1,
      flags: ["possible_duplicate"],
    };
  }

  it("searches the Agreements clients by name, tells same-name clients apart and sends the chosen id", async () => {
    const second = "c0000000-0000-4000-8000-0000000000c2";
    const search = vi.spyOn(agreementsApi, "getAgreementsWorkspace").mockResolvedValue({
      items: [row(CLIENT_ID, "Jasper Energy", "ST21"), row(second, "Jasper Energy", "Retro Rabbit")],
      total: 2,
    } as AgreementsWorkspace);
    const upload = vi.spyOn(agreementsApi, "uploadClientCopy").mockResolvedValue(doc("NDA", "client"));
    const props = renderDialog({ target: { mode: "client" } });
    const field = screen.getByRole("combobox", { name: "Client" });
    expect(field).toHaveAttribute("placeholder", "Start typing a client name");
    expect(screen.getByLabelText("What is this?")).toBeEnabled();

    chooseFile(pdf("Jasper.pdf"));
    await screen.findByText("Will be stored as");
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a client from the list.");
    expect(upload).not.toHaveBeenCalled();

    fireEvent.focus(field);
    fireEvent.change(field, { target: { value: "Jasper" } });
    const option = await screen.findByRole("option", { name: /Retro Rabbit · South Africa/ });
    expect(search).toHaveBeenLastCalledWith({ q: "Jasper", sort: "name", page: 1, page_size: 25 }, expect.anything());
    expect(within(screen.getByRole("listbox", { name: "Clients" })).getAllByRole("option")).toHaveLength(2);
    fireEvent.click(option);
    expect(field).toHaveValue("Jasper Energy");
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    await waitFor(() => expect(upload).toHaveBeenCalledWith(second, "NDA", expect.any(File), "", expect.any(Function)));
    await waitFor(() => expect(props.onUploaded).toHaveBeenCalledWith({ mode: "client", kind: "NDA", clientId: second }));
  });

  it("Escape closes an open client list first, not the dialog", async () => {
    vi.spyOn(agreementsApi, "getAgreementsWorkspace").mockResolvedValue({
      items: [row(CLIENT_ID, "Jasper Energy", "ST21")],
      total: 1,
    } as AgreementsWorkspace);
    const props = renderDialog({ target: { mode: "client" } });
    const field = screen.getByRole("combobox", { name: "Client" });
    fireEvent.focus(field);
    fireEvent.change(field, { target: { value: "Jas" } });
    await screen.findByRole("option", { name: /Jasper Energy/ });
    fireEvent.keyDown(field, { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(props.onOpenChange).not.toHaveBeenCalled();
  });
});

describe("standard copy", () => {
  it("says which version it adds, follows the chosen type in the title and confirms the version", async () => {
    vi.mocked(agreementsApi.getStandardDocuments).mockResolvedValue({ NDA: null, MSA: standardVersion("MSA", 1) });
    const upload = vi.spyOn(agreementsApi, "uploadStandard").mockResolvedValue(standardVersion("NDA", 1));
    const props = renderDialog({ target: { mode: "standard", kind: "MSA" } });
    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByText("Standard copy", { selector: "p" })).toBeInTheDocument();
    expect(dialog.getByRole("heading", { name: "Upload standard MSA" })).toBeInTheDocument();
    expect(
      await dialog.findByText(
        "This adds version 2 of the standard MSA. Copies already attached to clients stay as they are.",
      ),
    ).toBeInTheDocument();
    expect(dialog.queryByLabelText("Client")).toBeNull();
    expect(dialog.queryByLabelText("Note about this version (optional)")).toBeNull();

    fireEvent.change(dialog.getByLabelText("Document type"), { target: { value: "NDA" } });
    expect(dialog.getByRole("heading", { name: "Upload standard NDA" })).toBeInTheDocument();
    expect(
      dialog.getByText("This becomes the standard NDA. You attach it to existing clients in one step afterwards."),
    ).toBeInTheDocument();

    chooseFile(pdf("SmarTek21_Standard_NDA.pdf"));
    await dialog.findByText("Will be stored as");
    fireEvent.click(dialog.getByRole("button", { name: "Upload" }));
    await waitFor(() => expect(upload).toHaveBeenCalledWith("NDA", expect.any(File), expect.any(Function)));
    expect(await screen.findByText("Standard NDA v1 uploaded.")).toBeInTheDocument();
    expect(props.onUploaded).toHaveBeenCalledWith({ mode: "standard", kind: "NDA", clientId: null });
  });

  it("from the attach wizard shows Back to attach and returns there after the upload", async () => {
    vi.spyOn(agreementsApi, "uploadStandard").mockResolvedValue(standardVersion("NDA", 1));
    const onBackToWizard = vi.fn();
    const props = renderDialog({ target: { mode: "standard", kind: "NDA", fromWizard: true }, onBackToWizard });
    fireEvent.click(screen.getByRole("button", { name: "Back to attach" }));
    expect(onBackToWizard).toHaveBeenCalledTimes(1);
    chooseFile(pdf("NDA.pdf"));
    await screen.findByText("Will be stored as");
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    await waitFor(() => expect(onBackToWizard).toHaveBeenCalledTimes(2));
    expect(props.onUploaded).toHaveBeenCalledWith({ mode: "standard", kind: "NDA", clientId: null });
    expect(props.onOpenChange).not.toHaveBeenCalled();
  });
});

describe("dialog behaviour", () => {
  function Harness() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button type="button" onClick={() => setOpen(true)}>
          Open upload
        </button>
        <UploadDialog
          open={open}
          target={{ mode: "standard", kind: "NDA" }}
          canWrite
          onOpenChange={setOpen}
          onUploaded={() => undefined}
        />
      </>
    );
  }

  it("Escape closes it, the page behind is hidden from assistive tech meanwhile, and focus returns", async () => {
    render(
      <Providers>
        <Harness />
      </Providers>,
    );
    const opener = screen.getByRole("button", { name: "Open upload" });
    opener.focus();
    fireEvent.click(opener);
    const dialog = await screen.findByRole("dialog");
    expect(opener.closest("[aria-hidden='true']")).not.toBeNull();
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(opener));
  });

  it("a non-writer gets the reason instead of a form", () => {
    renderDialog({ canWrite: false });
    expect(
      screen.getByText("Only Legal and SystemAdmin can change agreements. You can view and download."),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Choose a file")).toBeNull();
  });
});
