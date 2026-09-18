/**
 * SOWConfirm — panel that renders the extracted SOW fields and lets the
 * account owner confirm each one before submitting to the GM build.
 *
 * We assert three story-critical behaviours:
 *
 *  - the extracted fields render with their page-ref link;
 *  - clicking `Confirm` flips a field's status chip to `confirmed`;
 *  - `Submit for GM build` stays disabled until every field is confirmed.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import { SOW_FIELDS, type SowVersion } from "../api/client";
import { SOWConfirm } from "../pages/SOWConfirm";

const VERSION_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const SOW_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
const OPP_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc";

function buildVersion(
  overrides: Partial<SowVersion> = {},
  fieldOverrides: Partial<Record<string, "confirmed" | "unconfirmed" | "disputed">> = {},
): SowVersion {
  const fields: SowVersion["extracted_fields"] = {};
  for (const [i, name] of SOW_FIELDS.entries()) {
    fields[name] = {
      value: `stub-${name}`,
      page_ref: i + 1,
      status: fieldOverrides[name] ?? "unconfirmed",
    };
  }
  return {
    id: VERSION_ID,
    sow_id: SOW_ID,
    opportunity_id: OPP_ID,
    uploaded_by: null,
    uploaded_at: "2026-09-17T10:00:00Z",
    file_s3_key: "sow/opp/test.pdf",
    file_hash: "sha256:abc",
    extracted_fields: fields,
    extract_status: "complete",
    extract_model: "anthropic.claude",
    extract_prompt_version: "sow-v1",
    confirmed_by: null,
    confirmed_at: null,
    engagement_type_suggested: "fixed_price",
    engagement_type_confirmed: null,
    download_url: "https://stub-sows.local/get/test.pdf?stub=1",
    ...overrides,
  };
}

describe("SOWConfirm", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders every extracted field with a page-ref link", () => {
    const v = buildVersion();
    render(
      <SOWConfirm version={v} onVersionChanged={() => {}} canEdit={true} />,
    );
    expect(screen.getByText("Scope summary")).toBeInTheDocument();
    expect(screen.getByText("Price")).toBeInTheDocument();
    expect(screen.getByText("Engagement type (suggested)")).toBeInTheDocument();
    // Page-ref link is rendered per field — "p.1" is the first.
    expect(screen.getByText("p.1")).toBeInTheDocument();
    // The submit button is present but disabled while fields remain
    // unconfirmed.
    const submit = screen.getByRole("button", { name: /submit for gm build/i });
    expect(submit).toBeDisabled();
  });

  it("flips a field to confirmed when the button is clicked", async () => {
    const v = buildVersion();
    const confirmed = buildVersion({}, { scope_summary: "confirmed" });
    const spy = vi
      .spyOn(apiClient, "confirmSowField")
      .mockResolvedValue(confirmed);
    const onChange = vi.fn();
    render(
      <SOWConfirm version={v} onVersionChanged={onChange} canEdit={true} />,
    );

    const confirmBtn = screen.getByRole("button", {
      name: /confirm scope summary/i,
    });
    await userEvent.click(confirmBtn);
    await waitFor(() => {
      expect(spy).toHaveBeenCalledTimes(1);
    });
    expect(spy.mock.calls[0][0]).toBe(VERSION_ID);
    expect(spy.mock.calls[0][1]).toBe("scope_summary");
    expect(onChange).toHaveBeenCalledWith(confirmed);
  });

  it("enables submit only after every field is confirmed", async () => {
    // Seed a version where every field is already confirmed.
    const overrides: Record<string, "confirmed"> = {};
    for (const name of SOW_FIELDS) {
      overrides[name] = "confirmed";
    }
    const v = buildVersion({}, overrides);
    const submitted = buildVersion(
      { confirmed_at: "2026-09-17T11:00:00Z", confirmed_by: "u" },
      overrides,
    );
    const spy = vi
      .spyOn(apiClient, "submitSowVersion")
      .mockResolvedValue(submitted);
    const onChange = vi.fn();
    render(
      <SOWConfirm version={v} onVersionChanged={onChange} canEdit={true} />,
    );
    const submit = screen.getByRole("button", { name: /submit for gm build/i });
    expect(submit).toBeEnabled();
    await userEvent.click(submit);
    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith(VERSION_ID);
    });
    expect(onChange).toHaveBeenCalledWith(submitted);
  });

  it("hides action buttons when canEdit is false", () => {
    const v = buildVersion();
    render(
      <SOWConfirm version={v} onVersionChanged={() => {}} canEdit={false} />,
    );
    expect(
      screen.queryByRole("button", { name: /confirm scope summary/i }),
    ).not.toBeInTheDocument();
    const submit = screen.getByRole("button", { name: /submit for gm build/i });
    expect(submit).toBeDisabled();
  });

  it("shows the manual-required banner when Bedrock is unavailable", () => {
    const v = buildVersion({ extract_status: "manual_required" });
    render(
      <SOWConfirm version={v} onVersionChanged={() => {}} canEdit={true} />,
    );
    expect(
      screen.getByText(/bedrock model access is not enabled/i),
    ).toBeInTheDocument();
  });
});
