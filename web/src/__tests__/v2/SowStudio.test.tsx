/**
 * SOW studio confirmation screen — Sprint 9 Wave 2 acceptance tests.
 *
 * Anchored to `docs/sow-first-principles.md` and CLAUDE.md rule 10.
 * The tests exercise the constraints the manifesto pins down:
 *
 * - The screen renders from a single `getSowConfirmation` payload.
 * - Every visible field has a provenance chip (no bare rows).
 * - `Submit for approval` is disabled while `needs_you.length > 0`.
 * - Submit calls `submitSowConfirmation` and navigates on success.
 * - Below-threshold engagement type surfaces the two-candidate chooser.
 * - Below-floor scenario shows the CEO gate step in `hold` state
 *   with the "Will trigger" microcopy.
 * - A blank form on open is a defect — the row-populated count is
 *   asserted at 0 for the well-formed fixture.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../../api/client";
import type { SowConfirmationPayload } from "../../api/client";
import { SowStudioPage } from "../../pages/v2/SowStudio";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const OPP = "00000000-0000-0000-0000-0000000000aa";

function makePayload(
  overrides: Partial<SowConfirmationPayload> = {},
): SowConfirmationPayload {
  return {
    source: {
    client_id: "c0000000-0000-0000-0000-000000000001",
    client_name: "Northwind Traders, Inc.",
    client_legal_name_extracted: "Northwind Traders, Inc.",
    legal_entity_name: "Northwind Traders US LLC",
    sow_title: "Northwind Traders, Inc. — platform modernisation",
    file_s3_key: "sow/abc/2026-sow.pdf",
    file_name: "2026-sow.pdf",
    ref_unit: "page",
    document_kind: "pdf",
  },
  sow_version: {
      id: "00000000-0000-0000-0000-0000000000ff",
      extract_status: "complete",
      engagement_type_suggested: "staff_aug",
      extracted_fields: {
        client_entity: {
          value: "Northstar Analytics — Delaware",
          provenance: "looked_up",
          source_id: "client-northstar",
        },
        sow_title: {
          value: "Data engineering — Q3 discovery",
          provenance: "extracted",
          page_ref: 1,
        },
        file: {
          value: "https://example.invalid/sows/northstar-q3.pdf",
          provenance: "extracted",
          page_ref: 1,
        },
        engagement_type: {
          value: "staff_aug",
          provenance: "calculated",
        },
        price: { value: "180000", provenance: "extracted", page_ref: 3 },
        currency: { value: "USD", provenance: "extracted", page_ref: 3 },
        term_start: { value: "2026-10-01", provenance: "extracted", page_ref: 2 },
        term_end: { value: "2027-03-31", provenance: "extracted", page_ref: 2 },
        notice_date: { value: "2027-01-31", provenance: "calculated" },
        billing_basis: { value: "T&M", provenance: "extracted", page_ref: 4 },
        deliverables: {
          value: "Two production data pipelines",
          provenance: "extracted",
          page_ref: 5,
        },
        milestones: { value: "M1, M2", provenance: "extracted", page_ref: 5 },
        acceptance_criteria: {
          value: "Client signoff per milestone",
          provenance: "extracted",
          page_ref: 6,
        },
        signatories: {
          value: "J. Doe (Northstar); A. Smith (DealGate)",
          provenance: "extracted",
          page_ref: 8,
        },
        rate_card: {
          value: "Northstar MSA v3",
          provenance: "looked_up",
          source_id: "card-northstar-v3",
        },
        rate_card_effective_from: {
          value: "2026-01-01",
          provenance: "looked_up",
        },
      },
    },
    engagement: {
      primary: { type: "staff_aug", confidence: 0.94 },
      secondary: null,
      rule_matched: "rule_named_roles_and_rates",
      auto_confirm: true,
    },
    staffing: {
      lines: [
        {
          role: "Data engineer",
          seniority: "Senior",
          location: "US",
          allocation_pct: "100",
          hours_billable: "480",
          hourly_bill_rate: "225",
          provenance: "extracted",
          source_id: null,
          warning: null,
          start_date: "2026-10-01",
          end_date: "2027-03-31",
        },
      ],
      notes: [],
      warnings: [],
      sources: [],
    },
    gm_model: {
      id: "00000000-0000-0000-0000-00000000gm01",
      engagement_type: "staff_aug",
      revenue_us: "180000",
      revenue_india: null,
      resource_line_count: 1,
    },
    floors: {
      us_pass: true,
      india_pass: true,
      requires_ceo: false,
      failing: [],
      gm_us: "0.42",
      gm_india: null,
      gm_blended: "0.42",
    },
    approvers: {
      delivery: {
        user_id: "00000000-0000-0000-0000-0000000000d1",
        source: "owner_row",
        business_unit: null,
      },
      hr: {
        user_id: "00000000-0000-0000-0000-0000000000h1",
        source: "owner_row",
        business_unit: null,
      },
      finance: {
        user_id: "00000000-0000-0000-0000-0000000000f1",
        source: "owner_row",
        business_unit: null,
      },
      legal: {
        user_id: "00000000-0000-0000-0000-0000000000l1",
        source: "owner_row",
        business_unit: null,
      },
    },
    projected_tasks: [],
    needs_you: [],
    ceo_gate: { will_trigger: false },
    ...overrides,
  };
}

function belowFloorPayload(): SowConfirmationPayload {
  return makePayload({
    floors: {
      us_pass: false,
      india_pass: true,
      requires_ceo: true,
      failing: ["us"],
      gm_us: "0.28",
      gm_india: "0.58",
      gm_blended: "0.32",
    },
    ceo_gate: {
      will_trigger: true,
      brief: { rationale: null },
    },
  });
}

function ambiguousEngagementPayload(): SowConfirmationPayload {
  return makePayload({
    engagement: {
      primary: { type: "fixed_price", confidence: 0.62 },
      secondary: { type: "tm", confidence: 0.31 },
      rule_matched: null,
      auto_confirm: false,
    },
    needs_you: [
      {
        field: "engagement_type",
        reason:
          "classifier confidence below threshold — pick between fixed_price and tm",
      },
    ],
  });
}

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function renderStudio(opportunityId: string | null = OPP) {
  const initial = opportunityId
    ? `/sows/new?opportunityId=${opportunityId}`
    : "/sows/new";
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/sows/new" element={<SowStudioPage />} />
        <Route
          path="/sows/:id/approvals"
          element={<div data-testid="approvals-landing">Approvals page</div>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Suite
// ---------------------------------------------------------------------------

describe("SowStudioPage — confirmation screen", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the confirmation screen from a mocked getSowConfirmation payload", async () => {
    vi.spyOn(apiClient, "getSowConfirmation").mockResolvedValue(makePayload());
    renderStudio();

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /Confirm SOW/i }),
      ).toBeInTheDocument();
    });
    expect(screen.getAllByText(/Confirmation, not entry/i).length).toBeGreaterThan(0);
    // Sections rendered by id.
    expect(document.getElementById("section-source")).not.toBeNull();
    expect(document.getElementById("section-scope")).not.toBeNull();
    expect(document.getElementById("section-ratecard")).not.toBeNull();
    expect(document.getElementById("section-staffing")).not.toBeNull();
    expect(document.getElementById("section-approvers")).not.toBeNull();
    expect(document.getElementById("section-needs-you")).not.toBeNull();
    // The scope value the extractor pulled is present as text.
    expect(
      screen.getByText(/Client signoff per milestone/i),
    ).toBeInTheDocument();
  });

  it("every field row carries a provenance chip", async () => {
    vi.spyOn(apiClient, "getSowConfirmation").mockResolvedValue(makePayload());
    renderStudio();

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Confirm SOW/i })).toBeInTheDocument();
    });

    // Field rows are addressable via `data-testid="field-row-<key>"`.
    const rows = document.querySelectorAll("[data-testid^='field-row-']");
    expect(rows.length).toBeGreaterThan(0);
    for (const row of Array.from(rows)) {
      const chip = row.querySelector("[data-testid^='provenance-']");
      expect(chip).not.toBeNull();
    }
  });

  it("has zero blank rows on open for a well-formed SOW", async () => {
    vi.spyOn(apiClient, "getSowConfirmation").mockResolvedValue(makePayload());
    renderStudio();

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Confirm SOW/i })).toBeInTheDocument();
    });
    // A "blank on open" row is any FieldRow with data-populated="false".
    const blanks = document.querySelectorAll(
      "[data-testid^='field-row-'][data-populated='false']",
    );
    expect(blanks.length).toBe(0);
  });

  it("disables Submit when needs_you.length > 0 and enables it when empty", async () => {
    // Empty needs_you: enabled.
    vi.spyOn(apiClient, "getSowConfirmation").mockResolvedValueOnce(makePayload());
    const { unmount } = renderStudio();
    await waitFor(() => {
      expect(screen.getByTestId("confirmation-submit")).toBeInTheDocument();
    });
    expect(screen.getByTestId("confirmation-submit")).not.toBeDisabled();
    expect(screen.getByTestId("needs-you-empty")).toBeInTheDocument();
    unmount();

    // A needs_you entry disables the button.
    vi.spyOn(apiClient, "getSowConfirmation").mockResolvedValueOnce(
      makePayload({
        needs_you: [
          { field: "signatories", reason: "extracted value missing" },
        ],
      }),
    );
    renderStudio();
    await waitFor(() => {
      expect(screen.getByTestId("confirmation-submit")).toBeInTheDocument();
    });
    expect(screen.getByTestId("confirmation-submit")).toBeDisabled();
    expect(
      screen.getByTestId("needs-you-item-signatories"),
    ).toBeInTheDocument();
  });

  it("submits via submitSowConfirmation and navigates on success", async () => {
    vi.spyOn(apiClient, "getSowConfirmation").mockResolvedValue(makePayload());
    const submitSpy = vi
      .spyOn(apiClient, "submitSowConfirmation")
      .mockResolvedValue(makePayload());

    renderStudio();

    await waitFor(() => {
      expect(screen.getByTestId("confirmation-submit")).toBeInTheDocument();
    });
    const btn = screen.getByTestId("confirmation-submit");
    await userEvent.click(btn);

    await waitFor(() => {
      expect(submitSpy).toHaveBeenCalledWith(OPP);
    });
    await waitFor(() => {
      expect(screen.getByTestId("approvals-landing")).toBeInTheDocument();
    });
  });

  it("shows the two-candidate chooser when classifier confidence is low", async () => {
    vi.spyOn(apiClient, "getSowConfirmation").mockResolvedValue(
      ambiguousEngagementPayload(),
    );
    renderStudio();

    await waitFor(() => {
      expect(screen.getByTestId("engagement-chooser")).toBeInTheDocument();
    });
    expect(
      screen.getByTestId("engagement-pick-fixed_price"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("engagement-pick-tm")).toBeInTheDocument();
    // Submit is blocked because engagement_type is in needs_you.
    expect(screen.getByTestId("confirmation-submit")).toBeDisabled();
  });

  it("shows CEO gate step in hold state with 'Will trigger' when below-floor", async () => {
    vi.spyOn(apiClient, "getSowConfirmation").mockResolvedValue(
      belowFloorPayload(),
    );
    renderStudio();

    await waitFor(() => {
      expect(screen.getByTestId("gate-step-ceo")).toBeInTheDocument();
    });
    const gate = screen.getByTestId("gate-step-ceo");
    expect(gate.getAttribute("data-state")).toBe("hold");
    expect(gate.textContent).toMatch(/Will trigger/i);
    expect(screen.getByTestId("ceo-will-trigger")).toBeInTheDocument();
  });

  it("renders the upload panel when no opportunity id is present", async () => {
    renderStudio(null);
    expect(
      screen.getByRole("heading", { name: /^New SOW$/ }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("upload-submit")).toBeInTheDocument();
    // No confirmation call was made.
    expect(screen.queryByTestId("confirmation-submit")).toBeNull();
  });

  it("surfaces an ErrorState when the confirmation loader throws", async () => {
    vi.spyOn(apiClient, "getSowConfirmation").mockRejectedValue(
      new Error("boom"),
    );
    renderStudio();
    await waitFor(() => {
      expect(
        screen.getByText(/We couldn't load the confirmation package/i),
      ).toBeInTheDocument();
    });
  });

  it("flips a field's provenance to manual when the reviewer overrides", async () => {
    vi.spyOn(apiClient, "getSowConfirmation").mockResolvedValue(makePayload());
    renderStudio();

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Confirm SOW/i })).toBeInTheDocument();
    });

    // The signatories row is not blank; open the editor, edit, save.
    const change = screen.getByTestId("field-change-signatories");
    await userEvent.click(change);
    const input = screen.getByTestId("field-edit-signatories");
    await userEvent.clear(input);
    await userEvent.type(input, "R. Kumar (Northstar); A. Smith (DealGate)");
    await userEvent.click(screen.getByTestId("field-save-signatories"));

    const row = screen.getByTestId("field-row-signatories");
    const chip = row.querySelector("[data-manual='true']");
    expect(chip).not.toBeNull();
  });
});
