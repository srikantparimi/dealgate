// S23-PL2 F4 · six metric cards (copy, drill into the URL, card = list),
// F5 · the stage navigator (nine stages, status memory), F6 · focus views
// (counts from `focus`, the unlinked "My opportunities" hint).
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as appConfig from "../../api/appConfig";
import * as api from "../../api/client";
import * as wsApi from "../../api/pipelineWorkspace";
import type { Workspace } from "../../api/pipelineWorkspace";
import { PipelinePage } from "../../pages/v2/Pipeline";
import { answerFor, currentParams, populated, renderAt, stages, tonight } from "./S23PipelineShellFixtures";

vi.mock("../../pages/v2/pipeline/RecordsPanel", async () => ({
  RecordsPanel: (await import("./S23PipelineShellFakes")).FakeRecordsPanel,
}));
vi.mock("../../pages/v2/pipeline/DealPreview", async () => ({
  DealPreview: (await import("./S23PipelineShellFakes")).FakeDealPreview,
}));
vi.mock("../../pages/v2/pipeline/ClientPreview", async () => ({
  ClientPreview: (await import("./S23PipelineShellFakes")).FakeClientPreview,
}));

function serve(base: Workspace) {
  vi.spyOn(wsApi, "getWorkspace").mockImplementation(async (query) => answerFor(query, base));
}

beforeEach(() => {
  vi.spyOn(api, "getMe").mockResolvedValue({ id: "user-1", email: "e2e@example.com", name: "E2E", groups: ["Sales"] });
  vi.spyOn(appConfig, "useAppConfig").mockReturnValue({ hubspotPortalId: "1234567", loading: false });
  vi.spyOn(wsApi, "listWorkspaceViews").mockResolvedValue([]);
  vi.spyOn(wsApi, "listWorkspaceGroups").mockResolvedValue([]);
  serve(tonight());
});

afterEach(() => vi.restoreAllMocks());

const params = () => currentParams(screen.getByTestId);
const cardsRegion = async () => screen.findByRole("region", { name: "Pipeline summary" });
const card = (label: RegExp) =>
  within(screen.getByRole("region", { name: "Pipeline summary" })).getByRole("button", { name: label });

describe("F4 · metric cards", () => {
  it("shows the six cards with tonight's copy (no work data yet)", async () => {
    renderAt(<PipelinePage />);
    const region = await cardsRegion();
    const texts = within(region)
      .getAllByRole("button")
      .map((b) => b.textContent);
    expect(texts).toEqual([
      "Open deals↗10955 accounts",
      "Open value · USD↗$21.60mincludes 2 on hold · unweighted",
      "Closing this month↗15$2.68m proposed value",
      "Overdue next actions↗0No deal has a next action yet",
      "Pending approvals↗0Deals with a SOW in review or CEO exception",
      // S24-AG1 F6: the clients that need attention, with the NDA & MSA page's note.
      "Agreement gaps↗55Net new, past stage 1, NDA or MSA missing",
    ]);
  });

  it("shows the populated copy once next actions, SOWs and agreement files exist", async () => {
    serve(populated());
    renderAt(<PipelinePage />);
    const region = await cardsRegion();
    expect(within(region).getByRole("button", { name: /^Overdue next actions/ })).toHaveTextContent(
      "10of 37 deals with a next action",
    );
    expect(within(region).getByRole("button", { name: /^Pending approvals/ })).toHaveTextContent("11");
    expect(within(region).getByRole("button", { name: /^Agreement gaps/ })).toHaveTextContent(
      "33Net new, past stage 1, NDA or MSA missing",
    );
  });

  it("handles singulars and an empty population", async () => {
    const base = tonight();
    serve(
      tonight({
        metrics: {
          ...base.metrics,
          open_deals: { ...base.metrics.open_deals, value: 1, accounts: 1 },
          open_value_usd: { ...base.metrics.open_value_usd, value: "0", includes_on_hold: 0 },
          closing_this_month: { ...base.metrics.closing_this_month, value: 0, value_usd: "0" },
          overdue_next_actions: { ...base.metrics.overdue_next_actions, value: 1, with_next_action: 1 },
          agreement_gap_clients: { ...base.metrics.agreement_gap_clients, value: 0, clients_total: 1, any_agreement_files: true },
        },
      }),
    );
    renderAt(<PipelinePage />);
    await cardsRegion();
    expect(card(/^Open deals/)).toHaveTextContent("1 account");
    expect(card(/^Open value/)).toHaveTextContent("$0unweighted");
    expect(card(/^Closing this month/)).toHaveTextContent("$0 proposed value");
    expect(card(/^Overdue next actions/)).toHaveTextContent("of 1 deal with a next action");
    // S24-AG1: no denominator any more; zero clients need attention is a real zero.
    expect(card(/^Agreement gaps/)).toHaveTextContent("0Net new, past stage 1, NDA or MSA missing");
  });

  it.each([
    [/^Open deals/, { status: "open" }, "109 rows", "deals"],
    [/^Open value/, { status: "open" }, "109 rows", "deals"],
    [/^Closing this month/, { status: "open", date_field: "close", date_preset: "month" }, "15 rows", "deals"],
    [/^Overdue next actions/, { attention: "overdue" }, "10 rows", "deals"],
    [/^Pending approvals/, { sow: "pending" }, "11 rows", "deals"],
    [/^Agreement gaps/, { tab: "clients", missing: "agreements" }, "33 rows", "clients"],
  ])("%s: the click puts the card's drill in the URL and the list has the card's number", async (label, drill, rows, tab) => {
    serve(populated());
    renderAt(<PipelinePage />);
    await cardsRegion();
    fireEvent.click(card(label as RegExp));
    await waitFor(() => {
      for (const [key, value] of Object.entries(drill)) expect(params().get(key)).toBe(value);
    });
    await waitFor(() => expect(screen.getByTestId("records-total")).toHaveTextContent(rows as string));
    expect(screen.getByTestId("records-tab")).toHaveTextContent(tab as string);
    expect(wsApi.getWorkspace).toHaveBeenLastCalledWith(expect.objectContaining(drill), expect.anything());
  });

  it("a card keeps the stage selection and the other filters, so the list stays the card's population", async () => {
    serve(populated());
    renderAt(<PipelinePage />, "/pipeline?status=all&stage=4&status_before=open&bu=Retro+Rabbit");
    await cardsRegion();
    fireEvent.click(card(/^Overdue next actions/));
    await waitFor(() => expect(params().get("attention")).toBe("overdue"));
    expect(params().getAll("stage")).toEqual(["4"]);
    expect(params().getAll("bu")).toEqual(["Retro Rabbit"]);
  });
});

describe("F5 · the stage navigator", () => {
  it("shows all nine stages with count, short name, amount and a full label", async () => {
    const base = tonight();
    serve(tonight({ stages: base.stages.map((s) => (s.stage_id === 3 ? { ...s, deals_without_amount: 1 } : s)) }));
    renderAt(<PipelinePage />);
    const region = await screen.findByRole("region", { name: "HubSpot sales stages" });
    const buttons = within(region).getAllByRole("button");
    expect(buttons).toHaveLength(9);
    expect(region).toHaveTextContent("Sales stage navigator");
    expect(region).toHaveTextContent("All-status overview · select stages to filter in place");
    expect(buttons[0]).toHaveAccessibleName("1 · Initial Contact / Prospecting: 22 deals, $3,950,000 known value");
    expect(buttons[0]).toHaveTextContent("0122Prospecting$3.95m");
    expect(buttons[2]).toHaveTextContent("$3.61m + 1 no amount");
    expect(buttons[3]).toHaveAccessibleName("4 · Proposal: 19 deals, $3,058,944.14 known value");
    expect(buttons[8]).toHaveAccessibleName("Hold (open, paused): 2 deals, $344,500 known value");
    expect(buttons[8]).toHaveTextContent("HOLD2On hold$344.5k");
    buttons.forEach((b) => expect(b).toHaveAttribute("aria-pressed", "false"));
  });

  it("selecting stages sets All statuses and remembers Open; clearing the last stage restores it", async () => {
    renderAt(<PipelinePage />);
    const region = await screen.findByRole("region", { name: "HubSpot sales stages" });
    const proposal = within(region).getByRole("button", { name: /^4 · Proposal/ });
    fireEvent.click(proposal);
    await waitFor(() => expect(params().getAll("stage")).toEqual(["4"]));
    expect(params().get("status")).toBe("all");
    expect(params().get("status_before")).toBe("open");
    expect(within(region).getByRole("button", { name: /^4 · Proposal/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("combobox", { name: "Deal status" })).toHaveValue("all");
    // "All statuses" is shown, with nothing to remove.
    expect(screen.getByText("All statuses", { selector: "span" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove All statuses" })).toBeNull();

    fireEvent.click(within(region).getByRole("button", { name: /^Hold \(open, paused\)/ }));
    await waitFor(() => expect(params().getAll("stage")).toEqual(["4", "9"]));
    fireEvent.click(screen.getByRole("button", { name: "Remove 4 · Proposal" }));
    await waitFor(() => expect(params().getAll("stage")).toEqual(["9"]));
    expect(params().get("status")).toBe("all");

    fireEvent.click(within(region).getByRole("button", { name: /^Hold \(open, paused\)/ }));
    await waitFor(() => expect(params().getAll("stage")).toEqual([]));
    expect(params().get("status")).toBe("open");
    expect(screen.getByRole("button", { name: "Remove Status: Open (includes on hold)" })).toBeInTheDocument();
  });

  it("remembers Closed won the same way, and a status change clears the stages", async () => {
    renderAt(<PipelinePage />, "/pipeline?status=won");
    const region = await screen.findByRole("region", { name: "HubSpot sales stages" });
    fireEvent.click(within(region).getByRole("button", { name: /^2 · Qualification/ }));
    await waitFor(() => expect(params().get("status")).toBe("all"));
    fireEvent.click(within(region).getByRole("button", { name: /^2 · Qualification/ }));
    await waitFor(() => expect(params().get("status")).toBe("won"));

    fireEvent.click(within(region).getByRole("button", { name: /^5 · Negotiation/ }));
    await waitFor(() => expect(params().getAll("stage")).toEqual(["5"]));
    fireEvent.change(screen.getByRole("combobox", { name: "Deal status" }), { target: { value: "lost" } });
    await waitFor(() => expect(params().get("status")).toBe("lost"));
    expect(params().getAll("stage")).toEqual([]);
  });

  it("the board's 'Show all N in list' selects that stage (status memory included) and switches to the list", async () => {
    renderAt(<PipelinePage />, "/pipeline?layout=board&status=hold");
    await screen.findByRole("region", { name: "HubSpot sales stages" });
    fireEvent.click(screen.getByRole("button", { name: "fake: show stage 1 in list" }));
    await waitFor(() => expect(params().getAll("stage")).toEqual(["1"]));
    expect(params().get("layout")).toBeNull();
    expect(params().get("status")).toBe("all");
    expect(params().get("status_before")).toBe("hold");
    expect(screen.getByRole("button", { name: "Remove 1 · Initial Contact / Prospecting" })).toBeInTheDocument();
  });

  it("stage counts are drawn from the answer as is (all-status overview)", async () => {
    serve(tonight({ stages: stages().map((s) => ({ ...s, deals: s.stage_id === 1 ? 4 : s.deals })) }));
    renderAt(<PipelinePage />);
    const region = await screen.findByRole("region", { name: "HubSpot sales stages" });
    expect(within(region).getAllByRole("button")[0]).toHaveTextContent("014Prospecting");
  });
});

describe("F6 · focus views", () => {
  const sidebar = async () => screen.findByRole("complementary", { name: "Views and groups" });

  it("shows the five views with counts from `focus`; All open is highlighted by default", async () => {
    serve(populated());
    renderAt(<PipelinePage />);
    const aside = await sidebar();
    await waitFor(() => expect(within(aside).getByRole("button", { name: /^All open opportunities/ })).toHaveTextContent("109"));
    const names = ["All open opportunities109", "Closing this month15", "My opportunities33", "Needs attention36", "Watching5"];
    const buttons = names.map((n) => within(aside).getByRole("button", { name: n.replace(/\d+$/, (d) => ` ${d}`) }));
    expect(buttons.map((b) => b.textContent)).toEqual(names);
    expect(buttons[0]).toHaveAttribute("aria-pressed", "true");
    expect(buttons.slice(1).map((b) => b.getAttribute("aria-pressed"))).toEqual(["false", "false", "false", "false"]);
  });

  it("a view resets every filter, applies its preset and keeps tab, layout and sort", async () => {
    renderAt(<PipelinePage />, "/pipeline?bu=ST21&sort=name&q=pod&tab=clients&layout=board");
    const aside = await sidebar();
    fireEvent.click(within(aside).getByRole("button", { name: /^Needs attention/ }));
    await waitFor(() => expect(params().get("attention")).toBe("any"));
    expect(params().getAll("bu")).toEqual([]);
    expect(params().get("q")).toBeNull();
    expect(params().get("sort")).toBe("name");
    expect(params().get("tab")).toBe("clients");
    expect(params().get("layout")).toBe("board");
    expect(within(aside).getByRole("button", { name: /^Needs attention/ })).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(within(aside).getByRole("button", { name: /^My opportunities/ }));
    await waitFor(() => expect(params().get("mine")).toBe("true"));
    expect(params().get("attention")).toBeNull();
    expect(screen.getByRole("button", { name: "Remove My opportunities" })).toBeInTheDocument();

    fireEvent.click(within(aside).getByRole("button", { name: /^Closing this month/ }));
    await waitFor(() => expect(params().get("date_preset")).toBe("month"));
    expect(params().get("date_field")).toBe("close");
    expect(screen.getByRole("button", { name: "Remove Expected close: this month" })).toBeInTheDocument();

    fireEvent.click(within(aside).getByRole("button", { name: /^Watching/ }));
    await waitFor(() => expect(params().get("watching")).toBe("true"));
    expect(screen.getByRole("button", { name: "Remove Watching" })).toBeInTheDocument();

    // Any further filter change drops the highlight.
    fireEvent.change(screen.getByRole("combobox", { name: "Deal status" }), { target: { value: "all" } });
    await waitFor(() => expect(within(aside).getByRole("button", { name: /^Watching/ })).toHaveAttribute("aria-pressed", "false"));
  });

  it("without an owner link, My opportunities is disabled with the hint and no count", async () => {
    const base = tonight();
    serve(tonight({ focus: { ...base.focus, mine: null, mine_available: false } }));
    renderAt(<PipelinePage />);
    const aside = await sidebar();
    const mine = await within(aside).findByRole("button", { name: "My opportunities" });
    await waitFor(() => expect(mine).toBeDisabled());
    expect(mine).toHaveTextContent(/^My opportunities$/);
    expect(mine).toHaveAccessibleDescription("Your user is not linked to a HubSpot owner yet. An administrator can link it in Settings → People & access.");
  });
});
