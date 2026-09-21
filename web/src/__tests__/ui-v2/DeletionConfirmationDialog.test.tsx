/**
 * DeletionConfirmationDialog — S13a-FE acceptance tests.
 *
 * The dialog is the single UI entry point for hard-delete + archive, so
 * three invariants matter:
 *
 *  1. Draft assessment renders the cascade counts verbatim and shows the
 *     red Delete button.
 *  2. Approved (or hubspot_linked) assessment hides Delete and offers
 *     "Archive instead" with the reason the server returned.
 *  3. A 4xx from the API is surfaced inline, and the dialog stays open so
 *     the user can retry (or cancel) — never a silent failure.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../../api/client";
import type { DeletionAssessmentResponse } from "../../api/client";
import { DeletionConfirmationDialog } from "../../ui-v2/DeletionConfirmationDialog";

const CLIENT_ID = "11111111-1111-1111-1111-111111111111";

function renderDialog(overrides: {
  onConfirmed?: (r: DeletionAssessmentResponse) => void;
  onOpenChange?: (o: boolean) => void;
} = {}) {
  const onConfirmed = overrides.onConfirmed ?? vi.fn();
  const onOpenChange = overrides.onOpenChange ?? vi.fn();
  render(
    <DeletionConfirmationDialog
      open={true}
      onOpenChange={onOpenChange}
      kind="client"
      id={CLIENT_ID}
      name="Peppermill Casino"
      onConfirmed={onConfirmed}
    />,
  );
  return { onConfirmed, onOpenChange };
}

describe("DeletionConfirmationDialog", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("draft: renders the cascade counts and the red Delete button, then calls the delete API", async () => {
    vi.spyOn(apiClient, "assessClientDeletion").mockResolvedValue({
      state: "draft",
      reason: "no approvals, no signed SOW, no HubSpot link",
      counts: {
        clients: 1,
        opportunities: 1,
        sows: 2,
        gm_models_deleted: 8,
        resource_lines: 17,
        client_contacts: 5,
        legal_entities: 1,
      },
    });
    const deleteSpy = vi
      .spyOn(apiClient, "deleteClient")
      .mockResolvedValue({
        state: "deleted",
        reason: "ok",
        counts: { clients: 1 },
      });

    const { onConfirmed } = renderDialog();

    // Cascade lines render, each with its integer count + role name.
    await waitFor(() => {
      expect(screen.getByTestId("deletion-cascade-list")).toBeInTheDocument();
    });
    const list = screen.getByTestId("deletion-cascade-list");
    expect(list).toHaveTextContent("1 client");
    expect(list).toHaveTextContent("1 opportunity");
    expect(list).toHaveTextContent("2 SOWs");
    expect(list).toHaveTextContent("8 GM models");
    expect(list).toHaveTextContent("17 resource lines");
    expect(list).toHaveTextContent("5 contacts");
    expect(list).toHaveTextContent("1 legal entity");

    // Delete button is present; Archive button is not.
    const del = screen.getByTestId("deletion-confirm");
    expect(del).toHaveTextContent("Delete");
    expect(screen.queryByTestId("deletion-archive")).toBeNull();

    await userEvent.click(del);

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith(CLIENT_ID, undefined);
    });
    expect(onConfirmed).toHaveBeenCalled();
  });

  it("approved: hides Delete, shows Archive-instead with the server reason", async () => {
    vi.spyOn(apiClient, "assessClientDeletion").mockResolvedValue({
      state: "approved",
      reason:
        "at least one opportunity has an approval package or a signed SOW; the approval trail is append-only",
      counts: { opportunities: 2 },
    });
    const archiveSpy = vi
      .spyOn(apiClient, "archiveClient")
      .mockResolvedValue({
        state: "archived",
        reason: "ok",
        counts: { client: 1 },
      });

    renderDialog();

    await waitFor(() => {
      expect(screen.getByTestId("deletion-cannot-delete")).toBeInTheDocument();
    });
    // The hard-delete button is not rendered for approved records.
    expect(screen.queryByTestId("deletion-confirm")).toBeNull();

    // The reason the API returned is visible to the user.
    expect(screen.getByTestId("deletion-server-reason")).toHaveTextContent(
      /approval package/i,
    );

    // Archive-instead is the primary action.
    const archive = screen.getByTestId("deletion-archive");
    expect(archive).toHaveTextContent("Archive instead");

    // Type a reason then archive.
    await userEvent.type(
      screen.getByTestId("deletion-archive-reason"),
      "cleaning stale record",
    );
    await userEvent.click(archive);

    await waitFor(() => {
      expect(archiveSpy).toHaveBeenCalledWith(
        CLIENT_ID,
        "cleaning stale record",
      );
    });
  });

  it("hubspot_linked: shows the HubSpot warning + Archive-instead button", async () => {
    vi.spyOn(apiClient, "assessClientDeletion").mockResolvedValue({
      state: "hubspot_linked",
      reason:
        "at least one opportunity is linked to a live HubSpot deal; the record will resurrect on the next HubSpot sync if hard deleted",
      counts: { opportunities: 1 },
    });

    renderDialog();

    await waitFor(() => {
      expect(screen.getByTestId("deletion-cannot-delete")).toBeInTheDocument();
    });
    expect(screen.getByTestId("deletion-cannot-delete")).toHaveTextContent(
      /HubSpot/,
    );
    expect(screen.getByTestId("deletion-archive")).toBeInTheDocument();
    expect(screen.queryByTestId("deletion-confirm")).toBeNull();
  });

  it("surfaces a 4xx from the delete API inline and keeps the dialog open", async () => {
    vi.spyOn(apiClient, "assessClientDeletion").mockResolvedValue({
      state: "draft",
      reason: "no approvals, no signed SOW, no HubSpot link",
      counts: { clients: 1, opportunities: 1 },
    });
    const err = new apiClient.ApiError(
      409,
      { detail: "client cannot be hard-deleted (approved); use archive instead" },
      "client cannot be hard-deleted (approved); use archive instead",
    );
    vi.spyOn(apiClient, "deleteClient").mockRejectedValue(err);

    const onOpenChange = vi.fn();
    const onConfirmed = vi.fn();
    renderDialog({ onOpenChange, onConfirmed });

    await waitFor(() =>
      expect(screen.getByTestId("deletion-confirm")).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByTestId("deletion-confirm"));

    await waitFor(() =>
      expect(screen.getByTestId("deletion-action-error")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("deletion-action-error")).toHaveTextContent(
      /cannot be hard-deleted/i,
    );
    // The dialog stays open — the API error did not close it.
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    expect(onConfirmed).not.toHaveBeenCalled();
  });
});
