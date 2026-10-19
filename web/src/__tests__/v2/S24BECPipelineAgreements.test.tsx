// S24-AG1 F6 (lane BE-C) · the Pipeline's NDA and MSA tags and its "Agreement gaps" card on the
// shared agreement states: the seven states with the prototype's wording and the kit's tones, the
// kind before each tag (both share one cell), nothing for a deal with no client, and the gap card's
// note and drill (clients that need attention, every status).
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { DocState } from "../../api/agreements";
import type { Agreements, WorkspaceMetrics } from "../../api/pipelineWorkspace";
import { AGREEMENT_GAP_NOTE, MetricCards } from "../../pages/v2/pipeline/MetricCards";
import { AgreementTags, agreementFilesText } from "../../pages/v2/pipeline/tags";

const STATES: [DocState, string, string][] = [
  ["client", "✓ Client copy", "bg-success-surface"],
  ["standard", "✓ Standard copy", "bg-primary-subtle"],
  ["covered", "✓ Marked covered", "bg-success-surface"],
  ["missing", "Missing", "bg-danger-surface"],
  ["due_later", "Due at stage 2", "bg-warning-surface"],
  ["not_needed", "Not needed now", "bg-surface-sunken"],
  ["existing_none", "Existing · none attached", "bg-surface-sunken"],
];

function tags(agreements: Agreements) {
  const { container } = render(<AgreementTags agreements={agreements} />);
  return container;
}

function tagAfter(kind: "NDA" | "MSA"): HTMLElement {
  const tag = screen.getByText(kind, { selector: "span" }).nextElementSibling;
  if (!(tag instanceof HTMLElement)) throw new Error(`no tag after ${kind}`);
  return tag;
}

describe("Pipeline NDA / MSA tags (F6)", () => {
  it.each(STATES)("state %s reads %s in its tone", (state, text, tone) => {
    tags({ nda_on_file: false, msa_on_file: false, nda_state: state, msa_state: "missing" });
    expect(tagAfter("NDA")).toHaveTextContent(text);
    expect(tagAfter("NDA").className).toContain(tone);
    // The tag text is the shared map's, never the old on-file wording.
    expect(screen.queryByText(/on file|NDA missing|MSA missing/)).toBeNull();
  });

  it("names each kind before its tag, NDA first", () => {
    const container = tags({ nda_on_file: true, msa_on_file: false, nda_state: "standard", msa_state: "due_later" });
    expect(container).toHaveTextContent("NDA✓ Standard copyMSADue at stage 2");
  });

  it("shows nothing for a deal with no client (no state), and nothing when an older API sends no state", () => {
    expect(tags({ nda_on_file: false, msa_on_file: false, nda_state: null, msa_state: null })).toBeEmptyDOMElement();
    expect(tags({ nda_on_file: true, msa_on_file: true })).toBeEmptyDOMElement();
  });

  it("keeps the preview's files line on files held (a client or standard copy; a mark is not a file)", () => {
    expect(agreementFilesText({ nda_on_file: true, msa_on_file: false, nda_state: "standard", msa_state: "covered" })).toBe("NDA");
    expect(agreementFilesText({ nda_on_file: false, msa_on_file: false, nda_state: "missing", msa_state: "covered" })).toBe(
      "None on file",
    );
  });
});

const DRILL = { tab: "clients", status: "all", missing: "agreements", include_unmatched_clients: false } as const;

function metrics(gaps: number): WorkspaceMetrics {
  return {
    open_deals: { value: 12, accounts: 5, drill: { tab: "deals", status: "open" } },
    open_value_usd: { value: "1075000.00", includes_on_hold: 2, deals: 12, drill: { tab: "deals", status: "open" } },
    closing_this_month: { value: 6, value_usd: "855000.00", drill: { tab: "deals", status: "open" } },
    overdue_next_actions: { value: 2, with_next_action: 6, drill: { tab: "deals", attention: "overdue" } },
    pending_approvals: { value: 3, drill: { tab: "deals", sow: "pending" } },
    agreement_gap_clients: { value: gaps, clients_total: 6, any_agreement_files: true, drill: { ...DRILL } },
  };
}

describe("Pipeline Agreement gaps card (F6 / B10)", () => {
  it("counts the clients that need attention with the NDA & MSA page's note, and no denominator", () => {
    render(<MetricCards metrics={metrics(3)} onDrill={vi.fn()} />);
    const card = within(screen.getByRole("region", { name: "Pipeline summary" })).getByRole("button", {
      name: /^Agreement gaps/,
    });
    expect(card).toHaveTextContent(`Agreement gaps↗3${AGREEMENT_GAP_NOTE}`);
    expect(AGREEMENT_GAP_NOTE).toBe("Net new, past stage 1, NDA or MSA missing");
    expect(card).not.toHaveTextContent(/of \d+ client|no agreement files uploaded yet|need attention/);
  });

  it("opens the server's drill: the clients tab, every status, missing = agreements", () => {
    const onDrill = vi.fn();
    render(<MetricCards metrics={metrics(3)} onDrill={onDrill} />);
    fireEvent.click(screen.getByRole("button", { name: /^Agreement gaps/ }));
    expect(onDrill).toHaveBeenCalledWith(DRILL);
  });
});
