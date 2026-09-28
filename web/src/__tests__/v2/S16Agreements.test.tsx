import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import * as api from "../../api/client";
import { AgreementsRegisterPage } from "../../pages/v2/AgreementsRegister";
import { AgreementsPanel } from "../../pages/AgreementsPanel";

afterEach(() => vi.restoreAllMocks());

it("shows entity tracking without internal approval ceremony", async () => {
  vi.spyOn(api, "getMe").mockResolvedValue({
    id: "legal",
    name: "Lee",
    email: "lee@example.test",
    groups: ["Legal"],
  });
  vi.spyOn(api, "listAgreements").mockResolvedValue({
    allowed_states: ["missing", "requested", "sent", "executed", "expired"],
    items: [
      {
        id: "a",
        legal_entity_id: "entity",
        kind: "NDA",
        state: "executed",
        display_state: "expiring",
        client_name: "Example",
        legal_entity_name: "Example US LLC",
        owner_email: "lee@example.test",
        next_action: "Renew NDA",
        due_date: null,
        effective_from: "2026-01-01",
        expiry: "2026-10-01",
        notice_days: null,
        evidence_s3_key: "agreements/a/signed.pdf",
        signatories: null,
        created_at: "2026-01-01",
        updated_at: "2026-01-01",
      },
    ],
  });
  render(
    <MemoryRouter>
      <AgreementsRegisterPage />
    </MemoryRouter>,
  );
  expect(await screen.findByText("Example US LLC")).toBeInTheDocument();
  expect(screen.getByText("Expiring")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Download NDA" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByText(/Internal approval|Legal execution|Approved|In review/),
  ).not.toBeInTheDocument();
});

it("client detail opens the same entity-scoped register", () => {
  render(
    <MemoryRouter>
      <AgreementsPanel legalEntityId="entity" />
    </MemoryRouter>,
  );
  expect(screen.getByRole("link")).toHaveAttribute(
    "href",
    "/agreements?entity=entity",
  );
});
