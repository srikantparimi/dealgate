// S24-AG1 FE-A · the Documents tab (F8: the old register kept, with source,
// batch label, Pacific dates, audited download, history and replace) and the
// Activity tab (F9: the audit-log feed and its empty state). Each list is asked
// for only while its tab is open, with the tab's own search and page.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as agreementsApi from "../../api/agreements";
import * as clientApi from "../../api/client";
import { ACTIVITY, DOC_CLIENT, DOC_STANDARD, IDS, ROLES, UUID_RE, after, renderAgreements } from "./S24FeAFixtures";

vi.mock("../../pages/v2/agreements/UploadDialog", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../pages/v2/agreements/UploadDialog")>()),
  UploadDialog: (await import("./S24FeAStandIns")).UploadDialogStandIn,
}));
vi.mock("../../pages/v2/agreements/ClientAgreementsPanel", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../pages/v2/agreements/ClientAgreementsPanel")>()),
  ClientAgreementsPanel: (await import("./S24FeAStandIns")).ClientAgreementsPanelStandIn,
}));
vi.mock("../../pages/v2/agreements/AttachWizard", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../pages/v2/agreements/AttachWizard")>()),
  AttachWizard: (await import("./S24FeAStandIns")).AttachWizardStandIn,
}));
vi.mock("../../pages/v2/agreements/UndoBatchDialog", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../pages/v2/agreements/UndoBatchDialog")>()),
  UndoBatchDialog: (await import("./S24FeAStandIns")).UndoBatchDialogStandIn,
}));
vi.mock("../../pages/v2/agreements/HubspotHintsDialog", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../pages/v2/agreements/HubspotHintsDialog")>()),
  HubspotHintsDialog: (await import("./S24FeAStandIns")).HubspotHintsDialogStandIn,
}));

let role: keyof typeof ROLES = "admin";

beforeEach(() => {
  role = "admin";
  vi.spyOn(agreementsApi, "getAgreementsWorkspace").mockImplementation(async () => after({ ...ROLES[role] }));
  vi.spyOn(agreementsApi, "getAgreementDocuments").mockImplementation(async (query) =>
    query.q === "nothing" ? { total: 0, items: [] } : { total: 2, items: [DOC_CLIENT, DOC_STANDARD] },
  );
  vi.spyOn(agreementsApi, "getAgreementActivity").mockResolvedValue({ total: 3, items: ACTIVITY });
  vi.spyOn(clientApi, "getMe").mockResolvedValue({ id: "me", email: "me@example.com", name: "Me", groups: ["Sales"] });
});

afterEach(() => vi.restoreAllMocks());

describe("the Documents tab", () => {
  it("is asked for only when open, and shows the old register with source, batch label and Pacific dates", async () => {
    renderAgreements();
    await screen.findByRole("button", { name: "Cobalt Pharma" });
    expect(agreementsApi.getAgreementDocuments).not.toHaveBeenCalled();
    expect(agreementsApi.getAgreementActivity).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /^Documents/ }));
    const table = await screen.findByRole("table", { name: "Documents" });
    expect(agreementsApi.getAgreementDocuments).toHaveBeenCalledTimes(1);
    expect(vi.mocked(agreementsApi.getAgreementDocuments).mock.calls[0][0]).toEqual({ q: "", page: 1, page_size: 25 });
    expect(screen.getByRole("searchbox", { name: "Search by client, type, file name or uploader" })).toHaveAttribute(
      "placeholder",
      "Search by client, type, file name or uploader",
    );
    // The client filters belong to the Clients tab.
    expect(screen.queryByRole("combobox", { name: "Relationship" })).toBeNull();
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Client",
      "Type",
      "File",
      "Source",
      "Uploaded by",
      "Uploaded",
      "Action",
    ]);
    expect(screen.getByText("2 documents · one row per client and type")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Documents/, pressed: true })).toHaveTextContent("Documents 2");

    const standard = within(table).getByText("SmarTek21_Standard_NDA.pdf").closest("tr")!;
    expect(standard).toHaveTextContent("Standard v1");
    expect(standard).toHaveTextContent("Batch AG-0001");
    expect(standard).toHaveTextContent("Srikanth Parimi");
    // 2026-10-16T05:30Z is Oct 15 in Los Angeles.
    expect(standard).toHaveTextContent("Oct 15, 2026");
    const own = within(table).getByText("Lakeside-Group-MSA-client-copy.pdf").closest("tr")!;
    expect(own).toHaveTextContent("Client copy");
    expect(own).toHaveTextContent("Legal user");
    expect(document.body.textContent ?? "").not.toMatch(UUID_RE);
  });

  it("Download goes through the audited client route, opens the link and says it is recorded", async () => {
    const link = vi
      .spyOn(agreementsApi, "getClientDownloadLink")
      .mockResolvedValue({ url: "https://files.example.test/msa", expires_in_seconds: 300, file_name: "x.pdf" });
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    renderAgreements("/agreements?tab=documents");
    await screen.findByRole("table", { name: "Documents" });
    const calls = vi.mocked(agreementsApi.getAgreementsWorkspace).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Download Lakeside Group MSA" }));
    await waitFor(() => expect(open).toHaveBeenCalledWith("https://files.example.test/msa", "_blank", "noopener,noreferrer"));
    expect(link).toHaveBeenCalledWith(IDS.lakeside, "MSA");
    expect(
      await screen.findByText(
        "A download link for Lakeside Group's MSA was created. It expires in 5 minutes and the download is recorded.",
      ),
    ).toBeInTheDocument();
    // The download is recorded: the Activity count is asked for again.
    await waitFor(() => expect(vi.mocked(agreementsApi.getAgreementsWorkspace).mock.calls.length).toBeGreaterThan(calls));
  });

  it("never shows a batch id that is not a label", async () => {
    vi.mocked(agreementsApi.getAgreementDocuments).mockResolvedValue({
      total: 1,
      items: [{ ...DOC_STANDARD, batch_id: "7d444840-9dc0-11d1-b245-5ffdce74fad2" }],
    });
    renderAgreements("/agreements?tab=documents");
    const row = (await screen.findByText("SmarTek21_Standard_NDA.pdf")).closest("tr")!;
    expect(row).toHaveTextContent("Standard v1");
    expect(row).not.toHaveTextContent("Batch");
    expect(document.body.textContent ?? "").not.toMatch(UUID_RE);
  });

  it("empty: the prototype's empty state; a search with no match offers Reset filters", async () => {
    vi.mocked(agreementsApi.getAgreementDocuments).mockResolvedValue({ total: 0, items: [] });
    const view = renderAgreements("/agreements?tab=documents");
    expect(await screen.findByText("No documents yet.")).toBeInTheDocument();
    expect(screen.getByText("Upload the standard NDA and MSA, or a client copy.")).toBeInTheDocument();
    expect(screen.getByText("0 documents · one row per client and type")).toBeInTheDocument();
    expect(screen.getByText("0–0 of 0")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("searchbox", { name: "Search by client, type, file name or uploader" }), {
      target: { value: "nothing" },
    });
    expect(await screen.findByText("No documents match this view.")).toBeInTheDocument();
    await waitFor(() =>
      expect(vi.mocked(agreementsApi.getAgreementDocuments).mock.calls.at(-1)?.[0]).toEqual({
        q: "nothing",
        page: 1,
        page_size: 25,
      }),
    );
    expect(view.params().get("q")).toBe("nothing");
  });

  it("switching tabs clears the search and the page but keeps the client filters", async () => {
    const view = renderAgreements("/agreements?status=attention&q=cob&page=2");
    await screen.findByRole("button", { name: "Cobalt Pharma" });
    fireEvent.click(screen.getByRole("button", { name: /^Documents/ }));
    await screen.findByRole("table", { name: "Documents" });
    expect(view.params().get("tab")).toBe("documents");
    expect(view.params().get("q")).toBeNull();
    expect(view.params().get("page")).toBeNull();
    expect(view.params().get("status")).toBe("attention");
    // The workspace keeps answering the cards and counts without the documents search.
    expect(vi.mocked(agreementsApi.getAgreementsWorkspace).mock.calls.at(-1)?.[0]).toMatchObject({
      status: "attention",
      q: "",
      page: 1,
    });
  });

  it("History lists every version and downloads one; Escape closes it and focus returns", async () => {
    vi.spyOn(clientApi, "listAgreementVersions").mockResolvedValue({
      items: [
        {
          version_no: 2,
          filename: "Lakeside-Group-MSA-client-copy.pdf",
          file_size: 150_000,
          file_hash: null,
          uploaded_by: "u-2",
          uploaded_by_name: "Legal user",
          uploaded_at: "2026-10-15T20:00:00Z",
          note: "Updated payment terms",
          source: "client",
        } as clientApi.AgreementFileVersion,
        {
          version_no: 1,
          filename: "SmarTek21_Standard_MSA.pdf",
          file_size: 388_000,
          file_hash: null,
          uploaded_by: "u-1",
          uploaded_by_name: "Srikanth Parimi",
          uploaded_at: "2026-10-15T18:00:00Z",
          source: "standard",
          standard_version: 1,
          batch_id: "AG-0001",
        } as clientApi.AgreementFileVersion,
      ],
    });
    const versionLink = vi
      .spyOn(clientApi, "getAgreementVersionDownloadUrl")
      .mockResolvedValue({ url: "https://files.example.test/v1", filename: "SmarTek21_Standard_MSA.pdf" });
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    renderAgreements("/agreements?tab=documents");
    await screen.findByRole("table", { name: "Documents" });
    const history = screen.getByRole("button", { name: "History of Lakeside Group MSA" });
    history.focus();
    fireEvent.click(history);

    const drawer = await screen.findByRole("dialog", { name: "MSA document history" });
    expect(clientApi.listAgreementVersions).toHaveBeenCalledWith(DOC_CLIENT.agreement_id);
    expect(await within(drawer).findByText("v2: Lakeside-Group-MSA-client-copy.pdf")).toBeInTheDocument();
    expect(within(drawer).getByText("Legal user · Oct 15, 2026")).toBeInTheDocument();
    expect(within(drawer).getByText("Note: Updated payment terms")).toBeInTheDocument();
    expect(within(drawer).getByText("Standard copy v1 · batch AG-0001")).toBeInTheDocument();
    // The page behind the drawer is hidden from assistive technology while it is open.
    expect(screen.getByRole("table", { name: "Documents", hidden: true }).closest("[aria-hidden='true']")).not.toBeNull();

    fireEvent.click(within(drawer).getByRole("button", { name: "Download version 1" }));
    await waitFor(() => expect(open).toHaveBeenCalledWith("https://files.example.test/v1", "_blank", "noopener,noreferrer"));
    expect(versionLink).toHaveBeenCalledWith(DOC_CLIENT.agreement_id, 1);
    expect(
      await within(drawer).findByText(
        "A download link for version 1 was created. It expires in 5 minutes and the download is recorded.",
      ),
    ).toBeInTheDocument();

    fireEvent.keyDown(drawer, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "MSA document history" })).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "History of Lakeside Group MSA" })));
  });

  it("Replace opens the upload dialog for that client and kind; Sales sees it locked, with Download and History open", async () => {
    renderAgreements("/agreements?tab=documents");
    await screen.findByRole("table", { name: "Documents" });
    fireEvent.click(screen.getByRole("button", { name: "Replace Lakeside Group NDA" }));
    const dialog = screen.getByRole("dialog", { name: "Upload dialog stand-in" });
    expect(dialog).toHaveAttribute("data-mode", "client");
    expect(dialog).toHaveAttribute("data-client", IDS.lakeside);
    expect(dialog).toHaveAttribute("data-kind", "NDA");
    expect(dialog).toHaveAttribute("data-lock-target", "true");
  });
});

describe("the Activity tab", () => {
  it("reads the audit-log feed: When (Pacific date), Who, What", async () => {
    renderAgreements();
    await screen.findByRole("button", { name: "Cobalt Pharma" });
    fireEvent.click(screen.getByRole("button", { name: /^Activity/ }));
    const table = await screen.findByRole("table", { name: "Activity" });
    expect(screen.getByRole("searchbox", { name: "Search activity" })).toBeInTheDocument();
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["When", "Who", "What"]);
    expect(screen.getByText("3 events · uploads, attachments, marks, undo and downloads")).toBeInTheDocument();
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("Oct 15, 2026");
    expect(rows[0]).toHaveTextContent("Legal user");
    expect(rows[0]).toHaveTextContent("Uploaded client copies for 10 clients");
    expect(rows[1]).toHaveTextContent(
      "Attached standard copies to 85 clients (batch AG-0001, NDA and MSA): 67 existing and 18 net new in the pipeline",
    );
    expect(document.body.textContent ?? "").not.toMatch(UUID_RE);
  });

  it("empty: the prototype's empty state", async () => {
    vi.mocked(agreementsApi.getAgreementActivity).mockResolvedValue({ total: 0, items: [] });
    renderAgreements("/agreements?tab=activity");
    expect(await screen.findByText("No agreement activity yet.")).toBeInTheDocument();
    expect(
      screen.getByText("Every upload, attach, mark, undo and download is recorded here and in the audit log."),
    ).toBeInTheDocument();
    expect(screen.getByText("0 events · uploads, attachments, marks, undo and downloads")).toBeInTheDocument();
  });

  it("without an activity count in the workspace the tab shows no number rather than a zero", async () => {
    vi.mocked(agreementsApi.getAgreementsWorkspace).mockImplementation(async () => {
      const ws = after();
      delete ws.activity_count;
      return ws;
    });
    renderAgreements();
    await screen.findByRole("button", { name: "Cobalt Pharma" });
    expect(screen.getByRole("button", { name: /^Activity/ }).textContent).toBe("Activity ");
  });
});

describe("Sales on the Documents tab", () => {
  it("keeps Replace visible but locked; Download and History stay open", async () => {
    role = "sales";
    renderAgreements("/agreements?tab=documents");
    await screen.findByRole("table", { name: "Documents" });
    const replace = screen.getByRole("button", { name: "Replace Lakeside Group MSA" });
    expect(replace).toHaveAttribute("aria-disabled", "true");
    expect(replace).toHaveAttribute("data-locked", "writer");
    fireEvent.click(replace);
    expect(await screen.findByText("Only Legal and SystemAdmin can change agreements. You can view and download.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Upload dialog stand-in" })).toBeNull();
    expect(screen.getByRole("button", { name: "Download Lakeside Group MSA" })).not.toHaveAttribute("aria-disabled");
    expect(screen.getByRole("button", { name: "History of Lakeside Group MSA" })).not.toHaveAttribute("aria-disabled");
  });
});
