// S23-PL2 · the page shell with the records lane's real components (no
// stand-ins): the prototype's order (tabs → toolbar → chips → records), a card's
// number on the real pagination line (F4), the real tabs relabelling the owner
// filter (F7), and the real bulk bar opening the page's group dialog (F13).
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as agreementsApi from "../../api/agreements";
import * as appConfig from "../../api/appConfig";
import * as api from "../../api/client";
import * as wsApi from "../../api/pipelineWorkspace";
import type { ClientRow, WorkspaceQuery } from "../../api/pipelineWorkspace";
import { PipelinePage } from "../../pages/v2/Pipeline";
import { Toaster } from "../../ui-v2/primitives/toaster";
import { BackButton, LocationProbe, answerFor, fakeDeal, populated, renderAt } from "./S23PipelineShellFixtures";

const DEALS = [
  fakeDeal(),
  fakeDeal({ id: "deal-2", title: "Quality engineering pod", client: { id: "client-2", name: "Keystone Energy" } }),
];
const CLIENT: ClientRow = {
  id: "client-1",
  name: "Vector Systems",
  account_owner: { name: null, state: "none" },
  matching_deals: 1,
  open_deals: 1,
  matching_value_usd: "542000",
  earliest_close_date: "2026-12-28",
  last_activity_date: null,
  days_since_activity: null,
  agreements: { nda_on_file: false, msa_on_file: false, nda_state: "missing", msa_state: "missing" },
  flags: [],
  hubspot_company_id: null,
};

function answer(query: Partial<WorkspaceQuery>) {
  const ws = answerFor(query, populated());
  return { ...ws, rows: query.tab === "clients" ? [CLIENT] : DEALS };
}

beforeEach(() => {
  vi.spyOn(api, "getMe").mockResolvedValue({ id: "user-1", email: "e2e@example.com", name: "E2E", groups: ["Sales"] });
  vi.spyOn(appConfig, "useAppConfig").mockReturnValue({ hubspotPortalId: "1234567", loading: false });
  vi.spyOn(wsApi, "listWorkspaceViews").mockResolvedValue([]);
  vi.spyOn(wsApi, "listWorkspaceGroups").mockResolvedValue([
    { id: "group-q4", name: "Q4 priorities", deal_ids: ["deal-3"] },
  ]);
  vi.spyOn(wsApi, "getWorkspace").mockImplementation(async (query) => answer(query));
});

afterEach(() => vi.restoreAllMocks());

const summary = () => screen.getByRole("region", { name: "Pipeline summary" });

describe("the page shell with the real records", () => {
  it("keeps the prototype's order: tabs, then the filter toolbar and chips, then the records", async () => {
    renderAt(<PipelinePage />);
    const title = await screen.findByRole("button", { name: "Cloud modernization" });
    const tabs = screen.getByRole("group", { name: "Records" });
    const filters = screen.getByRole("region", { name: "Pipeline filters" });
    const chip = screen.getByRole("button", { name: "Remove Status: Open (includes on hold)" });
    expect(tabs.compareDocumentPosition(filters) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(filters.compareDocumentPosition(chip) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(chip.compareDocumentPosition(title) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getAllByRole("region", { name: "Pipeline records" })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Views & groups" })).toHaveClass("md:hidden");
  });

  it("a card's number is the real list's count (deals and, for agreement gaps, clients)", async () => {
    renderAt(<PipelinePage />);
    await screen.findByText("1–25 of 109 opportunities");
    fireEvent.click(within(summary()).getByRole("button", { name: /^Overdue next actions/ }));
    expect(await screen.findByText("1–10 of 10 opportunities")).toBeInTheDocument();
    expect(within(summary()).getByRole("button", { name: /^Overdue next actions/ })).toHaveTextContent("10");

    fireEvent.click(within(summary()).getByRole("button", { name: /^Agreement gaps/ }));
    expect(await screen.findByText("1–25 of 33 clients")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Clients/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("the real tabs switch the owner filter between deal owner and account owner", async () => {
    renderAt(<PipelinePage />);
    await screen.findByRole("button", { name: "Cloud modernization" });
    const bar = () => within(screen.getByRole("region", { name: "Pipeline filters" }));
    expect(bar().getByRole("button", { name: "Deal owner" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Clients/ }));
    await waitFor(() => expect(bar().getByRole("button", { name: "Account owner" })).toBeInTheDocument());
  });

  it("the real bulk bar opens the page's group dialog with the selected deal", async () => {
    const add = vi.spyOn(wsApi, "addDealsToGroup").mockResolvedValue(undefined);
    renderAt(<PipelinePage />);
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select Cloud modernization" }));
    const bulk = await screen.findByRole("group", { name: "Bulk actions" });
    expect(bulk).toHaveTextContent("1 selected");
    fireEvent.click(within(bulk).getByRole("button", { name: "Add to group" }));
    const dialog = await screen.findByRole("dialog", { name: "Add selected deals to a group" });
    expect(dialog).toHaveAccessibleDescription("1 selected opportunity will be included.");
    fireEvent.click(within(dialog).getByRole("button", { name: "Add selected" }));
    await waitFor(() => expect(add).toHaveBeenCalledWith("group-q4", ["deal-1"]));
    expect(await screen.findByText("Added selected opportunities to “Q4 priorities”.")).toBeInTheDocument();
  });

  it("an old link to a page past the end is corrected in place, so one Back leaves the Pipeline", async () => {
    // 20 rows fit on page 1; page 9 comes back empty.
    const pagesAsked: number[] = [];
    vi.mocked(wsApi.getWorkspace).mockImplementation(async (query: Partial<WorkspaceQuery>) => {
      const page = query.page ?? 1;
      pagesAsked.push(page);
      const ws = populated();
      return { ...ws, rows: page === 1 ? DEALS : [], page: { number: page, size: 25, total_rows: 20, total_value_usd: "1" } };
    });
    render(
      <Toaster>
        <MemoryRouter initialEntries={["/command-center", "/pipeline?page=9"]} initialIndex={1}>
          <Routes>
            <Route path="/command-center" element={<p>COMMAND CENTER</p>} />
            <Route
              path="/pipeline"
              element={
                <>
                  <PipelinePage />
                  <LocationProbe />
                  <BackButton />
                </>
              }
            />
          </Routes>
        </MemoryRouter>
      </Toaster>,
    );
    await screen.findByRole("button", { name: "Cloud modernization" });
    expect(screen.getByTestId("location")).toHaveTextContent(/^\?status=open$/);
    expect(pagesAsked).toEqual([9, 1]);
    fireEvent.click(screen.getByRole("button", { name: "test: browser back" }));
    // A pushed correction would land on ?page=9 again, which corrects forward again.
    expect(await screen.findByText("COMMAND CENTER", undefined, { timeout: 2_000 })).toBeInTheDocument();
    expect(pagesAsked).toEqual([9, 1]);
  });

  it("a client without HubSpot deals, previewed from the Clients tab, keeps the owner and asks for its agreements", async () => {
    // S24-AG1 F3: the preview's agreement documents are the shared client panel, which reads the client's
    // NDA and MSA from the server (held pending here; the panel's own tests cover what it shows).
    const clientAgreements = vi.spyOn(agreementsApi, "getClientAgreements").mockReturnValue(new Promise(() => {}));
    const local: ClientRow = {
      ...CLIENT,
      id: "client-9",
      name: "Local SOW Client",
      account_owner: { name: "Janice Krpan", state: "active" },
      matching_deals: 0,
      open_deals: 0,
      matching_value_usd: null,
      agreements: { nda_on_file: true, msa_on_file: true, nda_state: "client", msa_state: "standard" },
    };
    vi.mocked(wsApi.getWorkspace).mockImplementation(async (query: Partial<WorkspaceQuery>) => {
      const ws = answerFor(query, populated());
      // The preview's reads are scoped to the client, which has no deal.
      if (query.client) return { ...ws, rows: [], page: { ...ws.page, total_rows: 0 } };
      return { ...ws, rows: query.tab === "clients" ? [local] : DEALS };
    });
    renderAt(<PipelinePage />, "/pipeline?tab=clients&include_unmatched_clients=true");
    fireEvent.click(await screen.findByRole("button", { name: "Preview Local SOW Client" }));
    const preview = await screen.findByRole("dialog", { name: "Local SOW Client" });
    expect(await within(preview).findByText("No opportunities linked to this client.")).toBeInTheDocument();
    expect(within(preview).getByText("Account owner: Janice Krpan")).toBeInTheDocument();
    expect(within(preview).getByRole("region", { name: "Agreement documents" })).toBeInTheDocument();
    expect(clientAgreements).toHaveBeenCalledWith("client-9", expect.anything());
  });

  it("a deal title opens the real preview; its Watch deal goes through the page", async () => {
    const watch = vi.spyOn(wsApi, "watchDeal").mockResolvedValue(undefined);
    renderAt(<PipelinePage />);
    fireEvent.click(await screen.findByRole("button", { name: "Cloud modernization" }));
    const preview = await screen.findByRole("dialog", { name: "Cloud modernization" });
    fireEvent.click(within(preview).getByRole("button", { name: /Watch deal/ }));
    await waitFor(() => expect(watch).toHaveBeenCalledWith("deal-1"));
  });

  it("F1 · the app's header copy, and none of the prototype's own chrome (theme toggle, demo controls, notes dialog)", async () => {
    renderAt(<PipelinePage />);
    await screen.findByRole("button", { name: "Cloud modernization" });
    expect(screen.getByRole("heading", { level: 1, name: "Pipeline" })).toBeInTheDocument();
    expect(screen.getByText("Commercial workspace")).toBeInTheDocument();
    expect(screen.getByText("Every relationship. Every opportunity. One clear next step.")).toBeInTheDocument();
    expect(screen.getByText("USD · calendar dates · today is Oct 14, 2026 (America/Los_Angeles)")).toBeInTheDocument();
    const text = document.body.textContent ?? "";
    for (const chrome of ["◐", "PROTOTYPE", "Prototype", "Work data", "What changed from the old page", "illustrative deals", "Preview workspace"]) {
      expect(text).not.toContain(chrome);
    }
    expect(screen.queryByRole("button", { name: "Switch light and dark appearance" })).toBeNull();
  });
});
