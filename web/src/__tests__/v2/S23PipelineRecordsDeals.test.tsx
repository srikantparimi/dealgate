// S23-PL2 F8/F13/F15/F17 · the deals list: columns, every tag state of spec §3
// with tonight's data and populated data, owner states, stars, selection, and
// HubSpot strings rendered as text.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { DealRow } from "../../api/pipelineWorkspace";
import { RecordsPanel, type RecordsPanelProps } from "../../pages/v2/pipeline/RecordsPanel";
import {
  INJECTION_CLIENT,
  INJECTION_TITLE,
  deal,
  overdueDeal,
  reviewDeal,
  urlState,
  wonDeal,
  workspace,
} from "./S23PipelineRecordsFixtures";

function renderPanel(rows: DealRow[], overrides: Partial<RecordsPanelProps> = {}) {
  const props: RecordsPanelProps = {
    workspace: workspace({ rows }),
    loading: false,
    error: null,
    state: urlState(),
    onStateChange: vi.fn(),
    onShowStageInList: vi.fn(),
    selected: new Set<string>(),
    onSelectedChange: vi.fn(),
    onOpenDeal: vi.fn(),
    onOpenClient: vi.fn(),
    onToggleWatch: vi.fn().mockResolvedValue(undefined),
    onWatchSelected: vi.fn().mockResolvedValue(undefined),
    onAddSelectedToGroup: vi.fn(),
    onOpenViewsPanel: vi.fn(),
    onResetFilters: vi.fn(),
    ...overrides,
  };
  const view = render(
    <MemoryRouter>
      <RecordsPanel {...props} />
    </MemoryRouter>,
  );
  return { props, ...view };
}

/** The table row (or phone card) that holds a deal title. */
function rowOf(title: string): HTMLElement {
  const row = screen.getByRole("button", { name: title }).closest("tr");
  if (!row) throw new Error(`no row for ${title}`);
  return row as HTMLElement;
}

describe("deals list columns (F8)", () => {
  it("has the select-page box and the seven columns of the spec, in order", () => {
    renderPanel([deal()]);
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent?.trim());
    expect(headers.slice(1)).toEqual([
      "Opportunity / client",
      "Sales stage",
      "Value / business unit",
      "Deal owner",
      "Close / activity",
      "SOW / agreements",
      "Next action",
    ]);
    expect(screen.getByRole("checkbox", { name: "Select current page" })).toBeInTheDocument();
  });

  it("shows tonight's first row the way staging looks tonight (D31 empty work columns)", () => {
    renderPanel([deal()]);
    const row = within(rowOf("Cloud modernization"));
    expect(row.getByRole("button", { name: "Vector Systems" })).toHaveTextContent("Vector Systems ↗");
    expect(row.getByText("No flags")).toBeInTheDocument();
    expect(row.getByText("6 · Contracting")).toBeInTheDocument();
    expect(row.getByText("$542k")).toBeInTheDocument();
    expect(row.getByText("IT Avalon")).toBeInTheDocument();
    expect(row.getByText("· US")).toBeInTheDocument();
    expect(row.getByText("SP")).toBeInTheDocument();
    expect(row.getByText("Srikanth")).toBeInTheDocument();
    expect(row.getByText("Dec 28")).toBeInTheDocument();
    expect(row.getByText("No activity recorded")).toBeInTheDocument();
    expect(row.getByText("No SOW")).toBeInTheDocument();
    expect(row.getByText("NDA missing")).toBeInTheDocument();
    expect(row.getByText("MSA missing")).toBeInTheDocument();
    expect(row.getByRole("button", { name: "Set next action" })).toHaveTextContent("Set next action →");
    const star = row.getByRole("button", { name: "Watch Cloud modernization" });
    expect(star).toHaveAttribute("aria-pressed", "false");
  });

  it("shows a populated row: overdue action, staffing note, next year's date", () => {
    renderPanel([overdueDeal()]);
    const row = within(rowOf("Quality engineering pod"));
    expect(row.getByText("Action overdue")).toBeInTheDocument();
    expect(row.getByText("3 · Fit gap analysis")).toBeInTheDocument();
    expect(row.getByText("$420k")).toBeInTheDocument();
    expect(row.getByText("· US · Staffing")).toBeInTheDocument();
    expect(row.getByText("Mar 15, 2027")).toBeInTheDocument();
    expect(row.getByRole("button", { name: "Confirm final commercial terms" })).toHaveTextContent(
      "Confirm final commercial terms →",
    );
    expect(row.getByText("Oct 13 · overdue")).toBeInTheDocument();
    expect(row.queryByRole("button", { name: "Set next action" })).not.toBeInTheDocument();
  });

  it("shows activity days, a pending SOW in the pending tone, and agreements on file", () => {
    renderPanel([reviewDeal()]);
    const row = within(rowOf("Application support"));
    expect(row.getByText("11d since activity")).toBeInTheDocument();
    const sow = row.getByText("In review · delivery/hr");
    expect(sow.className).toContain("bg-primary-subtle");
    expect(row.getByText("NDA on file").className).toContain("bg-success-surface");
    expect(row.getByText("MSA missing").className).toContain("bg-warning-surface");
    expect(row.getByText("MH")).toBeInTheDocument();
    expect(row.getByText("Michael")).toBeInTheDocument();
  });

  it("shows a closed won deal: green stage, former owner, signed SOW and a dash for next action", () => {
    renderPanel([wonDeal()]);
    const row = within(rowOf("Integration modernization"));
    expect(row.getByText("Closed won").className).toContain("bg-success-surface");
    expect(row.getByText("Former HubSpot user")).toBeInTheDocument();
    expect(row.getByText("ST21")).toBeInTheDocument();
    expect(row.getByText("Oct 2")).toBeInTheDocument();
    expect(row.getByText("56d since activity")).toBeInTheDocument();
    expect(row.getByText("Signed").className).toContain("bg-success-surface");
    expect(row.getByText("—")).toBeInTheDocument();
    expect(row.queryByRole("button", { name: "Set next action" })).not.toBeInTheDocument();
    expect(row.getByText("No flags")).toBeInTheDocument();
  });

  it("labels Hold as 'On hold' and still treats it as open", () => {
    renderPanel([deal({ title: "Observability service", stage_id: 9, stage_label: "On hold" })]);
    const row = within(rowOf("Observability service"));
    expect(row.getByText("On hold").className).toContain("bg-warning-surface");
    expect(row.queryByText(/9 ·/)).not.toBeInTheDocument();
    expect(row.getByRole("button", { name: "Set next action" })).toBeInTheDocument();
  });

  it("labels Closed lost in the danger tone", () => {
    renderPanel([deal({ title: "Lost deal", stage_id: 8, stage_label: "Closed lost" })]);
    expect(within(rowOf("Lost deal")).getByText("Closed lost").className).toContain("bg-danger-surface");
  });

  it("warns 'Not assigned' and flags 'No deal owner' only on open deals (B13)", () => {
    renderPanel([
      deal({ title: "Open no owner", deal_owner: { name: null, state: "none" }, flags: ["no_owner"] }),
      deal({ title: "Lost no owner", stage_id: 8, stage_label: "Closed lost", deal_owner: { name: null, state: "none" } }),
    ]);
    const open = within(rowOf("Open no owner"));
    expect(open.getByText("Not assigned").className).toContain("bg-warning-surface");
    expect(open.getByText("No deal owner")).toBeInTheDocument();
    const lost = within(rowOf("Lost no owner"));
    expect(lost.getByText("Not assigned").className).not.toContain("bg-warning-surface");
    expect(lost.queryByText("No deal owner")).not.toBeInTheDocument();
  });

  it("shows a passed close date, inactivity days, an unmapped region and a missing amount", () => {
    renderPanel([
      deal({
        title: "Late deal",
        close_date: "2026-10-09",
        last_activity_date: "2026-09-24",
        days_since_activity: 20,
        flags: ["close_passed", "inactive_14d"],
        business_unit: null,
        region: null,
        bu_unmapped: true,
        hubspot_region: "US - Other",
        amount: null,
      }),
    ]);
    const row = within(rowOf("Late deal"));
    expect(row.getByText("Oct 9 · passed")).toBeInTheDocument();
    expect(row.getByText("Close date passed")).toBeInTheDocument();
    expect(row.getByText("20d inactive")).toBeInTheDocument();
    expect(row.getByText("20d since activity")).toBeInTheDocument();
    expect(row.getByText("Unmapped region · US - Other")).toBeInTheDocument();
    expect(row.getByText("Not entered")).toBeInTheDocument();
  });

  it("says 'Not set' without a close date, 'No due date' without a due date, and shows the currency of a non-USD amount", () => {
    renderPanel([
      deal({
        title: "Euro deal",
        close_date: null,
        amount: "120000",
        currency: "EUR",
        next_action: { id: "a1", text: "Send revised estimate", due_on: null },
      }),
    ]);
    const row = within(rowOf("Euro deal"));
    expect(row.getByText("Not set")).toBeInTheDocument();
    expect(row.getByText("No due date")).toBeInTheDocument();
    expect(row.getByText("EUR 120k")).toBeInTheDocument();
  });

  it("shows an amount with no currency without '$', saying it has none; the USD basis line keeps '$'", () => {
    renderPanel([deal({ title: "Unpriced rollout", amount: "542000", currency: null })]);
    const row = within(rowOf("Unpriced rollout"));
    expect(row.getByText("542k · no currency")).toBeInTheDocument();
    expect(row.queryByText("$542k")).not.toBeInTheDocument();
    expect(screen.getByText(/· \$21\.60m · USD, unweighted ·/)).toBeInTheDocument();
  });

  it("adds '+N more' after the SOW tag when a deal has several SOWs (B6)", () => {
    renderPanel([
      reviewDeal({ title: "Three SOWs", sow_count: 3 }),
      reviewDeal({ title: "One SOW", sow_count: 1 }),
    ]);
    expect(within(rowOf("Three SOWs")).getByText("+2 more")).toBeInTheDocument();
    expect(within(rowOf("One SOW")).queryByText(/more$/)).not.toBeInTheDocument();
  });
});

describe("a deal without a client", () => {
  it("says 'No client' and offers no client link (never an empty link)", () => {
    renderPanel([deal({ title: "Standalone advisory", client: { id: null, name: null } })]);
    const row = screen.getByRole("row", { name: /Standalone advisory/ });
    expect(within(row).getByText("No client")).toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: /↗|^\s*$/ })).toBeNull();
  });
});

describe("deals list actions", () => {
  it("opens the deal from its title, its next action and 'Set next action', and the client from its link", () => {
    const tonight = deal();
    const populated = overdueDeal();
    const { props } = renderPanel([tonight, populated]);
    fireEvent.click(screen.getByRole("button", { name: "Cloud modernization" }));
    fireEvent.click(screen.getByRole("button", { name: "Set next action" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm final commercial terms" }));
    expect(props.onOpenDeal).toHaveBeenNthCalledWith(1, tonight);
    expect(props.onOpenDeal).toHaveBeenNthCalledWith(2, tonight);
    expect(props.onOpenDeal).toHaveBeenNthCalledWith(3, populated);
    fireEvent.click(screen.getByRole("button", { name: "Keystone Energy" }));
    expect(props.onOpenClient).toHaveBeenCalledWith({ id: populated.client.id, name: "Keystone Energy" });
  });

  it("toggles the star at once and hands the parent the state the user saw (F17 aria-pressed)", async () => {
    const d = deal();
    const { props } = renderPanel([d]);
    fireEvent.click(screen.getByRole("button", { name: "Watch Cloud modernization" }));
    const star = await screen.findByRole("button", { name: "Stop watching Cloud modernization" });
    expect(star).toHaveAttribute("aria-pressed", "true");
    expect(props.onToggleWatch).toHaveBeenCalledWith({ ...d, watching: false });
  });

  it("stops watching a watched deal", async () => {
    const d = deal({ watching: true });
    const { props } = renderPanel([d]);
    const star = screen.getByRole("button", { name: "Stop watching Cloud modernization" });
    expect(star).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(star);
    expect(await screen.findByRole("button", { name: "Watch Cloud modernization" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(props.onToggleWatch).toHaveBeenCalledWith({ ...d, watching: true });
  });

  it("puts the star back when the watch call fails", async () => {
    renderPanel([deal()], { onToggleWatch: vi.fn().mockRejectedValue(new Error("offline")) });
    fireEvent.click(screen.getByRole("button", { name: "Watch Cloud modernization" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Watch Cloud modernization" })).toHaveAttribute("aria-pressed", "false"),
    );
  });

  it("selects one row, the whole page, and clears the page (F13)", () => {
    const a = deal({ title: "Deal A" });
    const b = deal({ title: "Deal B" });
    const onSelectedChange = vi.fn();
    const first = renderPanel([a, b], { onSelectedChange });
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Deal A" }));
    expect(onSelectedChange).toHaveBeenLastCalledWith(new Set([a.id]));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select current page" }));
    expect(onSelectedChange).toHaveBeenLastCalledWith(new Set([a.id, b.id]));
    first.unmount();

    renderPanel([a, b], { onSelectedChange, selected: new Set([a.id]) });
    expect(screen.getByRole("checkbox", { name: "Select current page" })).toHaveAttribute("aria-checked", "mixed");
    expect(screen.getByRole("checkbox", { name: "Select Deal A" })).toHaveAttribute("aria-checked", "true");
  });

  it("clears the page when every row on it is selected, keeping selections from other pages", () => {
    const a = deal({ title: "Deal A" });
    const b = deal({ title: "Deal B" });
    const onSelectedChange = vi.fn();
    renderPanel([a, b], { onSelectedChange, selected: new Set([a.id, b.id, "other-page-deal"]) });
    const all = screen.getByRole("checkbox", { name: "Select current page" });
    expect(all).toHaveAttribute("aria-checked", "true");
    fireEvent.click(all);
    expect(onSelectedChange).toHaveBeenLastCalledWith(new Set(["other-page-deal"]));
  });
});

describe("HubSpot strings render as text (F15/T6)", () => {
  it("shows HTML and formula strings literally and creates no element from them", () => {
    const { container } = renderPanel([
      deal({ title: INJECTION_TITLE, client: { id: "c-x", name: INJECTION_CLIENT } }),
    ]);
    expect(screen.getByRole("button", { name: INJECTION_TITLE })).toHaveTextContent(INJECTION_TITLE);
    expect(screen.getByRole("button", { name: INJECTION_CLIENT })).toHaveTextContent(`${INJECTION_CLIENT} ↗`);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByRole("checkbox", { name: `Select ${INJECTION_TITLE}` })).toBeInTheDocument();
  });
});
