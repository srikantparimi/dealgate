/**
 * S21F:T14.06 — the workspace sheet sends the explicit decision kind.
 *
 * "Not renewing" must reach the API as `outcome: "not_renewing"` with a
 * closed status, because the server files closeout/roll-off tasks off
 * that explicit field — never off the free-text summary.
 */
import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import * as apiClient from "../../../api/client";
import type { RenewalRow } from "../../../api/client";
import { RenewalWorkspaceSheet } from "./RenewalWorkspaceSheet";

const RENEWAL = "11111111-1111-4111-8111-111111111111";
const OPP = "22222222-2222-4222-8222-222222222222";

function row(overrides: Partial<RenewalRow> = {}): RenewalRow {
  return {
    id: RENEWAL,
    opportunity_id: OPP,
    term_end: "2026-12-01",
    trigger_date: "2026-10-02",
    status: "open",
    outcome_summary: null,
    replacement_sow_version_id: null,
    opened_at: "2026-09-17T10:00:00",
    updated_at: "2026-09-17T10:00:00",
    days_until_end: 59,
    hubspot_deal_id: "H-DEAL-1",
    owner_id: OPP,
    client_id: null,
    ...overrides,
  } as RenewalRow;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("RenewalWorkspaceSheet", () => {
  it("sends outcome=not_renewing with a closed status", async () => {
    const renewal = row();
    const patchSpy = vi
      .spyOn(apiClient, "patchRenewal")
      .mockResolvedValue({ ...renewal, status: "closed" });

    render(
      <RenewalWorkspaceSheet
        open
        onOpenChange={() => {}}
        renewal={renewal}
        today="2026-10-03"
      />,
    );

    const user = userEvent.setup();
    await user.selectOptions(
      screen.getByTestId("renewal-outcome"),
      "not_renewing",
    );
    await user.click(screen.getByTestId("renewal-save"));

    await waitFor(() => expect(patchSpy).toHaveBeenCalledTimes(1));
    const [id, body] = patchSpy.mock.calls[0];
    expect(id).toBe(RENEWAL);
    expect(body).toEqual({
      outcome_summary: "Not renewing",
      status: "closed",
      outcome: "not_renewing",
    });
  });

  it("sends a signed outcome as extended", async () => {
    const renewal = row();
    const patchSpy = vi
      .spyOn(apiClient, "patchRenewal")
      .mockResolvedValue({ ...renewal, status: "extended" });

    render(
      <RenewalWorkspaceSheet
        open
        onOpenChange={() => {}}
        renewal={renewal}
        today="2026-10-03"
      />,
    );

    const user = userEvent.setup();
    await user.selectOptions(
      screen.getByTestId("renewal-outcome"),
      "extension_signed",
    );
    await user.click(screen.getByTestId("renewal-save"));

    await waitFor(() => expect(patchSpy).toHaveBeenCalledTimes(1));
    const [, body] = patchSpy.mock.calls[0];
    expect(body.status).toBe("extended");
    expect(body.outcome).toBe("extension_signed");
  });
});
