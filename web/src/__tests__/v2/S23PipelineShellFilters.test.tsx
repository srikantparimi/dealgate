// S23-PL2 F7 · the filter toolbar and its dialogs: search, status, deal owner
// (Opportunities) / account owner (Clients), business unit with regions and the
// US note, the date dialog with the prototype's presets, more filters. Every
// active filter is a removable chip; "Reset all"; F17: Escape closes a dialog
// and focus returns to the control that opened it.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as appConfig from "../../api/appConfig";
import * as api from "../../api/client";
import * as wsApi from "../../api/pipelineWorkspace";
import type { Workspace } from "../../api/pipelineWorkspace";
import { PipelinePage } from "../../pages/v2/Pipeline";
import { answerFor, currentParams, populated, renderAt, SOW_STATES } from "./S23PipelineShellFixtures";

vi.mock("../../pages/v2/pipeline/RecordsPanel", async () => ({
  RecordsPanel: (await import("./S23PipelineShellFakes")).FakeRecordsPanel,
}));
vi.mock("../../pages/v2/pipeline/DealPreview", async () => ({
  DealPreview: (await import("./S23PipelineShellFakes")).FakeDealPreview,
}));
vi.mock("../../pages/v2/pipeline/ClientPreview", async () => ({
  ClientPreview: (await import("./S23PipelineShellFakes")).FakeClientPreview,
}));

const GROUPS = [
  { id: "group-q4", name: "Q4 priorities", deal_ids: ["deal-1", "deal-2", "deal-3", "deal-4", "deal-5", "deal-6"] },
  { id: "group-sa", name: "Strategic accounts", deal_ids: ["deal-7", "deal-8", "deal-9", "deal-10"] },
];

function serve(base: Workspace) {
  vi.spyOn(wsApi, "getWorkspace").mockImplementation(async (query) => answerFor(query, base));
}

beforeEach(() => {
  vi.spyOn(api, "getMe").mockResolvedValue({ id: "user-1", email: "e2e@example.com", name: "E2E", groups: ["Sales"] });
  vi.spyOn(appConfig, "useAppConfig").mockReturnValue({ hubspotPortalId: "1234567", loading: false });
  vi.spyOn(wsApi, "listWorkspaceViews").mockResolvedValue([]);
  vi.spyOn(wsApi, "listWorkspaceGroups").mockResolvedValue(GROUPS);
  serve(populated());
});

afterEach(() => vi.restoreAllMocks());

const params = () => currentParams(screen.getByTestId);
const toolbar = () => screen.getByRole("region", { name: "Pipeline filters" });
async function ready() {
  await screen.findByRole("region", { name: "Pipeline summary" });
  await waitFor(() => expect(within(toolbar()).getByRole("button", { name: "Date" })).toBeEnabled());
}
async function openDialog(button: string | RegExp, title: string) {
  fireEvent.click(within(toolbar()).getByRole("button", { name: button }));
  return screen.findByRole("dialog", { name: title });
}

describe("F7 · the toolbar", () => {
  it("offers search, status with the prototype's five choices, and the four filter buttons", async () => {
    renderAt(<PipelinePage />);
    await ready();
    const bar = within(toolbar());
    const search = bar.getByRole("searchbox", { name: "Search deals, clients, owners or next actions" });
    expect(search).toHaveAttribute("placeholder", "Search deals, clients, owners or next actions…");
    const status = bar.getByRole("combobox", { name: "Deal status" });
    expect(within(status).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Open",
      "All statuses",
      "Closed won",
      "Closed lost",
      "On hold only",
    ]);
    expect(bar.getByRole("button", { name: "Deal owner" })).toBeInTheDocument();
    expect(bar.getByRole("button", { name: "Business unit" })).toBeInTheDocument();
    expect(bar.getByRole("button", { name: "Date" })).toBeInTheDocument();
    expect(bar.getByRole("button", { name: "More filters" })).toBeInTheDocument();
  });

  it("search goes into the URL as a chip; removing the chip empties the box", async () => {
    renderAt(<PipelinePage />);
    await ready();
    const search = within(toolbar()).getByRole("searchbox");
    fireEvent.change(search, { target: { value: "Bank" } });
    await waitFor(() => expect(params().get("q")).toBe("Bank"));
    fireEvent.click(screen.getByRole("button", { name: "Remove Search: Bank" }));
    await waitFor(() => expect(params().get("q")).toBeNull());
    expect(search).toHaveValue("");
  });

  it("the status chip's × means All statuses", async () => {
    renderAt(<PipelinePage />, "/pipeline?status=hold");
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "Remove On hold only" }));
    await waitFor(() => expect(params().get("status")).toBe("all"));
  });
});

describe("F7 · owner filters", () => {
  it("Deal owner: names, then No deal owner and Former HubSpot user; applies, shows chips, and a chip removes one", async () => {
    renderAt(<PipelinePage />);
    await ready();
    const dialog = await openDialog("Deal owner", "Filter by deal owner");
    const d = within(dialog);
    expect(d.getByText("Precise filters")).toBeInTheDocument();
    expect(dialog).toHaveTextContent(
      "Select one or more. Choices within a filter combine with OR; different filters combine with AND.",
    );
    expect(d.getAllByRole("checkbox").map((c) => document.querySelector(`label[for="${c.id}"]`)?.textContent)).toEqual([
      "Srikanth Parimi",
      "Janice Krpan",
      "Shawnna DelHierro",
      "Michael Holman",
      "No deal owner",
      "Former HubSpot user",
    ]);
    fireEvent.click(d.getByRole("checkbox", { name: "Janice Krpan" }));
    fireEvent.click(d.getByRole("checkbox", { name: "Former HubSpot user" }));
    fireEvent.click(d.getByRole("button", { name: "Apply filter" }));
    await waitFor(() => expect(params().getAll("owner")).toEqual(["owner-jk", "former"]));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(within(toolbar()).getByRole("button", { name: "Deal owner · 2" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove Deal owner: Janice Krpan" }));
    await waitFor(() => expect(params().getAll("owner")).toEqual(["former"]));
    expect(screen.getByRole("button", { name: "Remove Deal owner: Former HubSpot user" })).toBeInTheDocument();

    const again = await openDialog("Deal owner · 1", "Filter by deal owner");
    expect(within(again).getByRole("checkbox", { name: "Former HubSpot user" })).toBeChecked();
    fireEvent.click(within(again).getByRole("button", { name: "Clear this filter" }));
    await waitFor(() => expect(params().getAll("owner")).toEqual([]));
  });

  it("Account owner on the Clients tab: no former option; No account owner reads 'Not assigned' as a chip", async () => {
    renderAt(<PipelinePage />, "/pipeline?tab=clients");
    await ready();
    expect(within(toolbar()).queryByRole("button", { name: "Deal owner" })).toBeNull();
    const dialog = await openDialog("Account owner", "Filter by account owner");
    expect(within(dialog).queryByRole("checkbox", { name: "Former HubSpot user" })).toBeNull();
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "No account owner" }));
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Michael Holman" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Apply filter" }));
    await waitFor(() => expect(params().getAll("account_owner")).toEqual(["none", "owner-mh"]));
    expect(screen.getByRole("button", { name: "Remove Account owner: Michael Holman" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove Account owner: Not assigned" }));
    await waitFor(() => expect(params().getAll("account_owner")).toEqual(["owner-mh"]));
  });
});

describe("F7 · business unit", () => {
  it("lists each business unit with its region and the US note; applies and removes by chip", async () => {
    renderAt(<PipelinePage />);
    await ready();
    const dialog = await openDialog("Business unit", "Filter by business unit");
    const rows = within(dialog).getAllByRole("checkbox").map((c) => document.querySelector(`label[for="${c.id}"]`)?.textContent);
    expect(rows).toEqual(["ST21US", "IT AvalonUS", "Retro RabbitSouth Africa"]);
    expect(dialog).toHaveTextContent(
      "US covers two different business units, ST21 and IT Avalon. They are mapped from the HubSpot region value (Settings → Business units).",
    );
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /^IT Avalon/ }));
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /^Retro Rabbit/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Apply filter" }));
    await waitFor(() => expect(params().getAll("bu")).toEqual(["IT Avalon", "Retro Rabbit"]));
    expect(within(toolbar()).getByRole("button", { name: "Business unit · 2" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove BU: Retro Rabbit (South Africa)" }));
    await waitFor(() => expect(params().getAll("bu")).toEqual(["IT Avalon"]));
    expect(screen.getByRole("button", { name: "Remove BU: IT Avalon (US)" })).toBeInTheDocument();
  });

  it("offers Unmapped region while the list holds a deal with an unmapped HubSpot region", async () => {
    serve(populated({ unmapped_regions: 1 }));
    renderAt(<PipelinePage />);
    await ready();
    const dialog = await openDialog("Business unit", "Filter by business unit");
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Unmapped region" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Apply filter" }));
    await waitFor(() => expect(params().getAll("bu")).toEqual(["unmapped"]));
    expect(screen.getByRole("button", { name: "Remove BU: Unmapped region" })).toBeInTheDocument();
  });
});

describe("F7 · the date dialog", () => {
  it("has the prototype's fields and presets, refuses a reversed custom range, and applies a custom range", async () => {
    renderAt(<PipelinePage />);
    await ready();
    const dialog = await openDialog("Date", "Choose the date that matters");
    const d = within(dialog);
    expect(dialog).toHaveTextContent("Calendar dates. Today is Oct 14, 2026 (America/Los_Angeles).");
    expect(within(d.getByRole("combobox", { name: "Date field" })).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Expected close",
      "Created",
      "Last activity",
    ]);
    expect(within(d.getByRole("combobox", { name: "Period" })).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Any date",
      "Before today",
      "Next 7 days",
      "Next 30 days",
      "Next 90 days",
      "Last 7 days",
      "Last 30 days",
      "Last 90 days",
      "This month",
      "This quarter",
      "Custom range",
    ]);
    expect(dialog).toHaveTextContent(
      "From / Through apply with Custom range. “Next” periods suit Expected close; “Last” periods suit Created and Last activity.",
    );
    fireEvent.change(d.getByRole("combobox", { name: "Period" }), { target: { value: "custom" } });
    fireEvent.change(d.getByLabelText("From"), { target: { value: "2026-10-20" } });
    fireEvent.change(d.getByLabelText("Through"), { target: { value: "2026-10-01" } });
    fireEvent.click(d.getByRole("button", { name: "Apply date filter" }));
    expect(d.getByRole("alert")).toHaveTextContent("The start date must be on or before the end date.");
    expect(screen.getByRole("dialog", { name: "Choose the date that matters" })).toBeInTheDocument();
    expect(params().get("date_preset")).toBeNull();

    fireEvent.change(d.getByLabelText("From"), { target: { value: "2026-10-01" } });
    fireEvent.change(d.getByLabelText("Through"), { target: { value: "2026-10-31" } });
    fireEvent.click(d.getByRole("button", { name: "Apply date filter" }));
    await waitFor(() => expect(params().get("date_preset")).toBe("custom"));
    expect(params().get("date_field")).toBe("close");
    expect(params().get("date_from")).toBe("2026-10-01");
    expect(params().get("date_to")).toBe("2026-10-31");
    fireEvent.click(screen.getByRole("button", { name: "Remove Expected close: Oct 1 to Oct 31" }));
    await waitFor(() => expect(params().get("date_preset")).toBeNull());
    expect(params().get("date_from")).toBeNull();
  });

  it("a preset on another date field shows as its chip", async () => {
    renderAt(<PipelinePage />);
    await ready();
    const dialog = await openDialog("Date", "Choose the date that matters");
    fireEvent.change(within(dialog).getByRole("combobox", { name: "Date field" }), { target: { value: "created" } });
    fireEvent.change(within(dialog).getByRole("combobox", { name: "Period" }), { target: { value: "last90" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Apply date filter" }));
    await waitFor(() => expect(params().get("date_preset")).toBe("last90"));
    expect(params().get("date_field")).toBe("created");
    expect(screen.getByRole("button", { name: "Remove Created: last 90 days" })).toBeInTheDocument();
  });
});

describe("F7 · more filters", () => {
  it("offers SOW (the nine real states), attention, missing information, group and watching; each chip removes its filter", async () => {
    renderAt(<PipelinePage />);
    await ready();
    const dialog = await openDialog("More filters", "More ways to focus");
    const d = within(dialog);
    expect(within(d.getByRole("combobox", { name: "SOW state" })).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Any SOW state",
      "Pending approval (in review or CEO exception)",
      ...SOW_STATES.map((s) => s.label),
    ]);
    expect(within(d.getByRole("combobox", { name: "Attention" })).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Any attention state",
      "Overdue next action",
      "Close date passed",
      "No deal owner",
      "14+ days inactive",
      "Pending approval",
      "Any flag",
    ]);
    expect(
      within(d.getByRole("combobox", { name: "Missing information" })).getAllByRole("option").map((o) => o.textContent),
    ).toEqual([
      "No missing-data filter",
      "Deal owner",
      "Close date",
      "Activity date",
      "Next action",
      // S24-AG1 F6: the state "Missing" (a net-new client past stage 1), not "no file".
      "NDA (net new, past stage 1)",
      "MSA (net new, past stage 1)",
      "NDA or MSA (net new, past stage 1)",
    ]);
    await waitFor(() =>
      expect(within(d.getByRole("combobox", { name: "Tracking group" })).getAllByRole("option").map((o) => o.textContent)).toEqual([
        "All groups",
        "Q4 priorities",
        "Strategic accounts",
      ]),
    );
    expect(dialog).toHaveTextContent("A saved view stores filters. A group stores deal membership. Watching is your personal follow list.");

    fireEvent.change(d.getByRole("combobox", { name: "SOW state" }), { target: { value: "pending" } });
    fireEvent.change(d.getByRole("combobox", { name: "Attention" }), { target: { value: "inactive" } });
    fireEvent.change(d.getByRole("combobox", { name: "Missing information" }), { target: { value: "nda" } });
    fireEvent.change(d.getByRole("combobox", { name: "Tracking group" }), { target: { value: "group-q4" } });
    fireEvent.click(d.getByRole("checkbox", { name: "Only opportunities I’m watching (5)" }));
    fireEvent.click(d.getByRole("button", { name: "Apply filters" }));

    await waitFor(() => expect(params().get("sow")).toBe("pending"));
    expect(params().get("attention")).toBe("inactive");
    expect(params().get("missing")).toBe("nda");
    expect(params().get("group")).toBe("group-q4");
    expect(params().get("watching")).toBe("true");
    expect(within(toolbar()).getByRole("button", { name: "More filters 5" })).toBeInTheDocument();

    for (const [chip, key] of [
      ["SOW: pending approval", "sow"],
      ["Attention: 14d+ inactive", "attention"],
      ["Missing: NDA (net new, past stage 1)", "missing"],
      ["Group: Q4 priorities", "group"],
      ["Watching", "watching"],
    ]) {
      fireEvent.click(screen.getByRole("button", { name: `Remove ${chip}` }));
      await waitFor(() => expect(params().get(key!)).toBeNull());
    }
    expect(within(toolbar()).getByRole("button", { name: "More filters" })).toBeInTheDocument();
  });

  it("a single SOW state shows its label as the chip", async () => {
    renderAt(<PipelinePage />, "/pipeline?sow=in_review_finance_legal&missing=agreements&attention=past_close");
    await ready();
    expect(screen.getByRole("button", { name: "Remove SOW: In review · finance/legal" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Missing: NDA or MSA (net new, past stage 1)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Attention: close date passed" })).toBeInTheDocument();
  });
});

describe("F7 · Reset all and F17 · dialogs", () => {
  it("Reset all clears every filter and keeps tab, layout, sort and page size", async () => {
    renderAt(
      <PipelinePage />,
      "/pipeline?tab=clients&layout=board&sort=close&page_size=50&page=3&status=won&bu=ST21&q=pod&watching=true&include_unmatched_clients=true",
    );
    await ready();
    expect(screen.getByRole("button", { name: "Remove Including clients without matching deals" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reset all" }));
    await waitFor(() => expect(params().get("status")).toBe("open"));
    expect([...params().keys()].sort()).toEqual(["layout", "page_size", "sort", "status", "tab"]);
    expect(params().get("tab")).toBe("clients");
    expect(params().get("layout")).toBe("board");
    expect(params().get("sort")).toBe("close");
    expect(params().get("page_size")).toBe("50");
  });

  it("the records' empty-state 'Reset filters' is the same Reset all", async () => {
    renderAt(<PipelinePage />, "/pipeline?status=lost&q=nothing&sort=name");
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "fake: reset filters" }));
    await waitFor(() => expect(params().get("status")).toBe("open"));
    expect(params().get("q")).toBeNull();
    expect(params().get("sort")).toBe("name");
  });

  it("Escape closes a filter dialog without applying it, and focus returns to its button", async () => {
    renderAt(<PipelinePage />);
    await ready();
    const date = within(toolbar()).getByRole("button", { name: "Date" });
    date.focus();
    fireEvent.click(date);
    const dialog = await screen.findByRole("dialog", { name: "Choose the date that matters" });
    fireEvent.change(within(dialog).getByRole("combobox", { name: "Period" }), { target: { value: "next7" } });
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(date).toHaveFocus();
    expect(params().get("date_preset")).toBeNull();
  });

  it("every control in a dialog has a label (no unnamed inputs)", async () => {
    renderAt(<PipelinePage />);
    await ready();
    for (const [button, title] of [
      ["Deal owner", "Filter by deal owner"],
      ["Business unit", "Filter by business unit"],
      ["Date", "Choose the date that matters"],
      ["More filters", "More ways to focus"],
    ]) {
      const dialog = await openDialog(button!, title!);
      for (const role of ["checkbox", "combobox", "textbox", "button"] as const) {
        for (const control of within(dialog).queryAllByRole(role)) expect(control).toHaveAccessibleName();
      }
      fireEvent.keyDown(dialog, { key: "Escape" });
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    }
  });
});
