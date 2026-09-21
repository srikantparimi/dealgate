/**
 * Pipeline row-menu — S13a-FE acceptance.
 *
 * The delete role gate lives on the server; the frontend just hides the
 * button when the caller's Cognito groups don't match. Two tests pin
 * that:
 *
 *  - Admin sees the row kebab and can open the delete dialog.
 *  - A plain Sales user sees no kebab (and no Delete… item).
 */

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../../api/client";
import * as cognito from "../../auth/cognito";
import { PipelinePage } from "../../pages/v2/Pipeline";

const CLIENT_ID = "22222222-2222-2222-2222-222222222222";

function stubCognito(groups: string[]) {
  vi.spyOn(cognito, "getIdTokenClaims").mockReturnValue({
    sub: "user-1",
    email: "alice@smartek21.com",
    name: "Alice",
    "cognito:groups": groups,
  });
}

function stubApi() {
  vi.spyOn(apiClient, "listAgreements").mockResolvedValue({
    items: [],
    allowed_states: [],
  });
  vi.spyOn(apiClient, "listClients").mockResolvedValue({
    items: [
      {
        id: CLIENT_ID,
        name: "Peppermill Casino",
        hubspot_company_id: "COMP-99",
        coverage_state: "Complete",
        opportunity_count: 1,
        owner_ids: ["11111111-1111-1111-1111-111111111111"],
        owners: [
          { id: "11111111-1111-1111-1111-111111111111", name: "Alice" },
        ],
        sources: ["sow_upload"],
      },
    ],
    page: 1,
    size: 25,
    total: 1,
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/pipeline"]}>
      <PipelinePage />
    </MemoryRouter>,
  );
}

describe("PipelinePage row-menu delete gate", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    stubApi();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the row kebab menu trigger for an admin", async () => {
    stubCognito(["SystemAdmin"]);

    renderPage();

    // Row rendered, kebab trigger present with the correct aria label.
    await waitFor(() => {
      expect(screen.getByText("Peppermill Casino")).toBeInTheDocument();
    });
    const kebab = screen.getByTestId(`row-menu-${CLIENT_ID}`);
    expect(kebab).toBeInTheDocument();
    expect(kebab).toHaveAttribute(
      "aria-label",
      "Actions for Peppermill Casino",
    );
  });

  it("hides the row kebab menu for a plain Sales user", async () => {
    stubCognito(["Sales"]);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Peppermill Casino")).toBeInTheDocument();
    });
    // The kebab trigger is not rendered for a non-privileged user.
    expect(screen.queryByTestId(`row-menu-${CLIENT_ID}`)).toBeNull();
    expect(screen.queryByTestId(`row-delete-${CLIENT_ID}`)).toBeNull();
  });
});
