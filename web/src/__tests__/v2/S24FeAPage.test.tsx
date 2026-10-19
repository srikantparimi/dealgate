// S24-AG1 FE-A · the NDA & MSA page shell (F1, F10, F12): header, cutover line,
// six cards with reset-then-drill, standard panels, the Clients list, filters in
// the URL, chips, locked-not-hidden write controls per role, one dialog at a
// time with focus return, the old links, export, hostile names and no raw ids.
// The shared dialogs and the client panel (lane FE-B) are stand-ins that show
// the props the page passed.
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as agreementsApi from "../../api/agreements";
import type { AgreementsWorkspace, WorkspaceQuery } from "../../api/agreements";
import * as clientApi from "../../api/client";
import {
  BATCH_DONE,
  CEDAR,
  COBALT,
  HOSTILE_NAME,
  IDS,
  LAKESIDE,
  ROLES,
  UUID_RE,
  after,
  renderAgreements,
  tonight,
} from "./S24FeAFixtures";

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

let answer: (query: Partial<WorkspaceQuery>) => AgreementsWorkspace;

beforeEach(() => {
  answer = () => tonight();
  vi.spyOn(agreementsApi, "getAgreementsWorkspace").mockImplementation(async (query) => answer(query));
  vi.spyOn(agreementsApi, "getAgreementDocuments").mockResolvedValue({ total: 0, items: [] });
  vi.spyOn(agreementsApi, "getAgreementActivity").mockResolvedValue({ total: 0, items: [] });
  vi.spyOn(clientApi, "getMe").mockResolvedValue({ id: "me", email: "me@example.com", name: "Me", groups: ["Sales"] });
});

afterEach(() => vi.restoreAllMocks());

const summary = () => screen.getByRole("region", { name: "Agreement summary" });
const lastQuery = () => vi.mocked(agreementsApi.getAgreementsWorkspace).mock.calls.at(-1)?.[0] ?? {};

describe("the page on staging tonight (no files, no cutover)", () => {
  it("shows the header, the not-set line, six cards, the standard panels and the client rows", async () => {
    renderAgreements();
    expect(await screen.findByRole("button", { name: "Cobalt Pharma" })).toBeInTheDocument();
    expect(screen.getByText("Commercial governance")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("NDA & MSA");
    expect(
      screen.getByText(
        "Standard copies cover existing clients and any pipeline clients you choose. Any client can have its own updated copy.",
      ),
    ).toBeInTheDocument();
    for (const name of [/Export view/, /HubSpot hints/, /Attach standard copies…/, /Upload document/]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }

    const line = document.querySelector('[data-state="not-set"]');
    expect(line).toHaveTextContent(
      "Not set up yet. No NDA or MSA has been uploaded. Existing and net-new are provisional until you attach the standard copies, which also sets the cutover date.",
    );

    const cards = within(summary()).getAllByRole("button");
    expect(cards.map((c) => c.textContent)).toEqual([
      "Clients20870 existing · 138 net new",
      "Existing clients7047 Closed Won · 32 with an SOW or engagement",
      "Net-new clients138Bring their own copy unless included",
      "Needs attention21Net new, past stage 1, NDA or MSA missing",
      "Standard copies attached0clients · NDA 0 · MSA 0",
      "Client copies on file0clients · NDA 0 · MSA 0",
    ]);

    const standard = screen.getByRole("region", { name: "Standard documents" });
    expect(within(standard).getByRole("heading", { name: "Standard NDA" })).toBeInTheDocument();
    expect(
      within(standard).getAllByText("Not uploaded yet. Upload it once, then attach it to every existing client in one step."),
    ).toHaveLength(2);
    expect(within(standard).getByRole("button", { name: /Upload standard NDA/ })).toBeInTheDocument();
    expect(within(standard).getByRole("button", { name: /Upload standard MSA/ })).toBeInTheDocument();

    const table = screen.getByRole("table", { name: "Clients" });
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Client",
      "Relationship",
      "Furthest open stage",
      "NDA",
      "MSA",
      "Action",
    ]);
    const cobalt = within(table).getByRole("button", { name: "Cobalt Pharma" }).closest("tr")!;
    expect(cobalt).toHaveTextContent("ST21 · US · 1 deal");
    expect(cobalt).toHaveTextContent("Net new");
    expect(cobalt).toHaveTextContent("No earlier work found");
    expect(cobalt).toHaveTextContent("6 · Contracting");
    expect(within(cobalt).getAllByText("Missing")).toHaveLength(2);
    expect(within(cobalt).getByRole("button", { name: "Upload client copy for Cobalt Pharma" })).toBeInTheDocument();

    const lakeside = within(table).getByRole("button", { name: "Lakeside Group" }).closest("tr")!;
    expect(lakeside).toHaveTextContent("Existing");
    expect(lakeside).toHaveTextContent("Closed Won deal");
    expect(lakeside).toHaveTextContent("No active deal");
    expect(lakeside).toHaveTextContent("✓ Standard copy");
    expect(lakeside).toHaveTextContent("✓ Client copy");
    expect(within(lakeside).getByRole("button", { name: "Open Lakeside Group" })).toBeInTheDocument();

    expect(screen.getByText("3 clients · same population as the cards above")).toBeInTheDocument();
    expect(screen.getByText("1–3 of 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Clients/, pressed: true })).toHaveTextContent("Clients 3");
    expect(screen.getByRole("button", { name: /^Documents/ })).toHaveTextContent("Documents 0");
    expect(screen.getByRole("button", { name: /^Activity/ })).toHaveTextContent("Activity 0");
  });

  it("colours Needs attention red above zero and green at zero", async () => {
    renderAgreements();
    await screen.findByRole("button", { name: "Cobalt Pharma" });
    const value = () => within(summary()).getByRole("button", { name: /^Needs attention/ }).querySelector("strong")!;
    expect(value()).toHaveClass("text-danger");
    answer = () => tonight({ cards: tonight().cards.map((c) => (c.key === "needs_attention" ? { ...c, value: 0 } : c)) });
    fireEvent.change(screen.getByRole("combobox", { name: "Sort" }), { target: { value: "name" } });
    await waitFor(() => expect(value()).toHaveClass("text-success"));
  });

  it("an uploaded standard copy makes the 'No NDA or MSA has been uploaded' sentence go away", async () => {
    answer = () => tonight({ standard: { NDA: after().standard.NDA, MSA: null } });
    renderAgreements();
    await screen.findByRole("button", { name: "Cobalt Pharma" });
    const line = document.querySelector('[data-state="not-set"]')!;
    expect(line).toHaveTextContent("Not set up yet. Existing and net-new are provisional");
    expect(line).not.toHaveTextContent("No NDA or MSA has been uploaded");
  });

  it("shows each business unit with its region, and a client without one says why", async () => {
    renderAgreements();
    const row = (await screen.findByRole("button", { name: HOSTILE_NAME })).closest("tr")!;
    expect(row).toHaveTextContent("Region not mapped to a business unit: Mars · 1 deal");
    expect(row).toHaveTextContent("Possible duplicate");
    expect(row).toHaveTextContent("Test data");
    expect(row).toHaveTextContent("1 · Prospecting");
    expect(within(row).getAllByText("Due at stage 2")).toHaveLength(2);
  });
});

describe("cards and filters live in the URL", () => {
  it("a card resets the filters, opens the Clients tab and applies only its drill", async () => {
    const view = renderAgreements("/agreements?tab=documents&status=missing_nda&stage=past_stage_1&q=foo&sort=name&page=3");
    await screen.findByText("No documents match this view.");
    fireEvent.click(within(summary()).getByRole("button", { name: /^Needs attention/ }));
    await screen.findByRole("table", { name: "Clients" });
    const params = view.params();
    expect(params.get("status")).toBe("attention");
    expect(params.get("sort")).toBe("name");
    expect(params.get("tab")).toBeNull();
    expect(params.get("stage")).toBeNull();
    expect(params.get("q")).toBeNull();
    expect(params.get("page")).toBeNull();
    expect(lastQuery()).toMatchObject({ status: "attention", stage: "any", q: "", page: 1, sort: "name" });
  });

  it("the Clients card clears every filter (its drill is empty)", async () => {
    const view = renderAgreements("/agreements?relationship=existing&bu=ST21");
    await screen.findByRole("button", { name: "Cobalt Pharma" });
    fireEvent.click(within(summary()).getByRole("button", { name: /^Clients/ }));
    await waitFor(() => expect(view.params().toString()).toBe(""));
  });

  it("selects change the URL and the request; chips remove one filter; Reset filters clears them all", async () => {
    const view = renderAgreements();
    await screen.findByRole("button", { name: "Cobalt Pharma" });
    const filters = within(screen.getByRole("region", { name: "Filters" }));
    expect(filters.getByRole("searchbox", { name: "Search clients" })).toHaveAttribute("placeholder", "Search clients");

    fireEvent.change(filters.getByRole("combobox", { name: "Relationship" }), { target: { value: "net_new" } });
    fireEvent.change(filters.getByRole("combobox", { name: "Agreement status" }), { target: { value: "missing_msa" } });
    fireEvent.change(filters.getByRole("combobox", { name: "Deal stage" }), { target: { value: "past_stage_1" } });
    fireEvent.change(filters.getByRole("combobox", { name: "Business unit" }), { target: { value: "Retro Rabbit" } });
    fireEvent.change(filters.getByRole("combobox", { name: "Sort" }), { target: { value: "stage" } });
    await waitFor(() =>
      expect(lastQuery()).toMatchObject({
        relationship: "net_new",
        status: "missing_msa",
        stage: "past_stage_1",
        bu: ["Retro Rabbit"],
        sort: "stage",
      }),
    );
    expect(view.params().getAll("bu")).toEqual(["Retro Rabbit"]);

    for (const chip of ["Net-new clients", "Missing MSA", "Past stage 1", "Retro Rabbit · South Africa"]) {
      expect(screen.getByRole("button", { name: `Remove ${chip}` })).toBeInTheDocument();
    }
    fireEvent.click(screen.getByRole("button", { name: "Remove Missing MSA" }));
    await waitFor(() => expect(view.params().get("status")).toBeNull());
    expect(view.params().get("relationship")).toBe("net_new");

    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    await waitFor(() => expect(view.params().toString()).toBe("sort=stage"));
    expect(screen.queryByRole("button", { name: /^Remove / })).toBeNull();
  });

  it("search waits for typing, shows a chip, and the empty view offers Reset filters", async () => {
    answer = (query) => (query.q ? tonight({ total: 0, items: [] }) : tonight());
    const view = renderAgreements();
    await screen.findByRole("button", { name: "Cobalt Pharma" });
    fireEvent.change(screen.getByRole("searchbox", { name: "Search clients" }), { target: { value: "zzzz-no-match" } });
    expect(await screen.findByText("No clients match this view.")).toBeInTheDocument();
    expect(screen.getByText("Remove a filter or reset the view.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Search: zzzz-no-match" })).toBeInTheDocument();
    expect(screen.getByText("0 clients · same population as the cards above")).toBeInTheDocument();
    // Two buttons read "Reset filters": the chips row's and the empty state's ("Reset filters →").
    const empty = screen.getByText("No clients match this view.").closest<HTMLElement>('[role="status"]')!;
    fireEvent.click(within(empty).getByRole("button", { name: "Reset filters" }));
    await waitFor(() => expect(view.params().get("q")).toBeNull());
  });

  it("paging asks for the next page; a page past the end moves to the last page", async () => {
    answer = (query) => tonight({ total: 60, items: (query.page ?? 1) > 3 ? [] : [COBALT] });
    const view = renderAgreements("/agreements?page=9");
    await waitFor(() => expect(view.params().get("page")).toBe("3"));
    expect(await screen.findByText("51–60 of 60")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
    await waitFor(() => expect(view.params().get("page")).toBe("2"));
    fireEvent.change(screen.getByRole("combobox", { name: "Rows" }), { target: { value: "50" } });
    await waitFor(() => expect(view.params().get("page_size")).toBe("50"));
    expect(view.params().get("page")).toBeNull();
  });
});

describe("roles: write controls stay visible, locked with a reason", () => {
  it("Sales sees every write control locked; a click explains why; view and download stay open", async () => {
    answer = () => tonight({ ...ROLES.sales });
    renderAgreements();
    await screen.findByRole("button", { name: "Cobalt Pharma" });

    const upload = screen.getByRole("button", { name: /Upload document/ });
    expect(upload).toHaveAttribute("aria-disabled", "true");
    expect(upload).toHaveAttribute("data-locked", "writer");
    fireEvent.click(upload);
    expect(await screen.findByText("Only Legal and SystemAdmin can change agreements. You can view and download.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Upload dialog stand-in" })).toBeNull();

    const attach = screen.getByRole("button", { name: /Attach standard copies…/ });
    expect(attach).toHaveAttribute("data-locked", "admin");
    fireEvent.click(attach);
    expect(await screen.findByText("Only SystemAdmin can attach standard copies in bulk.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Attach wizard stand-in" })).toBeNull();

    expect(screen.getByRole("button", { name: /Upload standard NDA/ })).toHaveAttribute("data-locked", "writer");
    expect(screen.getByRole("button", { name: /Upload client copy for Cobalt Pharma/ })).toHaveAttribute(
      "aria-disabled",
      "true",
    );

    expect(screen.getByRole("button", { name: /Export view/ })).not.toHaveAttribute("aria-disabled");
    fireEvent.click(screen.getByRole("button", { name: /HubSpot hints/ }));
    expect(screen.getByRole("dialog", { name: "HubSpot hints stand-in" })).toHaveAttribute("data-admin", "false");
  });

  it("Legal uploads but cannot run or undo a batch", async () => {
    answer = () => after({ ...ROLES.legal });
    renderAgreements();
    await screen.findByRole("button", { name: "Cobalt Pharma" });
    expect(screen.getByRole("button", { name: /Upload document/ })).not.toHaveAttribute("aria-disabled");
    expect(screen.getByRole("button", { name: /Attach standard copies…/ })).toHaveAttribute("data-locked", "admin");
    const undo = screen.getByRole("button", { name: /Undo batch AG-0001/ });
    expect(undo).toHaveAttribute("data-locked", "admin");
    fireEvent.click(undo);
    expect(await screen.findByText("Only SystemAdmin can do this.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Undo dialog stand-in" })).toBeNull();
  });

  it("without can_write in the answer the page asks /me once and locks by its groups", async () => {
    answer = () => {
      const ws = tonight();
      delete ws.can_write;
      delete ws.is_admin;
      return ws;
    };
    renderAgreements();
    await screen.findByRole("button", { name: "Cobalt Pharma" });
    await waitFor(() => expect(screen.getByRole("button", { name: /Upload document/ })).toHaveAttribute("data-locked", "writer"));
    expect(clientApi.getMe).toHaveBeenCalledTimes(1);
  });
});

describe("after the backfill (SystemAdmin)", () => {
  it("shows the cutover, the latest batch and the standard copies; Undo opens the undo dialog with the label", async () => {
    answer = () => after();
    renderAgreements();
    await screen.findByRole("button", { name: "Cobalt Pharma" });
    const line = document.querySelector('[data-state="set"]')!;
    expect(line).toHaveTextContent(
      "Cutover Oct 15, 2026. Clients that existed at the cutover are covered. Clients created or closing a first deal after it need their own copy. Latest batch AG-0001 attached 85 clients.",
    );
    const standard = within(screen.getByRole("region", { name: "Standard documents" }));
    expect(standard.getByText("SmarTek21_Standard_NDA.pdf · 214 KB")).toBeInTheDocument();
    expect(standard.getByText("Uploaded by Srikanth Parimi · Oct 15, 2026 · attached to 80 clients")).toBeInTheDocument();
    expect(standard.getByText("SmarTek21_Standard_MSA.pdf · 388 KB")).toBeInTheDocument();
    expect(standard.getAllByText("A new version does not change copies already attached.")).toHaveLength(2);
    expect(standard.getByRole("button", { name: "Upload new version of the standard MSA" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Documents/ })).toHaveTextContent("Documents 169");

    fireEvent.click(screen.getByRole("button", { name: "Undo batch AG-0001" }));
    expect(screen.getByRole("dialog", { name: "Undo dialog stand-in" })).toHaveAttribute("data-label", "AG-0001");
  });

  it("a running batch says how far it got and the page keeps asking until it finishes", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let running = true;
      answer = () =>
        after({
          cutover: {
            set: true,
            date: "2026-10-15",
            latest_batch: running
              ? { ...BATCH_DONE, status: "running", done_count: 50, attached_count: 90, attached_clients: 45 }
              : BATCH_DONE,
          },
        });
      renderAgreements();
      const line = await screen.findByText(/Batch AG-0001 is attaching standard copies: 50 of 85 clients done\./);
      expect(line).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Undo batch/ })).toBeNull();
      const calls = vi.mocked(agreementsApi.getAgreementsWorkspace).mock.calls.length;
      running = false;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4100);
      });
      await waitFor(() => expect(vi.mocked(agreementsApi.getAgreementsWorkspace).mock.calls.length).toBeGreaterThan(calls));
      expect(await screen.findByText(/Latest batch AG-0001 attached 85 clients\./)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("standard panels: Download opens the audited link and says so; Upload new version opens a standard upload", async () => {
    answer = () => after();
    const link = vi
      .spyOn(agreementsApi, "getStandardDownloadLink")
      .mockResolvedValue({ url: "https://files.example.test/nda", expires_in_seconds: 300, file_name: "x.pdf" });
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    renderAgreements();
    await screen.findByRole("button", { name: "Cobalt Pharma" });
    fireEvent.click(screen.getByRole("button", { name: "Download the standard NDA" }));
    await waitFor(() => expect(open).toHaveBeenCalledWith("https://files.example.test/nda", "_blank", "noopener,noreferrer"));
    expect(link).toHaveBeenCalledWith("NDA");
    expect(
      await screen.findByText(
        "A download link for the standard NDA was created. It expires in 5 minutes and the download is recorded.",
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Upload new version of the standard MSA" }));
    const dialog = screen.getByRole("dialog", { name: "Upload dialog stand-in" });
    expect(dialog).toHaveAttribute("data-mode", "standard");
    expect(dialog).toHaveAttribute("data-kind", "MSA");
  });
});

describe("dialogs: one at a time, the right target, focus back where it was", () => {
  it("a row's Upload client copy opens the upload dialog for that client and its first missing kind", async () => {
    answer = () => tonight({ items: [CEDAR, COBALT] });
    renderAgreements();
    fireEvent.click(await screen.findByRole("button", { name: "Upload client copy for Cedar Freight" }));
    const dialog = screen.getByRole("dialog", { name: "Upload dialog stand-in" });
    expect(dialog).toHaveAttribute("data-mode", "client");
    expect(dialog).toHaveAttribute("data-client", IDS.cedar);
    expect(dialog).toHaveAttribute("data-client-name", "Cedar Freight");
    expect(dialog).toHaveAttribute("data-kind", "MSA");
    expect(dialog).toHaveAttribute("data-lock-target", "true");
    expect(dialog).toHaveAttribute("data-can-write", "true");
  });

  it("the header opens a free client upload; a standard panel opens a standard upload; the hints and the wizard open", async () => {
    renderAgreements();
    await screen.findByRole("button", { name: "Cobalt Pharma" });
    fireEvent.click(screen.getByRole("button", { name: /Upload document/ }));
    let dialog = screen.getByRole("dialog", { name: "Upload dialog stand-in" });
    expect(dialog).toHaveAttribute("data-mode", "client");
    expect(dialog).toHaveAttribute("data-client", "");
    expect(dialog).toHaveAttribute("data-lock-target", "false");
    fireEvent.click(within(dialog).getByRole("button", { name: "Close upload" }));

    fireEvent.click(screen.getByRole("button", { name: /Upload standard NDA/ }));
    dialog = screen.getByRole("dialog", { name: "Upload dialog stand-in" });
    expect(dialog).toHaveAttribute("data-mode", "standard");
    expect(dialog).toHaveAttribute("data-kind", "NDA");
    fireEvent.click(within(dialog).getByRole("button", { name: "Close upload" }));

    fireEvent.click(screen.getByRole("button", { name: /Attach standard copies…/ }));
    expect(screen.getByRole("dialog", { name: "Attach wizard stand-in" })).toBeInTheDocument();
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Close wizard" }));

    fireEvent.click(screen.getByRole("button", { name: /HubSpot hints/ }));
    expect(screen.getByRole("dialog", { name: "HubSpot hints stand-in" })).toHaveAttribute("data-admin", "true");
  });

  it("after an upload the dialog closes, the page asks again, and focus returns to the row", async () => {
    renderAgreements();
    const opener = await screen.findByRole("button", { name: "Upload client copy for Cobalt Pharma" });
    opener.focus();
    fireEvent.click(opener);
    const calls = vi.mocked(agreementsApi.getAgreementsWorkspace).mock.calls.length;
    const finish = screen.getByRole("button", { name: "Finish upload" });
    finish.focus();
    // The answer after the upload: Cobalt no longer needs attention, so its upload button goes away.
    answer = () => tonight({ items: [{ ...COBALT, needs_attention: false, nda: { state: "client" } }, LAKESIDE] });
    fireEvent.click(finish);
    expect(screen.queryByRole("dialog", { name: "Upload dialog stand-in" })).toBeNull();
    await waitFor(() => expect(vi.mocked(agreementsApi.getAgreementsWorkspace).mock.calls.length).toBeGreaterThan(calls));
    await screen.findByRole("button", { name: "Open Cobalt Pharma" });
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Cobalt Pharma" })));
  });

  it("the client name opens the panel through the URL; closing it returns focus to the name", async () => {
    const view = renderAgreements();
    const name = await screen.findByRole("button", { name: "Lakeside Group" });
    name.focus();
    fireEvent.click(name);
    const panel = await screen.findByRole("dialog", { name: "Client panel stand-in" });
    expect(panel).toHaveAttribute("data-client", IDS.lakeside);
    expect(panel).toHaveAttribute("data-variant", "drawer");
    expect(view.params().get("client_id")).toBe(IDS.lakeside);
    const close = within(panel).getByRole("button", { name: "Close panel" });
    close.focus();
    fireEvent.click(close);
    await waitFor(() => expect(view.params().get("client_id")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(name));
  });

  it("a change made in the panel refreshes the page's numbers", async () => {
    renderAgreements("/agreements?client_id=" + IDS.cobalt);
    const panel = await screen.findByRole("dialog", { name: "Client panel stand-in" });
    await screen.findByRole("button", { name: "Cobalt Pharma" });
    const calls = vi.mocked(agreementsApi.getAgreementsWorkspace).mock.calls.length;
    fireEvent.click(within(panel).getByRole("button", { name: "Report a change" }));
    await waitFor(() => expect(vi.mocked(agreementsApi.getAgreementsWorkspace).mock.calls.length).toBeGreaterThan(calls));
  });
});

describe("old links keep working", () => {
  it("?client_id= (and the S17 ?client=) opens that client's panel", async () => {
    renderAgreements(`/agreements?client=${IDS.lakeside}`);
    expect(await screen.findByRole("dialog", { name: "Client panel stand-in" })).toHaveAttribute("data-client", IDS.lakeside);
  });

  it("?client_id=…&kind=MSA&upload=1 opens the upload dialog for a writer, then the client's panel", async () => {
    const view = renderAgreements(`/agreements?client_id=${IDS.cobalt}&kind=MSA&upload=1`);
    const dialog = await screen.findByRole("dialog", { name: "Upload dialog stand-in" });
    expect(dialog).toHaveAttribute("data-client", IDS.cobalt);
    expect(dialog).toHaveAttribute("data-client-name", "Cobalt Pharma");
    expect(dialog).toHaveAttribute("data-kind", "MSA");
    expect(dialog).toHaveAttribute("data-lock-target", "true");
    await waitFor(() => expect(view.params().get("upload")).toBeNull());
    expect(view.params().get("kind")).toBeNull();
    expect(screen.queryByRole("dialog", { name: "Client panel stand-in" })).toBeNull();
    fireEvent.click(within(dialog).getByRole("button", { name: "Close upload" }));
    expect(await screen.findByRole("dialog", { name: "Client panel stand-in" })).toHaveAttribute("data-client", IDS.cobalt);
  });

  it("the same link for Sales opens the panel and says why there is no upload", async () => {
    answer = () => tonight({ ...ROLES.sales });
    renderAgreements(`/agreements?client_id=${IDS.cobalt}&kind=NDA&upload=1`);
    expect(await screen.findByRole("dialog", { name: "Client panel stand-in" })).toHaveAttribute("data-client", IDS.cobalt);
    expect(screen.queryByRole("dialog", { name: "Upload dialog stand-in" })).toBeNull();
    expect(await screen.findByText("Only Legal and SystemAdmin can change agreements. You can view and download.")).toBeInTheDocument();
  });

  it("the Command Center tile's link opens the Needs-attention view", async () => {
    renderAgreements("/agreements?status=attention");
    await screen.findByRole("button", { name: "Cobalt Pharma" });
    expect(lastQuery()).toMatchObject({ status: "attention" });
    expect(screen.getByRole("combobox", { name: "Agreement status" })).toHaveValue("attention");
    expect(screen.getByRole("button", { name: "Remove Needs attention" })).toBeInTheDocument();
  });
});

describe("export, escaping and ids", () => {
  it("Export view downloads the CSV of the filtered view (every row) and says so", async () => {
    const download = vi.spyOn(agreementsApi, "downloadAgreementsCsv").mockResolvedValue("DealGate_Agreements.csv");
    renderAgreements("/agreements?relationship=net_new&q=co&page=2");
    await screen.findByRole("button", { name: "Cobalt Pharma" });
    fireEvent.click(screen.getByRole("button", { name: /Export view/ }));
    await waitFor(() => expect(download).toHaveBeenCalledTimes(1));
    expect(download.mock.calls[0][0]).toMatchObject({ relationship: "net_new", q: "co" });
    expect(await screen.findByText("Downloaded DealGate_Agreements.csv.")).toBeInTheDocument();
    expect(screen.getByText("3 clients from the filtered view, every row, not just this page.")).toBeInTheDocument();
  });

  it("a failed export says so and keeps the page", async () => {
    vi.spyOn(agreementsApi, "downloadAgreementsCsv").mockRejectedValue(new Error("403: not allowed"));
    renderAgreements();
    await screen.findByRole("button", { name: "Cobalt Pharma" });
    fireEvent.click(screen.getByRole("button", { name: /Export view/ }));
    expect(await screen.findByText("The export could not download.")).toBeInTheDocument();
    expect(screen.getByText("403: not allowed")).toBeInTheDocument();
  });

  it("renders a hostile client name as text and never shows a raw id", async () => {
    answer = () => after();
    const { container } = renderAgreements();
    await screen.findByRole("button", { name: HOSTILE_NAME });
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByRole("button", { name: HOSTILE_NAME })).toHaveTextContent(HOSTILE_NAME);
    expect(document.body.textContent ?? "").not.toMatch(UUID_RE);
  });

  it("a failed load says so with Try again", async () => {
    vi.mocked(agreementsApi.getAgreementsWorkspace).mockRejectedValue(new Error("Service unavailable"));
    renderAgreements();
    expect(await screen.findByText("The clients could not load.")).toBeInTheDocument();
    expect(screen.getByText("Service unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
