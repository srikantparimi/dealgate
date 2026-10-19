// S24-AG1 FE-A · the page with the REAL shared dialogs and client panel (no
// stand-ins), for the two promises the page itself makes about them: a page
// view asks for exactly one thing (the workspace; B3), and a dialog opened from
// the page is modal (the page behind it is hidden from assistive technology),
// closes on Escape and gives focus back to the control that opened it (F12).
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as agreementsApi from "../../api/agreements";
import type { ClientAgreements, DocCard } from "../../api/agreements";
import * as clientApi from "../../api/client";
import { IDS, renderAgreements, tonight } from "./S24FeAFixtures";

function card(kind: "NDA" | "MSA"): DocCard {
  return { kind, state: "existing_none", history: [] };
}

const PANEL: ClientAgreements = {
  client_id: IDS.lakeside,
  name: "Lakeside Group",
  relationship: "existing",
  relationship_basis: "closed_won",
  requirement: "none",
  needs_attention: false,
  possible_duplicates: [],
  deals: { open: 0, won: 1, lost: 1, furthest_open_stage: 0 },
  nda: card("NDA"),
  msa: card("MSA"),
  can_write: true,
  business_units: [{ name: "IT Avalon", region: "US" }],
  flags: [],
  basis_text: "Closed Won deal",
};

const OTHER_READS = [
  "getAgreementDocuments",
  "getAgreementActivity",
  "getStandardDocuments",
  "getClientAgreements",
  "listBatches",
  "getHubspotValues",
] as const;

beforeEach(() => {
  vi.spyOn(agreementsApi, "getAgreementsWorkspace").mockImplementation(async () => tonight());
  vi.spyOn(agreementsApi, "getAgreementDocuments").mockResolvedValue({ total: 0, items: [] });
  vi.spyOn(agreementsApi, "getAgreementActivity").mockResolvedValue({ total: 0, items: [] });
  vi.spyOn(agreementsApi, "getStandardDocuments").mockResolvedValue({ NDA: null, MSA: null });
  vi.spyOn(agreementsApi, "getClientAgreements").mockResolvedValue(PANEL);
  vi.spyOn(agreementsApi, "listBatches").mockResolvedValue({ items: [] });
  vi.spyOn(agreementsApi, "getHubspotValues").mockResolvedValue({ stored: false, items: [] });
  vi.spyOn(clientApi, "getMe").mockResolvedValue({ id: "me", email: "me@example.com", name: "Me", groups: ["SystemAdmin"] });
});

afterEach(() => vi.restoreAllMocks());

it("a page view asks for the workspace once and nothing else", async () => {
  renderAgreements();
  await screen.findByRole("button", { name: "Cobalt Pharma" });
  await new Promise((resolve) => setTimeout(resolve, 50));
  expect(agreementsApi.getAgreementsWorkspace).toHaveBeenCalledTimes(1);
  for (const name of OTHER_READS) expect(agreementsApi[name]).not.toHaveBeenCalled();
  expect(clientApi.getMe).not.toHaveBeenCalled();
});

it("the real upload drawer is modal, closes on Escape and gives focus back to Upload document", async () => {
  renderAgreements();
  await screen.findByRole("button", { name: "Cobalt Pharma" });
  const opener = screen.getByRole("button", { name: /Upload document/ });
  opener.focus();
  fireEvent.click(opener);
  const dialog = await screen.findByRole("dialog");
  expect(screen.getByRole("table", { name: "Clients", hidden: true }).closest("[aria-hidden='true']")).not.toBeNull();
  fireEvent.keyDown(dialog, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  await waitFor(() => expect(document.activeElement).toBe(opener));
});

it("the real client panel opens from the client name, closes on Escape, leaves the URL and gives focus back", async () => {
  const view = renderAgreements();
  const name = await screen.findByRole("button", { name: "Lakeside Group" });
  name.focus();
  fireEvent.click(name);
  const dialog = await screen.findByRole("dialog");
  expect(view.params().get("client_id")).toBe(IDS.lakeside);
  await waitFor(() => expect(agreementsApi.getClientAgreements).toHaveBeenCalled());
  expect(vi.mocked(agreementsApi.getClientAgreements).mock.calls[0][0]).toBe(IDS.lakeside);
  fireEvent.keyDown(dialog, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(view.params().get("client_id")).toBeNull();
  await waitFor(() => expect(document.activeElement).toBe(name));
});
