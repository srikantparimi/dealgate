// S24-AG1 F3/B10 · the client strip on the deal page, the client page and the SOW workspace: the shared
// states and wording (GET /clients/{id}/agreements), the warning for a net-new client past stage 1, an
// Upload that opens the upload dialog right here for writers (CLAUDE.md rule 13), and a locked Upload
// with its reason for everyone else.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as agreementsApi from "../../api/agreements";
import type { AgreementKind, ClientAgreements, DocCard, DocState } from "../../api/agreements";
import { ClientAgreementPresence } from "../../ui-v2/ClientAgreementPresence";
import { Toaster } from "../../ui-v2/primitives/toaster";
import { TooltipProvider } from "../../ui-v2/primitives/tooltip";

function doc(kind: AgreementKind, state: DocState): DocCard {
  return { kind, state, history: [] };
}

function data(overrides: Partial<ClientAgreements> = {}): ClientAgreements {
  return {
    client_id: "a",
    name: "Cobalt Pharma",
    relationship: "net_new",
    relationship_basis: "none",
    requirement: "required",
    needs_attention: true,
    deals: { open: 1, won: 0, lost: 0, furthest_open_stage: 4 },
    nda: doc("NDA", "missing"),
    msa: doc("MSA", "standard"),
    can_write: true,
    ...overrides,
  };
}

afterEach(cleanup);
beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(agreementsApi, "getStandardDocuments").mockResolvedValue({ NDA: null, MSA: null });
});

const mount = (id = "a") =>
  render(
    <MemoryRouter>
      <TooltipProvider>
        <Toaster>
          <ClientAgreementPresence clientId={id} />
        </Toaster>
      </TooltipProvider>
    </MemoryRouter>,
  );

it("shows the shared states, the warning and links to the client's panel", async () => {
  vi.spyOn(agreementsApi, "getClientAgreements").mockResolvedValue(data());
  mount();
  const strip = within(await screen.findByRole("region", { name: "Client NDA and MSA" }));
  expect(await strip.findByText("Net new, past stage 1, NDA missing.")).toBeInTheDocument();
  expect(strip.getByText("Missing")).toBeInTheDocument();
  expect(strip.getByText("✓ Standard copy")).toBeInTheDocument();
  expect(strip.getByRole("link", { name: "View MSA documents" })).toHaveAttribute(
    "href",
    "/agreements?client_id=a&kind=MSA",
  );
  // Nothing held for the NDA: nothing to view.
  expect(strip.queryByRole("link", { name: "View NDA documents" })).toBeNull();
});

it("a writer uploads in place: the dialog opens here for that client and kind", async () => {
  vi.spyOn(agreementsApi, "getClientAgreements").mockResolvedValue(data());
  mount();
  fireEvent.click(await screen.findByRole("button", { name: "Upload NDA" }));
  const dialog = within(await screen.findByRole("dialog"));
  expect(dialog.getByRole("heading", { name: "Upload a document" })).toBeInTheDocument();
  expect(dialog.getByLabelText("Client")).toHaveValue("Cobalt Pharma");
  expect(dialog.getByLabelText("Document type")).toHaveValue("NDA");
  expect(dialog.getByLabelText("What is this?")).toBeDisabled();
});

it("does not call failed loading absence", async () => {
  vi.spyOn(agreementsApi, "getClientAgreements").mockRejectedValue(new Error("Access unavailable"));
  mount();
  expect(await screen.findByRole("alert")).toHaveTextContent("Access unavailable");
  expect(screen.queryByText("Missing")).toBeNull();
  expect(screen.getByRole("button", { name: "Retry documents" })).toBeInTheDocument();
});

it("readers see the Upload locked with its reason and no dialog", async () => {
  vi.spyOn(agreementsApi, "getClientAgreements").mockResolvedValue(data({ can_write: false }));
  mount();
  const upload = await screen.findByRole("button", { name: /^Upload NDA/ });
  expect(upload).toHaveAttribute("aria-disabled", "true");
  fireEvent.click(upload);
  expect(
    await screen.findByText("Only Legal and SystemAdmin can change agreements. You can view and download."),
  ).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).toBeNull();
});

it("does not show previous client presence after a route change", async () => {
  let resolve!: (value: ClientAgreements) => void;
  vi.spyOn(agreementsApi, "getClientAgreements").mockImplementation((clientId) =>
    clientId === "a"
      ? new Promise((r) => {
          resolve = r;
        })
      : Promise.resolve(data({ client_id: "b", needs_attention: false, nda: doc("NDA", "not_needed"), msa: doc("MSA", "not_needed") })),
  );
  const view = mount();
  view.rerender(
    <MemoryRouter>
      <TooltipProvider>
        <Toaster>
          <ClientAgreementPresence clientId="b" />
        </Toaster>
      </TooltipProvider>
    </MemoryRouter>,
  );
  expect(await screen.findAllByText("Not needed now")).toHaveLength(2);
  await act(async () => resolve(data()));
  expect(screen.queryByText("Net new, past stage 1, NDA missing.")).toBeNull();
  expect(screen.queryByText("Missing")).toBeNull();
});

it("without a client says so", () => {
  render(
    <MemoryRouter>
      <ClientAgreementPresence clientId={null} />
    </MemoryRouter>,
  );
  expect(screen.getByText("Client documents unavailable: no client linked.")).toBeInTheDocument();
});
