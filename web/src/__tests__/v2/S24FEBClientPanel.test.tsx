// S24-AG1 F3 · the shared client panel: the prototype's information and copy for every state, the
// writer lock with its reason, mark / remove / relationship / attach / upload / download against the
// typed API, the deletion receipt without its id, focus and Escape, escaping, and the Pipeline section.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState, type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as agreementsApi from "../../api/agreements";
import type { AgreementKind, ClientAgreements, DocCard, DocState, StandardVersion } from "../../api/agreements";
import { ApiError } from "../../api/client";
import {
  ClientAgreementsPanel,
  type ClientAgreementsPanelProps,
} from "../../pages/v2/agreements/ClientAgreementsPanel";
import { pacificToday } from "../../pages/v2/agreements/UploadForm";
import { Toaster } from "../../ui-v2/primitives/toaster";
import { TooltipProvider } from "../../ui-v2/primitives/tooltip";

const CLIENT_ID = "c0000000-0000-4000-8000-0000000000a1";
const UUID_TEXT = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const WRITER_LOCK = "Only Legal and SystemAdmin can change agreements. You can view and download.";

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

function panel(overrides: Partial<ClientAgreements> & { stage_text?: string } = {}): ClientAgreements {
  return {
    client_id: CLIENT_ID,
    name: "Cobalt Pharma",
    relationship: "net_new",
    relationship_basis: "none",
    requirement: "required",
    needs_attention: true,
    possible_duplicates: [],
    deals: { open: 1, won: 0, lost: 0, furthest_open_stage: 6 },
    nda: doc("NDA", "missing"),
    msa: doc("MSA", "missing"),
    can_write: true,
    business_units: [{ name: "ST21", region: "US" }],
    flags: [],
    basis_text: "No earlier work found",
    stage_text: "6 · Contracting",
    ...overrides,
  } as ClientAgreements;
}

function standardVersion(kind: AgreementKind): StandardVersion {
  return {
    kind,
    version: 1,
    file_name: `SmarTek21_Standard_${kind}.pdf`,
    file_size: 214000,
    uploaded_by: "Srikanth Parimi",
    uploaded_at: "2026-10-15T18:00:00Z",
    attached_clients: 85,
  };
}

const STANDARD_NDA = doc("NDA", "standard", {
  agreement_id: "a0000000-0000-4000-8000-000000000001",
  source: "standard",
  standard_version: 1,
  batch_id: "AG-0001",
  file_name: "SmarTek21_Standard_NDA.pdf",
  file_size: 214000,
  version_no: 1,
  uploaded_by: "Srikanth Parimi",
  uploaded_at: "2026-10-15T18:00:00Z",
});

const CLIENT_MSA = doc("MSA", "client", {
  agreement_id: "a0000000-0000-4000-8000-000000000002",
  source: "client",
  file_name: "Lakeside-Group-MSA-client-copy.pdf",
  file_size: 150000,
  version_no: 2,
  uploaded_by: "Legal user",
  uploaded_at: "2026-10-15T20:30:00Z",
  note: "Updated payment terms",
  history: [
    { at: "2026-10-15T18:00:00Z", by: "Srikanth Parimi", what: "Standard MSA v1 attached (batch AG-0001)" },
    { at: "2026-10-15T20:30:00Z", by: "Legal user", what: "Replaced with a client copy: Updated payment terms" },
  ],
});

function renderPanel(overrides: Partial<ClientAgreementsPanelProps> = {}) {
  const props: ClientAgreementsPanelProps = {
    clientId: CLIENT_ID,
    variant: "drawer",
    open: true,
    onOpenChange: vi.fn(),
    onChanged: vi.fn(),
    ...overrides,
  };
  render(
    <Providers>
      <ClientAgreementsPanel {...props} />
    </Providers>,
  );
  return props;
}

const card = (kind: AgreementKind) => within(screen.getByRole("article", { name: kind }));

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(agreementsApi, "getClientAgreements").mockResolvedValue(panel());
  vi.spyOn(agreementsApi, "getStandardDocuments").mockResolvedValue({ NDA: null, MSA: null });
  vi.spyOn(agreementsApi, "getHubspotValues").mockResolvedValue({ stored: false, items: [] });
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("what the panel shows", () => {
  it("a net-new client past stage 1 with both missing: the warning, the facts and both cards", async () => {
    renderPanel();
    const dialog = within(await screen.findByRole("dialog"));
    expect(await dialog.findByRole("heading", { name: "Cobalt Pharma" })).toBeInTheDocument();
    expect(dialog.getByText("Client · agreements")).toBeInTheDocument();
    expect(
      dialog.getByText(
        "This client is net new and past stage 1 with NDA and MSA missing. This is a warning only. Nothing is blocked.",
      ),
    ).toBeInTheDocument();
    expect(dialog.getByText("Net new")).toBeInTheDocument();
    expect(dialog.getByText("No earlier work found")).toBeInTheDocument();
    expect(dialog.getByText("ST21")).toBeInTheDocument();
    expect(dialog.getByText("· US")).toBeInTheDocument();
    expect(dialog.getByText("1 open (furthest: 6 · Contracting)")).toBeInTheDocument();
    const link = dialog.getByRole("link", { name: "Open deals in Pipeline" });
    const href = new URL(link.getAttribute("href")!, "http://dealgate.test");
    expect(href.pathname).toBe("/pipeline");
    expect(href.searchParams.get("status")).toBe("all");
    expect(href.searchParams.get("q")).toBe("Cobalt Pharma");
    for (const kind of ["NDA", "MSA"] as const) {
      expect(card(kind).getByText("Missing")).toBeInTheDocument();
      expect(card(kind).getByText("Required: this client is net new and past stage 1.")).toBeInTheDocument();
      expect(card(kind).getByRole("button", { name: "Upload client copy" })).toBeInTheDocument();
      expect(card(kind).getByRole("button", { name: "Mark covered" })).toBeInTheDocument();
      // No standard copy uploaded yet: nothing to attach.
      expect(card(kind).queryByRole("button", { name: "Attach standard copy" })).toBeNull();
      expect(card(kind).queryByRole("button", { name: "Download" })).toBeNull();
    }
    expect(dialog.queryByText(/Prototype/)).toBeNull();
  });

  it("standard and client copies: file, source with its batch label, uploader, note, version and history", async () => {
    vi.mocked(agreementsApi.getClientAgreements).mockResolvedValue(
      panel({
        relationship: "existing",
        relationship_basis: "closed_won",
        basis_text: "Closed Won deal",
        needs_attention: false,
        deals: { open: 0, won: 1, lost: 1, furthest_open_stage: 0 },
        nda: STANDARD_NDA,
        msa: CLIENT_MSA,
      }),
    );
    renderPanel();
    await screen.findByRole("article", { name: "NDA" });
    expect(screen.getByText("1 Closed Won · 1 Closed Lost")).toBeInTheDocument();
    expect(card("NDA").getByText("✓ Standard copy")).toBeInTheDocument();
    expect(card("NDA").getByText("SmarTek21_Standard_NDA.pdf · 214 KB")).toBeInTheDocument();
    expect(card("NDA").getByText("Standard NDA v1 · batch AG-0001")).toBeInTheDocument();
    expect(card("NDA").getByText("Srikanth Parimi · Oct 15, 2026")).toBeInTheDocument();
    expect(card("NDA").getByRole("button", { name: "Replace with client copy" })).toBeInTheDocument();
    expect(card("NDA").getByRole("button", { name: "Remove from client" })).toBeInTheDocument();
    expect(card("NDA").queryByRole("button", { name: "Mark covered" })).toBeNull();

    expect(card("MSA").getByText("✓ Client copy")).toBeInTheDocument();
    expect(card("MSA").getByText("Client copy for this client · version 2")).toBeInTheDocument();
    expect(card("MSA").getByText("Updated payment terms")).toBeInTheDocument();
    expect(card("MSA").getByRole("button", { name: "Upload new version" })).toBeInTheDocument();
    expect(card("MSA").getByText("History (2)")).toBeInTheDocument();
    expect(
      card("MSA").getByText("Oct 15, 2026 · Legal user · Replaced with a client copy: Updated payment terms"),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog").textContent).not.toMatch(UUID_TEXT);
  });

  it("a mark from HubSpot: who, when, why, the source, the value as its note, and Remove mark", async () => {
    vi.mocked(agreementsApi.getClientAgreements).mockResolvedValue(
      panel({
        relationship: "existing",
        needs_attention: false,
        nda: STANDARD_NDA,
        msa: doc("MSA", "covered", {
          mark: {
            reason: "per_hubspot",
            marked_on: "2026-10-14",
            marked_by: "Srikanth Parimi",
            source: "hubspot",
            hubspot_value: "Signed MSA",
          },
          hubspot_hint: "Signed MSA",
        }),
      }),
    );
    renderPanel();
    await screen.findByRole("article", { name: "MSA" });
    expect(card("MSA").getByText("✓ Marked covered")).toBeInTheDocument();
    expect(card("MSA").getByText("Srikanth Parimi · Oct 14, 2026")).toBeInTheDocument();
    expect(card("MSA").getByText("Per HubSpot")).toBeInTheDocument();
    expect(card("MSA").getByText("HubSpot msa_type")).toBeInTheDocument();
    expect(card("MSA").getByText("msa_type “Signed MSA”")).toBeInTheDocument();
    expect(card("MSA").getByText("hint only")).toBeInTheDocument();
    expect(card("MSA").getByRole("button", { name: "Remove mark" })).toBeInTheDocument();
    expect(card("MSA").queryByRole("button", { name: "Mark covered" })).toBeNull();
  });

  it("a HubSpot hint on an empty MSA says when it is mapped to Covered", async () => {
    vi.mocked(agreementsApi.getClientAgreements).mockResolvedValue(
      panel({ msa: doc("MSA", "missing", { hubspot_hint: "Signed MSA" }) }),
    );
    vi.mocked(agreementsApi.getHubspotValues).mockResolvedValue({
      stored: true,
      items: [{ value: "Signed MSA", clients: 28, action: "covered" }],
    });
    renderPanel();
    await screen.findByRole("article", { name: "MSA" });
    expect(await card("MSA").findByText(/mapped as Covered, applies when you run the mapping/)).toBeInTheDocument();
    expect(card("MSA").getByText(/“Signed MSA”/)).toBeInTheDocument();
  });

  it("names possible duplicates, test data and the Unknown company placeholder", async () => {
    vi.mocked(agreementsApi.getClientAgreements).mockResolvedValue(
      panel({
        possible_duplicates: ["Jasper Energy", "Jasper Energy Inc."],
        flags: ["possible_duplicate", "test_data", "unknown_company"],
      }),
    );
    renderPanel();
    expect(await screen.findByText("Jasper Energy, Jasper Energy Inc.")).toBeInTheDocument();
    expect(screen.getByText("Possible duplicate of")).toBeInTheDocument();
    expect(screen.getByText("Test data. Never attached in a backfill.")).toBeInTheDocument();
    expect(screen.getByText("HubSpot sent a deal with no company. Give it a real client first.")).toBeInTheDocument();
  });

  it("renders a hostile client name as text", async () => {
    vi.mocked(agreementsApi.getClientAgreements).mockResolvedValue(panel({ name: "<img src=x onerror=alert(1)>" }));
    renderPanel();
    expect(await screen.findByRole("heading", { name: "<img src=x onerror=alert(1)>" })).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });

  it("names a failed load and retries", async () => {
    vi.mocked(agreementsApi.getClientAgreements)
      .mockRejectedValueOnce(new ApiError(404, { detail: "client not found" }, "client not found"))
      .mockResolvedValueOnce(panel());
    renderPanel();
    expect(await screen.findByRole("alert")).toHaveTextContent("client not found");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("article", { name: "NDA" })).toBeInTheDocument();
  });
});

describe("who can write", () => {
  it("Sales sees every write control locked with the reason and can still download", async () => {
    vi.mocked(agreementsApi.getClientAgreements).mockResolvedValue(
      panel({ can_write: false, nda: STANDARD_NDA, msa: doc("MSA", "missing") }),
    );
    vi.mocked(agreementsApi.getStandardDocuments).mockResolvedValue({ NDA: standardVersion("NDA"), MSA: standardVersion("MSA") });
    const mark = vi.spyOn(agreementsApi, "markCovered");
    const link = vi.spyOn(agreementsApi, "getClientDownloadLink").mockResolvedValue({
      url: "https://files.example/nda",
      expires_in_seconds: 300,
      file_name: "SmarTek21_Standard_NDA.pdf",
    });
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const props = renderPanel();
    await screen.findByRole("article", { name: "MSA" });
    const locked = [
      screen.getByRole("button", { name: /^Change relationship/ }),
      card("NDA").getByRole("button", { name: /^Replace with client copy/ }),
      card("NDA").getByRole("button", { name: /^Remove from client/ }),
      card("MSA").getByRole("button", { name: /^Upload client copy/ }),
      card("MSA").getByRole("button", { name: /^Attach standard copy/ }),
      card("MSA").getByRole("button", { name: /^Mark covered/ }),
    ];
    for (const button of locked) {
      expect(button).toHaveAttribute("aria-disabled", "true");
      expect(button).not.toBeDisabled();
    }
    fireEvent.click(card("MSA").getByRole("button", { name: /^Mark covered/ }));
    expect(await screen.findByText(WRITER_LOCK)).toBeInTheDocument();
    expect(mark).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Cobalt Pharma" })).toBeInTheDocument();

    expect(props.onChanged).not.toHaveBeenCalled();
    fireEvent.click(card("NDA").getByRole("button", { name: "Download" }));
    await waitFor(() => expect(open).toHaveBeenCalledWith("https://files.example/nda", "_blank", "noopener,noreferrer"));
    expect(link).toHaveBeenCalledWith(CLIENT_ID, "NDA");
    // The download is an Activity event: the page refreshes its count (review finding).
    expect(props.onChanged).toHaveBeenCalledTimes(1);
    expect(
      (await screen.findAllByText(
        "A download link for Cobalt Pharma's NDA was created. It expires in 5 minutes and the download is recorded.",
      )).length,
    ).toBeGreaterThan(0);
  });
});

describe("review fixes", () => {
  it("shows the server's reason when no business unit is recorded", async () => {
    vi.mocked(agreementsApi.getClientAgreements).mockResolvedValue(
      panel({ business_units: [], business_unit_note: "Region not mapped to a business unit: Mars" }),
    );
    renderPanel();
    expect(await screen.findByText("Region not mapped to a business unit: Mars")).toBeInTheDocument();
    expect(screen.queryByText("No business unit recorded")).toBeNull();
  });

  it("saves a provisional relationship by hand even when the word is the same; a manual one is a no-op", async () => {
    const set = vi.spyOn(agreementsApi, "setRelationship").mockResolvedValue(
      panel({ relationship_basis: "manual", basis_text: "Marked net new by Legal user", provisional: true }),
    );
    vi.mocked(agreementsApi.getClientAgreements).mockResolvedValue(panel({ provisional: true }));
    renderPanel();
    await screen.findByRole("article", { name: "NDA" });
    fireEvent.click(screen.getByRole("button", { name: "Change relationship" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(set).toHaveBeenCalledWith(CLIENT_ID, { relationship: "net_new" }));
    expect(await screen.findByText("Marked net new by Legal user")).toBeInTheDocument();

    // Now stored by hand: saving the same word again sends nothing and returns to the client.
    fireEvent.click(screen.getByRole("button", { name: "Change relationship" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Change relationship" })).toBeNull());
    expect(set).toHaveBeenCalledTimes(1);
  });
});

describe("writes", () => {
  it("mark covered: refuses a future date in the browser, then saves, reloads and moves focus to the card", async () => {
    const today = pacificToday();
    const next = new Date(`${today}T12:00:00Z`);
    next.setUTCDate(next.getUTCDate() + 1);
    const tomorrow = next.toISOString().slice(0, 10);
    const mark = vi.spyOn(agreementsApi, "markCovered").mockResolvedValue(doc("NDA", "covered"));
    const props = renderPanel();
    await screen.findByRole("article", { name: "NDA" });
    vi.mocked(agreementsApi.getClientAgreements).mockResolvedValue(
      panel({
        nda: doc("NDA", "covered", {
          mark: { reason: "confirmed_with_client", marked_on: today, marked_by: "Legal user", source: "dealgate", note: "Per email" },
        }),
      }),
    );
    fireEvent.click(card("NDA").getByRole("button", { name: "Mark covered" }));

    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByRole("heading", { name: "Mark NDA covered" })).toBeInTheDocument();
    expect(dialog.getByText("Cobalt Pharma", { selector: "p" })).toBeInTheDocument();
    expect(
      dialog.getByText(
        "Use this when the NDA is in place but there is no file to attach here. The warning for this client clears. Records who marked it and why.",
      ),
    ).toBeInTheDocument();
    const reason = dialog.getByLabelText("Reason");
    expect(Array.from((reason as HTMLSelectElement).options).map((o) => o.text)).toEqual([
      "Signed outside DealGate",
      "Covered by earlier work",
      "Confirmed with the client",
      "Other",
    ]);
    const date = dialog.getByLabelText("Date it was signed or confirmed");
    expect(date).toHaveValue(today);
    expect(date).toHaveAttribute("max", today);
    fireEvent.change(date, { target: { value: tomorrow } });
    fireEvent.click(dialog.getByRole("button", { name: "Mark covered" }));
    expect(await dialog.findByRole("alert")).toHaveTextContent("The date cannot be in the future.");
    expect(mark).not.toHaveBeenCalled();

    fireEvent.change(date, { target: { value: today } });
    fireEvent.change(reason, { target: { value: "confirmed_with_client" } });
    fireEvent.change(dialog.getByLabelText("Note (optional)"), { target: { value: "Per email" } });
    fireEvent.click(dialog.getByRole("button", { name: "Mark covered" }));
    await waitFor(() =>
      expect(mark).toHaveBeenCalledWith(CLIENT_ID, "NDA", {
        reason: "confirmed_with_client",
        marked_on: today,
        note: "Per email",
      }),
    );
    expect(await card("NDA").findByText("✓ Marked covered")).toBeInTheDocument();
    expect(props.onChanged).toHaveBeenCalledTimes(1);
    expect(agreementsApi.getClientAgreements).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("heading", { name: "NDA" })));
    expect((await screen.findAllByText("NDA marked covered.")).length).toBeGreaterThan(0);
  });

  it("Cancel returns to the client with focus on the control that opened the form", async () => {
    renderPanel();
    await screen.findByRole("article", { name: "NDA" });
    fireEvent.click(card("NDA").getByRole("button", { name: "Upload client copy" }));
    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByRole("heading", { name: "Upload a document" })).toBeInTheDocument();
    expect(dialog.getByLabelText("What is this?")).toBeDisabled();
    expect(dialog.getByLabelText("Client")).toHaveValue("Cobalt Pharma");
    fireEvent.click(dialog.getByRole("button", { name: "Cancel" }));
    expect(await screen.findByRole("heading", { name: "Cobalt Pharma" })).toBeInTheDocument();
    await waitFor(() =>
      expect(document.activeElement).toBe(card("NDA").getByRole("button", { name: "Upload client copy" })),
    );
  });

  it("removing a standard attachment removes only the row; a client copy shows its cleanup without the job id", async () => {
    vi.mocked(agreementsApi.getClientAgreements).mockResolvedValue(
      panel({ relationship: "existing", needs_attention: false, nda: STANDARD_NDA, msa: CLIENT_MSA }),
    );
    const detach = vi
      .spyOn(agreementsApi, "detachAgreement")
      .mockResolvedValueOnce(doc("NDA", "existing_none"))
      .mockResolvedValueOnce({ job_id: "5b0c5d2e-8f8a-4b8e-9d55-2d1c4e2f7a10", status: "pending" });
    const props = renderPanel();
    await screen.findByRole("article", { name: "NDA" });

    fireEvent.click(card("NDA").getByRole("button", { name: "Remove from client" }));
    let dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByRole("heading", { name: "Remove NDA from this client" })).toBeInTheDocument();
    expect(
      dialog.getByText(
        "The standard copy is detached from Cobalt Pharma. The shared standard file stays for every other client, and you can attach it again later.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(dialog.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(detach).toHaveBeenCalledWith(CLIENT_ID, "NDA"));
    expect(await screen.findByText("NDA removed.", { selector: "p:not([role])" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "View cleanup status" })).toBeNull();

    fireEvent.click(card("MSA").getByRole("button", { name: "Remove from client" }));
    dialog = within(screen.getByRole("dialog"));
    expect(
      dialog.getByText(
        "The client copy is removed from Cobalt Pharma with all its versions. The stored files are queued for cleanup. This cannot be undone.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(dialog.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(detach).toHaveBeenCalledWith(CLIENT_ID, "MSA"));
    const cleanup = await screen.findByRole("link", { name: "View cleanup status" });
    expect(cleanup).toHaveAttribute("href", "/deletions/5b0c5d2e-8f8a-4b8e-9d55-2d1c4e2f7a10");
    expect(screen.getByText(/MSA removed\. Its stored files are queued for cleanup\./)).toBeInTheDocument();
    expect(screen.getByRole("dialog").textContent).not.toMatch(UUID_TEXT);
    expect(props.onChanged).toHaveBeenCalledTimes(2);
  });

  it("removes a mark", async () => {
    vi.mocked(agreementsApi.getClientAgreements).mockResolvedValue(
      panel({
        msa: doc("MSA", "covered", {
          mark: { reason: "signed_outside_dealgate", marked_on: "2026-10-15", marked_by: "Srikanth Parimi", source: "dealgate" },
        }),
      }),
    );
    const remove = vi.spyOn(agreementsApi, "removeMark").mockResolvedValue(doc("MSA", "missing"));
    renderPanel();
    await screen.findByRole("article", { name: "MSA" });
    fireEvent.click(card("MSA").getByRole("button", { name: "Remove mark" }));
    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByRole("heading", { name: "Remove MSA mark" })).toBeInTheDocument();
    expect(dialog.getByText("The client goes back to its normal status.")).toBeInTheDocument();
    fireEvent.click(dialog.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(remove).toHaveBeenCalledWith(CLIENT_ID, "MSA"));
  });

  it("changes the relationship by hand and shows the server's answer without a second request", async () => {
    const set = vi.spyOn(agreementsApi, "setRelationship").mockResolvedValue(
      panel({
        relationship: "existing",
        relationship_basis: "manual",
        basis_text: "Marked existing by Legal user",
        needs_attention: false,
        nda: doc("NDA", "existing_none"),
        msa: doc("MSA", "existing_none"),
      }),
    );
    const props = renderPanel();
    await screen.findByRole("article", { name: "NDA" });
    fireEvent.click(screen.getByRole("button", { name: "Change relationship" }));
    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByRole("heading", { name: "Change relationship" })).toBeInTheDocument();
    expect(
      dialog.getByText(
        "Existing clients are covered by the standard copies. Net-new clients need their own copy. Use this to correct a client, for example a duplicate or a test record.",
      ),
    ).toBeInTheDocument();
    const select = dialog.getByLabelText("Relationship");
    expect(Array.from((select as HTMLSelectElement).options).map((o) => o.text)).toEqual([
      "Existing: worked with before",
      "Net new",
    ]);
    fireEvent.change(select, { target: { value: "existing" } });
    fireEvent.click(dialog.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(set).toHaveBeenCalledWith(CLIENT_ID, { relationship: "existing" }));
    expect(await screen.findByText("Marked existing by Legal user")).toBeInTheDocument();
    expect(screen.getByText("Existing")).toBeInTheDocument();
    expect(card("NDA").getByText("Existing client. No standard copy attached yet.")).toBeInTheDocument();
    expect(props.onChanged).toHaveBeenCalledTimes(1);
    expect(agreementsApi.getClientAgreements).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole("button", { name: "Change relationship" })),
    );
  });

  it("attaches the standard copy to a client holding nothing, only where a standard exists", async () => {
    vi.mocked(agreementsApi.getClientAgreements).mockResolvedValue(
      panel({
        relationship: "existing",
        needs_attention: false,
        nda: doc("NDA", "existing_none"),
        msa: doc("MSA", "existing_none"),
      }),
    );
    vi.mocked(agreementsApi.getStandardDocuments).mockResolvedValue({ NDA: standardVersion("NDA"), MSA: null });
    const attach = vi.spyOn(agreementsApi, "attachStandardToClient").mockResolvedValue(STANDARD_NDA);
    const props = renderPanel();
    await screen.findByRole("article", { name: "NDA" });
    expect(card("MSA").queryByRole("button", { name: "Attach standard copy" })).toBeNull();
    vi.mocked(agreementsApi.getClientAgreements).mockResolvedValue(
      panel({ relationship: "existing", needs_attention: false, nda: STANDARD_NDA, msa: doc("MSA", "existing_none") }),
    );
    fireEvent.click(card("NDA").getByRole("button", { name: "Attach standard copy" }));
    await waitFor(() => expect(attach).toHaveBeenCalledWith(CLIENT_ID, "NDA"));
    expect(await card("NDA").findByText("✓ Standard copy")).toBeInTheDocument();
    expect((await screen.findAllByText("Standard NDA attached.")).length).toBeGreaterThan(0);
    expect(props.onChanged).toHaveBeenCalledTimes(1);
  });
});

describe("requests", () => {
  it("takes the standard copy's availability from the cards when the server sends it: one request", async () => {
    vi.mocked(agreementsApi.getClientAgreements).mockResolvedValue(
      panel({
        relationship: "existing",
        needs_attention: false,
        nda: { ...doc("NDA", "existing_none"), standard_available_version: 2 } as DocCard,
        msa: { ...doc("MSA", "existing_none"), standard_available_version: null } as DocCard,
      }),
    );
    renderPanel();
    await screen.findByRole("article", { name: "NDA" });
    expect(card("NDA").getByRole("button", { name: "Attach standard copy" })).toBeInTheDocument();
    expect(card("MSA").queryByRole("button", { name: "Attach standard copy" })).toBeNull();
    expect(agreementsApi.getStandardDocuments).not.toHaveBeenCalled();
    expect(agreementsApi.getClientAgreements).toHaveBeenCalledTimes(1);
  });
});

describe("dialog behaviour", () => {
  function Harness() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button type="button" onClick={() => setOpen(true)}>
          Open client
        </button>
        <ClientAgreementsPanel clientId={CLIENT_ID} variant="drawer" open={open} onOpenChange={setOpen} />
      </>
    );
  }

  it("Escape closes the drawer and focus returns to what opened it", async () => {
    render(
      <Providers>
        <Harness />
      </Providers>,
    );
    const opener = screen.getByRole("button", { name: "Open client" });
    opener.focus();
    fireEvent.click(opener);
    const dialog = await screen.findByRole("dialog");
    await screen.findByRole("article", { name: "NDA" });
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(opener));
  });

  it("in the Pipeline section the cards are inline and a form opens in a drawer over them", async () => {
    render(
      <Providers>
        <ClientAgreementsPanel clientId={CLIENT_ID} variant="section" />
      </Providers>,
    );
    expect(await screen.findByRole("heading", { name: "Agreement documents" })).toBeInTheDocument();
    await screen.findByRole("article", { name: "NDA" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByRole("link", { name: "Open deals in Pipeline" })).toBeNull();
    const opener = card("NDA").getByRole("button", { name: "Mark covered" });
    opener.focus();
    fireEvent.click(opener);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "Mark NDA covered" })).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(opener));
  });

  it("does not show one client's answer under another", async () => {
    let resolveFirst!: (value: ClientAgreements) => void;
    vi.mocked(agreementsApi.getClientAgreements).mockImplementation((id) =>
      id === CLIENT_ID
        ? new Promise((resolve) => {
            resolveFirst = resolve;
          })
        : Promise.resolve(panel({ client_id: id, name: "Other Client" })),
    );
    const view = render(
      <Providers>
        <ClientAgreementsPanel clientId={CLIENT_ID} variant="section" />
      </Providers>,
    );
    view.rerender(
      <Providers>
        <ClientAgreementsPanel clientId="c0000000-0000-4000-8000-0000000000b2" variant="section" />
      </Providers>,
    );
    await screen.findByRole("article", { name: "NDA" });
    await act(async () => resolveFirst(panel({ name: "Stale Client", nda: STANDARD_NDA })));
    expect(card("NDA").getByText("Missing")).toBeInTheDocument();
  });
});
