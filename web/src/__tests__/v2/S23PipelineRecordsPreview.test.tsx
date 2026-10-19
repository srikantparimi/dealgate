// S23-PL2 F11 · deal and client previews (spec §6): every field, the callouts,
// the next-action editor on the EXISTING endpoint (POST /next-actions, PATCH
// /next-actions/{id}), the watch toggle, real destinations, and text nodes.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as agreementsApi from "../../api/agreements";
import type { ClientAgreements } from "../../api/agreements";
import * as api from "../../api/client";
import * as wsApi from "../../api/pipelineWorkspace";
import { DEFAULT_WORKSPACE_QUERY, type DealRow, type WorkspaceQuery } from "../../api/pipelineWorkspace";
import { ClientPreview, type ClientPreviewProps } from "../../pages/v2/pipeline/ClientPreview";
import { DealPreview, type DealPreviewProps } from "../../pages/v2/pipeline/DealPreview";
import { Toaster } from "../../ui-v2/primitives/toaster";
import { TooltipProvider } from "../../ui-v2/primitives/tooltip";
import {
  INJECTION_CLIENT,
  INJECTION_TITLE,
  TODAY,
  deal,
  overdueDeal,
  reviewDeal,
  urlState,
  wonDeal,
  workspace,
} from "./S23PipelineRecordsFixtures";

beforeEach(() => {
  vi.restoreAllMocks();
});
afterEach(() => {
  vi.restoreAllMocks();
});

function nextActionRow(overrides: Partial<api.NextActionRow> = {}): api.NextActionRow {
  return {
    id: "na-1",
    opportunity_id: "deal-1",
    title: "Call the sponsor",
    description: "Call the sponsor",
    assignee_user_id: "me-id",
    owner_user_id: "me-id",
    due_date: "2026-10-20",
    status: "open",
    blocker: null,
    outcome: null,
    approval_package_id: null,
    revision: "r1",
    can_edit: true,
    ...overrides,
  };
}

function renderDeal(d: DealRow | null, overrides: Partial<DealPreviewProps> = {}) {
  const props: DealPreviewProps = {
    deal: d,
    open: true,
    onOpenChange: vi.fn(),
    today: TODAY,
    hubspotPortalId: "48656168",
    assigneeId: "me-id",
    onOpenClient: vi.fn(),
    onToggleWatch: vi.fn().mockResolvedValue(undefined),
    onChanged: vi.fn(),
    ...overrides,
  };
  render(
    <MemoryRouter>
      <DealPreview {...props} />
    </MemoryRouter>,
  );
  return props;
}

/** The value shown under a label in a preview's detail grid. */
function valueOf(label: string): string | null | undefined {
  return screen.getByText(label, { selector: "dt" }).nextElementSibling?.textContent;
}

describe("deal preview (spec §6.1)", () => {
  it("shows tonight's deal: kicker, title, client, business unit, stage, pipeline and the eight facts", () => {
    // S24-AG1 F6: the row carries the client's NDA / MSA states from the shared agreement service.
    const d = deal({ agreements: { nda_on_file: false, msa_on_file: false, nda_state: "missing", msa_state: "missing" } });
    const props = renderDeal(d);
    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByText("Opportunity · quick preview")).toBeInTheDocument();
    expect(dialog.getByRole("heading", { name: "Cloud modernization" })).toBeInTheDocument();
    expect(dialog.getByText("6 · Contracting")).toBeInTheDocument();
    expect(dialog.getByText("Global sales pipeline")).toBeInTheDocument();
    expect(dialog.getByText("IT Avalon")).toBeInTheDocument();
    expect(valueOf("Deal value · USD")).toBe("$542,000");
    expect(valueOf("Expected close")).toBe("Dec 28");
    expect(valueOf("HubSpot deal owner")).toBe("Srikanth Parimi");
    expect(valueOf("Account owner")).toBe("Not assigned");
    expect(valueOf("Created")).toBe("Sep 12");
    expect(valueOf("Last activity")).toBe("None recorded");
    expect(valueOf("HubSpot region")).toBe("US - IT Avalon");
    expect(valueOf("Business unit")).toBe("IT Avalon · US");
    expect(dialog.getByText("No next action set for this deal.")).toBeInTheDocument();
    expect(dialog.getByRole("textbox", { name: "Next action" })).toHaveAttribute("placeholder", "What happens next?");
    expect(dialog.getByRole("textbox", { name: "Next action" })).toHaveAttribute("maxlength", "140");
    expect(dialog.getByLabelText("Due date")).toHaveAttribute("type", "date");
    expect(dialog.getByRole("button", { name: "Save next action" })).toBeEnabled();
    // S24-AG1 F6: each kind's name followed by its shared state tag (AgreementTags in tags.tsx).
    expect(dialog.getAllByText("Missing")).toHaveLength(2);
    expect(dialog.getByText("NDA", { selector: "span" })).toBeInTheDocument();
    expect(dialog.getByText("MSA", { selector: "span" })).toBeInTheDocument();
    expect(dialog.getByText("No SOW").className).toContain("bg-primary-subtle");
    expect(
      dialog.getByText(
        "NDA and MSA show the client's state: Client copy, Standard copy, Marked covered, Missing or Due at stage 2. A warning only; nothing is blocked. The SOW state is separate from the HubSpot sales stage.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(dialog.getByRole("button", { name: "Vector Systems" }));
    expect(props.onOpenClient).toHaveBeenCalledWith({ id: d.client.id, name: "Vector Systems" });
  });

  it("links Upload SOW, the watch toggle and HubSpot to real destinations", () => {
    const d = deal();
    renderDeal(d);
    const upload = screen.getByRole("link", { name: "Upload SOW" });
    expect(upload).toHaveTextContent("Upload SOW →");
    expect(upload).toHaveAttribute(
      "href",
      `/sows/new?bindOppId=${encodeURIComponent(d.id)}&bindClientId=${encodeURIComponent(d.client.id!)}`,
    );
    const hubspot = screen.getByRole("link", { name: "HubSpot" });
    expect(hubspot).toHaveTextContent("HubSpot ↗");
    expect(hubspot).toHaveAttribute("href", "https://app.hubspot.com/contacts/48656168/record/0-3/9001");
    expect(hubspot).toHaveAttribute("target", "_blank");
    expect(hubspot.getAttribute("rel")).toContain("noopener");
    expect(screen.getByRole("button", { name: "Watch deal" })).toHaveAttribute("aria-pressed", "false");
  });

  it("opens the SOW workspace when the deal has a SOW, and hides HubSpot without a portal id", () => {
    const d = reviewDeal({ sow_count: 2 });
    renderDeal(d, { hubspotPortalId: null });
    expect(screen.getByRole("link", { name: "Open SOW workspace" })).toHaveAttribute(
      "href",
      `/sows/${encodeURIComponent(d.id)}`,
    );
    expect(screen.queryByRole("link", { name: "Upload SOW" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "HubSpot" })).not.toBeInTheDocument();
    expect(screen.getByText("In review · delivery/hr")).toBeInTheDocument();
    expect(screen.getByText("+1 more")).toBeInTheDocument();
    expect(valueOf("Last activity")).toBe("Oct 3");
    expect(valueOf("Account owner")).toBe("Janice Krpan");
  });

  it("warns about a missing owner and a passed close date on an open deal (both together)", () => {
    renderDeal(
      deal({ deal_owner: { name: null, state: "none" }, close_date: "2026-10-09", flags: ["no_owner", "close_passed"] }),
    );
    expect(valueOf("HubSpot deal owner")).toBe("Not assigned");
    expect(
      screen.getByText("The deal needs an owner in HubSpot. Its client account owner is a separate field."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("The expected close date has passed. Update it in HubSpot or move the deal."),
    ).toBeInTheDocument();
  });

  it("shows a closed deal without callouts or editor, and a former owner", () => {
    renderDeal(wonDeal({ close_date: "2026-10-02", flags: [] }));
    expect(screen.getByText("Deal is closed.")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Next action" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save next action" })).not.toBeInTheDocument();
    expect(valueOf("HubSpot deal owner")).toBe("Former HubSpot user");
    expect(screen.queryByText(/expected close date has passed/)).not.toBeInTheDocument();
    expect(screen.getByText("Closed won")).toBeInTheDocument();
  });

  it("shows the current next action and its overdue due date", () => {
    // The editor's read of the action never answers here: this test is about the summary.
    vi.spyOn(api, "listNextActions").mockReturnValue(new Promise(() => undefined));
    renderDeal(overdueDeal());
    expect(screen.getByText("Confirm final commercial terms", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("Due Oct 13 · overdue")).toBeInTheDocument();
    expect(valueOf("Expected close")).toBe("Mar 15, 2027");
  });

  it("shows an unmapped region in the business unit line and fact", () => {
    renderDeal(deal({ business_unit: null, region: null, bu_unmapped: true, hubspot_region: "US - Other" }));
    expect(screen.getByText("Unmapped region · US - Other")).toBeInTheDocument();
    expect(valueOf("Business unit")).toBe("Unmapped · US - Other");
    expect(valueOf("HubSpot region")).toBe("US - Other");
  });

  it("toggles watching and passes the state the user saw", async () => {
    const d = deal();
    const props = renderDeal(d);
    fireEvent.click(screen.getByRole("button", { name: "Watch deal" }));
    expect(props.onToggleWatch).toHaveBeenCalledWith({ ...d, watching: false });
    const on = await screen.findByRole("button", { name: "Watching" });
    expect(on).toHaveAttribute("aria-pressed", "true");
    expect(on).toHaveTextContent("★ Watching");
    fireEvent.click(on);
    expect(props.onToggleWatch).toHaveBeenLastCalledWith({ ...d, watching: true });
    expect(await screen.findByRole("button", { name: "Watch deal" })).toHaveAttribute("aria-pressed", "false");
  });

  it("follows the fresh row the page gets after a watch, so a failed watch does not stay starred", async () => {
    const d = deal();
    const base: DealPreviewProps = {
      deal: d,
      open: true,
      onOpenChange: vi.fn(),
      today: TODAY,
      hubspotPortalId: null,
      assigneeId: "me-id",
      onOpenClient: vi.fn(),
      onToggleWatch: vi.fn().mockResolvedValue(undefined),
      onChanged: vi.fn(),
    };
    const { rerender } = render(
      <MemoryRouter>
        <DealPreview {...base} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Watch deal" }));
    expect(await screen.findByRole("button", { name: "Watching" })).toHaveAttribute("aria-pressed", "true");
    // The page asked again and the API still says "not watching" (the watch failed).
    rerender(
      <MemoryRouter>
        <DealPreview {...base} deal={{ ...d }} />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("button", { name: "Watch deal" })).toHaveAttribute("aria-pressed", "false");
  });

  it("shows a deal with no currency without '$' or 'USD', and says it has none", () => {
    // HubSpot sent no deal_currency_code: the API sends currency null and leaves the amount out of every USD total.
    renderDeal(deal({ amount: "542000", currency: null }));
    expect(screen.queryByText(/^Deal value · /, { selector: "dt" })).not.toBeInTheDocument();
    expect(valueOf("Deal value")).toBe("542,000 · no currency");
    expect(screen.getByRole("dialog")).not.toHaveTextContent("$542,000");
  });

  it("names a non-USD currency in the label and the value", () => {
    renderDeal(deal({ amount: "120000", currency: "EUR" }));
    expect(valueOf("Deal value · EUR")).toBe("EUR 120,000");
  });

  it("renders HubSpot strings with HTML or formulas literally (F15)", () => {
    renderDeal(deal({ title: INJECTION_TITLE, client: { id: "c-x", name: INJECTION_CLIENT } }));
    expect(screen.getByRole("heading", { name: INJECTION_TITLE })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: INJECTION_CLIENT })).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });
});

describe("next-action editor (F11, existing /next-actions endpoint)", () => {
  it("creates a next action for the signed-in user, refreshes the page and shows the saved action", async () => {
    const d = deal({ id: "deal-1" });
    const list = vi.spyOn(api, "listNextActions");
    const create = vi.spyOn(api, "createNextAction").mockResolvedValue(nextActionRow());
    const patch = vi.spyOn(api, "patchNextAction").mockResolvedValue(
      nextActionRow({ title: "Call the CFO", revision: "r2" }),
    );
    const props = renderDeal(d);
    fireEvent.change(screen.getByRole("textbox", { name: "Next action" }), { target: { value: "  Call the sponsor " } });
    fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-10-20" } });
    fireEvent.click(screen.getByRole("button", { name: "Save next action" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Next action saved."));
    expect(create).toHaveBeenCalledWith({
      opportunity_id: "deal-1",
      title: "Call the sponsor",
      assignee_user_id: "me-id",
      due_date: "2026-10-20",
    });
    expect(list).not.toHaveBeenCalled();
    expect(props.onChanged).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Call the sponsor", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("Due Oct 20")).toBeInTheDocument();
    expect(screen.queryByText("No next action set for this deal.")).not.toBeInTheDocument();

    // A second save edits the action it just created, with the revision the API returned.
    fireEvent.change(screen.getByRole("textbox", { name: "Next action" }), { target: { value: "Call the CFO" } });
    fireEvent.click(screen.getByRole("button", { name: "Save next action" }));
    await waitFor(() => expect(patch).toHaveBeenCalledTimes(1));
    expect(patch).toHaveBeenCalledWith("na-1", { title: "Call the CFO", due_date: "2026-10-20", expected_revision: "r1" });
    await waitFor(() => expect(props.onChanged).toHaveBeenCalledTimes(2));
    expect(create).toHaveBeenCalledTimes(1);
  });

  it("asks for text before saving and calls nothing", () => {
    const create = vi.spyOn(api, "createNextAction");
    renderDeal(deal());
    fireEvent.click(screen.getByRole("button", { name: "Save next action" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter what happens next.");
    expect(create).not.toHaveBeenCalled();
  });

  it("edits the deal's open next action with its current revision, and clears the due date", async () => {
    const d = overdueDeal({ id: "deal-2" });
    const list = vi.spyOn(api, "listNextActions").mockResolvedValue({
      items: [
        nextActionRow({ id: "other", revision: "x" }),
        nextActionRow({ id: d.next_action!.id, title: "Confirm final commercial terms", due_date: "2026-10-13", revision: "rev-1" }),
      ],
    });
    const patch = vi.spyOn(api, "patchNextAction").mockResolvedValue(
      nextActionRow({ id: d.next_action!.id, title: "Confirm final commercial terms", due_date: null, revision: "rev-2" }),
    );
    const props = renderDeal(d);
    const text = screen.getByRole("textbox", { name: "Next action" });
    expect(text).toHaveValue("Confirm final commercial terms");
    expect(screen.getByLabelText("Due date")).toHaveValue("2026-10-13");
    await waitFor(() => expect(list).toHaveBeenCalledWith({ opportunity_id: "deal-2" }));
    fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save next action" }));
    await waitFor(() => expect(patch).toHaveBeenCalled());
    expect(patch).toHaveBeenCalledWith(d.next_action!.id, {
      title: "Confirm final commercial terms",
      clear_due_date: true,
      expected_revision: "rev-1",
    });
    await waitFor(() => expect(props.onChanged).toHaveBeenCalledTimes(1));
    expect(screen.getByText("No due date.")).toBeInTheDocument();
  });

  it("explains who may change a next action the user cannot edit, instead of a form that would fail", async () => {
    const d = overdueDeal();
    vi.spyOn(api, "listNextActions").mockResolvedValue({
      items: [nextActionRow({ id: d.next_action!.id, can_edit: false })],
    });
    renderDeal(d);
    expect(
      await screen.findByText("Only the person assigned to this next action, its creator or a sales leader can change it."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Next action" })).not.toBeInTheDocument();
  });

  it("shows the API's reason when a save fails", async () => {
    vi.spyOn(api, "createNextAction").mockRejectedValue(
      new api.ApiError(403, { detail: "Assignee is outside this deal's authorized registered users" }, "Assignee is outside this deal's authorized registered users"),
    );
    const props = renderDeal(deal());
    fireEvent.change(screen.getByRole("textbox", { name: "Next action" }), { target: { value: "Call" } });
    fireEvent.click(screen.getByRole("button", { name: "Save next action" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Assignee is outside this deal's authorized registered users");
    expect(props.onChanged).not.toHaveBeenCalled();
  });

  it("waits for the signed-in user before it can create a next action", () => {
    renderDeal(deal(), { assigneeId: null });
    expect(screen.getByRole("button", { name: "Save next action" })).toBeDisabled();
  });
});

describe("client preview (spec §6.2)", () => {
  const CLIENT = { id: "c0000000-0000-4000-8000-000000000001", name: "Vector Systems" };
  const observability = deal({
    title: "Observability service",
    stage_id: 2,
    stage_label: "Qualification",
    amount: "67000",
    deal_owner: { name: "Michael Holman", state: "active" },
  });
  const cloud = deal();
  const lost = deal({
    title: "Cloud modernization (2025)",
    stage_id: 8,
    stage_label: "Closed lost",
    amount: "322000",
    deal_owner: { name: null, state: "archived" },
  });
  const unowned = deal({ title: "Unowned rollout", deal_owner: { name: null, state: "none" }, amount: null });

  // S24-AG1 F3: the agreement documents are the shared client panel (GET /clients/{id}/agreements).
  function agreements(overrides: Partial<ClientAgreements> = {}): ClientAgreements {
    return {
      client_id: CLIENT.id,
      name: "Vector Systems",
      relationship: "net_new",
      relationship_basis: "none",
      requirement: "required",
      needs_attention: true,
      possible_duplicates: [],
      deals: { open: 2, won: 0, lost: 1, furthest_open_stage: 6 },
      nda: { kind: "NDA", state: "missing", history: [] },
      msa: { kind: "MSA", state: "missing", history: [] },
      can_write: true,
      basis_text: "No earlier work found",
      ...overrides,
    };
  }

  beforeEach(() => {
    vi.spyOn(agreementsApi, "getClientAgreements").mockResolvedValue(agreements());
    vi.spyOn(agreementsApi, "getStandardDocuments").mockResolvedValue({ NDA: null, MSA: null });
    vi.spyOn(agreementsApi, "getHubspotValues").mockResolvedValue({ stored: false, items: [] });
  });

  function mockWorkspaces(allRows: DealRow[], matchingRows: DealRow[]) {
    return vi.spyOn(wsApi, "getWorkspace").mockImplementation(async (q: Partial<WorkspaceQuery>) => {
      const matching = (q.bu ?? []).length > 0;
      const rows = matching ? matchingRows : allRows;
      return workspace({
        rows,
        page: { number: 1, size: 100, total_rows: rows.length, total_value_usd: null },
        metrics: {
          ...workspace().metrics,
          open_deals: { value: 2, accounts: 1, drill: { tab: "deals", status: "open" } },
          open_value_usd: { value: "609000", includes_on_hold: 0, deals: 2, drill: { tab: "deals", status: "open" } },
        },
      });
    });
  }

  function renderClient(overrides: Partial<ClientPreviewProps> = {}) {
    const props: ClientPreviewProps = {
      client: CLIENT,
      open: true,
      onOpenChange: vi.fn(),
      state: urlState({ bu: ["IT Avalon"], sort: "close", page: 3, layout: "board" }),
      today: TODAY,
      onOpenDeal: vi.fn(),
      onShowClientDeals: vi.fn(),
      ...overrides,
    };
    render(
      <MemoryRouter>
        <TooltipProvider>
          <Toaster>
            <ClientPreview {...props} />
          </Toaster>
        </TooltipProvider>
      </MemoryRouter>,
    );
    return props;
  }

  it("asks for every linked deal and for the ones matching the current view, as the list", async () => {
    const get = mockWorkspaces([observability, cloud, lost], [observability, cloud]);
    const props = renderClient();
    await screen.findByText("All linked opportunities · 3");
    expect(get).toHaveBeenCalledWith(
      { ...DEFAULT_WORKSPACE_QUERY, client: CLIENT.id, status: "all", page_size: 100 },
      expect.anything(),
    );
    expect(get).toHaveBeenCalledWith(
      { ...props.state.query, client: CLIENT.id, tab: "deals", layout: "list", page: 1, page_size: 100 },
      expect.anything(),
    );
  });

  it("shows the owner, the deal facts, the shared agreements panel and every linked deal with its match tag", async () => {
    mockWorkspaces([observability, cloud, lost, unowned], [observability, cloud]);
    const props = renderClient();
    expect(await screen.findByText("All linked opportunities · 4")).toBeInTheDocument();
    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByText("Client · relationship overview")).toBeInTheDocument();
    expect(dialog.getByRole("heading", { name: "Vector Systems" })).toBeInTheDocument();
    expect(dialog.getByText("Account owner: Not assigned")).toBeInTheDocument();
    expect(valueOf("All open deal value")).toBe("$609,000");
    expect(valueOf("Deals matching current filters")).toBe("2");
    expect(valueOf("Total open deals")).toBe("2");
    expect(dialog.queryByText("Agreement files")).toBeNull();
    expect(dialog.getByRole("heading", { name: "Agreement documents" })).toBeInTheDocument();
    expect(
      await dialog.findByText(
        "This client is net new and past stage 1 with NDA and MSA missing. This is a warning only. Nothing is blocked.",
      ),
    ).toBeInTheDocument();
    expect(valueOf("Relationship")).toBe("Net newNo earlier work found");
    expect(within(dialog.getByRole("article", { name: "NDA" })).getByText("Missing")).toBeInTheDocument();
    expect(within(dialog.getByRole("article", { name: "MSA" })).getByText("Missing")).toBeInTheDocument();
    expect(agreementsApi.getClientAgreements).toHaveBeenCalledWith(CLIENT.id, expect.anything());

    expect(dialog.getByRole("button", { name: "Observability service" })).toHaveTextContent("Observability service →");
    expect(dialog.getByText("2 · Qualification · $67k · Michael Holman")).toBeInTheDocument();
    expect(dialog.getByText("6 · Contracting / Drive Commitment · $542k · Srikanth Parimi")).toBeInTheDocument();
    expect(dialog.getByText("8 · Closed Lost · $322k · Former HubSpot user")).toBeInTheDocument();
    expect(dialog.getByText("6 · Contracting / Drive Commitment · Not entered · Deal owner not assigned")).toBeInTheDocument();
    expect(dialog.getAllByText("Matches current view")).toHaveLength(2);
    expect(dialog.getAllByText("Outside current filters")).toHaveLength(2);

    fireEvent.click(dialog.getByRole("button", { name: "Observability service" }));
    expect(props.onOpenDeal).toHaveBeenCalledWith(observability);
    fireEvent.click(dialog.getByRole("button", { name: "Show this client’s deals" }));
    expect(props.onShowClientDeals).toHaveBeenCalledWith("Vector Systems");
    expect(dialog.getByRole("link", { name: "Agreement documents" })).toHaveAttribute(
      "href",
      `/agreements?client_id=${encodeURIComponent(CLIENT.id)}`,
    );
  });

  it("shows the client's NDA and MSA as the Agreements page does, and an attach refreshes the Pipeline", async () => {
    const owned = deal({ account_owner: { name: "Janice Krpan", state: "active" } });
    mockWorkspaces([owned], [owned]);
    vi.mocked(agreementsApi.getClientAgreements).mockResolvedValue(
      agreements({
        relationship: "existing",
        relationship_basis: "closed_won",
        basis_text: "Closed Won deal",
        needs_attention: false,
        nda: {
          kind: "NDA",
          state: "standard",
          source: "standard",
          standard_version: 1,
          batch_id: "AG-0001",
          file_name: "SmarTek21_Standard_NDA.pdf",
          file_size: 214000,
          uploaded_by: "Srikanth Parimi",
          uploaded_at: "2026-10-15T18:00:00Z",
          history: [],
        },
        msa: { kind: "MSA", state: "existing_none", history: [] },
      }),
    );
    vi.mocked(agreementsApi.getStandardDocuments).mockResolvedValue({
      NDA: null,
      MSA: {
        kind: "MSA",
        version: 1,
        file_name: "SmarTek21_Standard_MSA.pdf",
        file_size: 388000,
        uploaded_by: "Srikanth Parimi",
        uploaded_at: "2026-10-15T18:00:00Z",
        attached_clients: 85,
      },
    });
    const attach = vi.spyOn(agreementsApi, "attachStandardToClient").mockResolvedValue({
      kind: "MSA",
      state: "standard",
      history: [],
    });
    const onChanged = vi.fn();
    renderClient({ onChanged });
    await screen.findByText("All linked opportunities · 1");
    expect(screen.getByText("Account owner: Janice Krpan")).toBeInTheDocument();
    const nda = within(await screen.findByRole("article", { name: "NDA" }));
    expect(nda.getByText("✓ Standard copy")).toBeInTheDocument();
    expect(nda.getByText("Standard NDA v1 · batch AG-0001")).toBeInTheDocument();
    const msa = within(screen.getByRole("article", { name: "MSA" }));
    expect(msa.getByText("Existing · none attached")).toBeInTheDocument();
    fireEvent.click(msa.getByRole("button", { name: "Attach standard copy" }));
    await waitFor(() => expect(attach).toHaveBeenCalledWith(CLIENT.id, "MSA"));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
  });

  it("says when no opportunity is linked", async () => {
    mockWorkspaces([], []);
    renderClient();
    expect(await screen.findByText("No opportunities linked to this client.")).toBeInTheDocument();
    expect(screen.getByText("All linked opportunities · 0")).toBeInTheDocument();
  });

  it("a client with no HubSpot deals keeps the account owner its Clients row showed; its agreements come from the panel", async () => {
    mockWorkspaces([], []);
    vi.mocked(agreementsApi.getClientAgreements).mockResolvedValue(
      agreements({
        relationship: "existing",
        relationship_basis: "sow_engagement",
        basis_text: "Engagement from the forecast model",
        needs_attention: false,
        deals: { open: 0, won: 0, lost: 0, furthest_open_stage: 0 },
        nda: { kind: "NDA", state: "client", source: "client", file_name: "Vector-NDA.pdf", history: [] },
        msa: { kind: "MSA", state: "existing_none", history: [] },
      }),
    );
    renderClient({
      client: {
        ...CLIENT,
        facts: {
          account_owner: { name: "Janice Krpan", state: "active" },
          agreements: { nda_on_file: true, msa_on_file: false },
        },
      },
    });
    expect(await screen.findByText("No opportunities linked to this client.")).toBeInTheDocument();
    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByText("Account owner: Janice Krpan")).toBeInTheDocument();
    expect(dialog.getByRole("heading", { name: "Agreement documents" })).toBeInTheDocument();
    expect(within(await dialog.findByRole("article", { name: "NDA" })).getByText("✓ Client copy")).toBeInTheDocument();
    expect(within(dialog.getByRole("article", { name: "MSA" })).getByText("Existing · none attached")).toBeInTheDocument();
    expect(dialog.getByText("Engagement from the forecast model")).toBeInTheDocument();
  });

  it("without deals or row facts it says 'Not assigned' and still shows both agreement states", async () => {
    mockWorkspaces([], []);
    renderClient();
    expect(await screen.findByText("No opportunities linked to this client.")).toBeInTheDocument();
    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByText("Account owner: Not assigned")).toBeInTheDocument();
    expect(dialog.getByRole("heading", { name: "Agreement documents" })).toBeInTheDocument();
    expect(within(await dialog.findByRole("article", { name: "NDA" })).getByText("Missing")).toBeInTheDocument();
    expect(within(dialog.getByRole("article", { name: "MSA" })).getByText("Missing")).toBeInTheDocument();
  });

  it("lists a linked deal with no currency without '$'", async () => {
    const noCurrency = deal({ title: "Unpriced rollout", amount: "542000", currency: null });
    mockWorkspaces([noCurrency], [noCurrency]);
    renderClient();
    await screen.findByText("All linked opportunities · 1");
    expect(
      screen.getByText("6 · Contracting / Drive Commitment · 542k · no currency · Srikanth Parimi"),
    ).toBeInTheDocument();
    // The client's total is USD and keeps its "$".
    expect(valueOf("All open deal value")).toBe("$609,000");
  });

  it("names a failed load", async () => {
    vi.spyOn(wsApi, "getWorkspace").mockRejectedValue(new Error("API error 500"));
    renderClient();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The client details could not load.");
    expect(alert).toHaveTextContent("API error 500");
  });
});
