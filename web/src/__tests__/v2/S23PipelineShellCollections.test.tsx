// S23-PL2 F12 · saved views and tracking groups (real and per user): open,
// save a second view, duplicate names, delete; groups: filter, create, add the
// selection. F13 (page part): watch selected / one deal. F14: export. F19:
// Create in HubSpot from the config portal id. F16 (page part): the views
// panel from the records' "Views & groups" button. Preview wiring (§3 seam).
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as appConfig from "../../api/appConfig";
import * as api from "../../api/client";
import * as wsApi from "../../api/pipelineWorkspace";
import type { SavedWorkspaceView } from "../../api/pipelineWorkspace";
import { PipelinePage } from "../../pages/v2/Pipeline";
import { answerFor, currentParams, populated, renderAt } from "./S23PipelineShellFixtures";

vi.mock("../../pages/v2/pipeline/RecordsPanel", async () => ({
  RecordsPanel: (await import("./S23PipelineShellFakes")).FakeRecordsPanel,
}));
vi.mock("../../pages/v2/pipeline/DealPreview", async () => ({
  DealPreview: (await import("./S23PipelineShellFakes")).FakeDealPreview,
}));
vi.mock("../../pages/v2/pipeline/ClientPreview", async () => ({
  ClientPreview: (await import("./S23PipelineShellFakes")).FakeClientPreview,
}));

const ST21_OPEN: SavedWorkspaceView = {
  id: "view-1",
  name: "ST21 open",
  tab: "deals",
  layout: "list",
  filters: { status: "open", bu: ["ST21"] },
};
const RR_CLOSING: SavedWorkspaceView = {
  id: "view-2",
  name: "Retro Rabbit · closing this month",
  tab: "deals",
  layout: "list",
  filters: { status: "open", bu: ["Retro Rabbit"], date_field: "close", date_preset: "month" },
};
const GROUPS = [
  { id: "group-q4", name: "Q4 priorities", deal_ids: ["deal-1", "deal-2", "deal-3", "deal-4", "deal-5", "deal-6"] },
  { id: "group-sa", name: "Strategic accounts", deal_ids: ["deal-7", "deal-8", "deal-9", "deal-10"] },
];

function me(groups: string[]) {
  vi.spyOn(api, "getMe").mockResolvedValue({ id: "user-1", email: "e2e@example.com", name: "E2E", groups });
}

beforeEach(() => {
  me(["Sales"]);
  vi.spyOn(appConfig, "useAppConfig").mockReturnValue({ hubspotPortalId: "1234567", loading: false });
  vi.spyOn(wsApi, "listWorkspaceViews").mockResolvedValue([ST21_OPEN]);
  vi.spyOn(wsApi, "listWorkspaceGroups").mockResolvedValue(GROUPS);
  vi.spyOn(wsApi, "getWorkspace").mockImplementation(async (query) => answerFor(query, populated()));
});

afterEach(() => vi.restoreAllMocks());

const params = () => currentParams(screen.getByTestId);
const sidebar = () => screen.getByRole("complementary", { name: "Views and groups" });
async function ready() {
  await screen.findByRole("region", { name: "Pipeline summary" });
  await within(sidebar()).findByRole("button", { name: "ST21 open" });
}

describe("F12 · saved views", () => {
  it("opening a saved view applies its filters, tab and layout (sort and page size stay) and says so", async () => {
    vi.mocked(wsApi.listWorkspaceViews).mockResolvedValue([ST21_OPEN, RR_CLOSING]);
    renderAt(<PipelinePage />, "/pipeline?q=old&sort=name&page_size=50&page=2");
    await ready();
    fireEvent.click(within(sidebar()).getByRole("button", { name: "Retro Rabbit · closing this month" }));
    await waitFor(() => expect(params().getAll("bu")).toEqual(["Retro Rabbit"]));
    expect(params().get("date_preset")).toBe("month");
    expect(params().get("q")).toBeNull();
    expect(params().get("page")).toBeNull();
    expect(params().get("sort")).toBe("name");
    expect(params().get("page_size")).toBe("50");
    expect(screen.getByRole("button", { name: "Remove BU: Retro Rabbit (South Africa)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Expected close: this month" })).toBeInTheDocument();
    expect(await screen.findByText("Opened saved view: Retro Rabbit · closing this month")).toBeInTheDocument();
  });

  it("saves a second view with the current filters, tab and layout, and lists it", async () => {
    const saved: SavedWorkspaceView = {
      id: "view-3",
      name: "Everything open",
      tab: "clients",
      layout: "board",
      filters: { status: "all", bu: ["ST21"] },
    };
    vi.mocked(wsApi.listWorkspaceViews).mockResolvedValueOnce([ST21_OPEN]).mockResolvedValue([ST21_OPEN, saved]);
    const create = vi.spyOn(wsApi, "createWorkspaceView").mockResolvedValue(saved);
    renderAt(<PipelinePage />, "/pipeline?status=all&bu=ST21&tab=clients&layout=board");
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "Save view ＋" }));
    const dialog = await screen.findByRole("dialog", { name: "Save your working view" });
    expect(dialog).toHaveAccessibleDescription("Keeps the current filters, tab and layout together.");
    const name = within(dialog).getByRole("textbox", { name: "View name" });
    expect(name).toHaveAttribute("maxlength", "60");
    expect(name).toHaveAttribute("placeholder", "e.g. Retro Rabbit · closing this month");
    fireEvent.change(name, { target: { value: "  Everything open " } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save view" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(create).toHaveBeenCalledWith({
      name: "Everything open",
      tab: "clients",
      layout: "board",
      filters: expect.objectContaining({ status: "all", bu: ["ST21"], q: "", watching: false }),
    });
    expect(await screen.findByText("Saved view “Everything open”.")).toBeInTheDocument();
    expect(await within(sidebar()).findByRole("button", { name: "Everything open" })).toBeInTheDocument();
    expect(within(sidebar()).getByRole("button", { name: "ST21 open" })).toBeInTheDocument();
  });

  it("refuses an empty name and a duplicate in any letter case before asking", async () => {
    const create = vi.spyOn(wsApi, "createWorkspaceView");
    renderAt(<PipelinePage />);
    await ready();
    fireEvent.click(within(sidebar()).getByRole("button", { name: "＋ Save current view" }));
    const dialog = await screen.findByRole("dialog", { name: "Save your working view" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save view" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Enter a name for this view.");
    fireEvent.change(within(dialog).getByRole("textbox", { name: "View name" }), { target: { value: "st21 OPEN" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save view" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("You already have a view with this name.");
    expect(create).not.toHaveBeenCalled();
  });

  it("shows the same message when the server answers 409", async () => {
    vi.spyOn(wsApi, "createWorkspaceView").mockRejectedValue(
      new api.ApiError(409, { detail: "You already have a view with this name." }, "You already have a view with this name."),
    );
    renderAt(<PipelinePage />);
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "Save view ＋" }));
    const dialog = await screen.findByRole("dialog", { name: "Save your working view" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "View name" }), { target: { value: "Made elsewhere" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save view" }));
    await waitFor(() => expect(within(dialog).getByRole("alert")).toHaveTextContent("You already have a view with this name."));
    expect(screen.getByRole("dialog", { name: "Save your working view" })).toBeInTheDocument();
  });

  it("deletes a saved view through its labelled control, after a confirmation", async () => {
    vi.mocked(wsApi.listWorkspaceViews).mockResolvedValueOnce([ST21_OPEN, RR_CLOSING]).mockResolvedValue([RR_CLOSING]);
    const remove = vi.spyOn(wsApi, "deleteWorkspaceView").mockResolvedValue(undefined);
    renderAt(<PipelinePage />);
    await ready();
    fireEvent.click(within(sidebar()).getByRole("button", { name: "Delete saved view ST21 open" }));
    let dialog = await screen.findByRole("dialog", { name: "Delete saved view" });
    expect(dialog).toHaveTextContent("“ST21 open” will be removed from your saved views.");
    fireEvent.click(within(dialog).getByRole("button", { name: "Keep view" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(remove).not.toHaveBeenCalled();

    fireEvent.click(within(sidebar()).getByRole("button", { name: "Delete saved view ST21 open" }));
    dialog = await screen.findByRole("dialog", { name: "Delete saved view" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete view" }));
    await waitFor(() => expect(remove).toHaveBeenCalledWith("view-1"));
    await waitFor(() => expect(within(sidebar()).queryByRole("button", { name: "ST21 open" })).toBeNull());
    expect(await screen.findByText("Deleted saved view “ST21 open”.")).toBeInTheDocument();
  });

  it("says when your views cannot be listed, and Retry asks again", async () => {
    vi.mocked(wsApi.listWorkspaceViews).mockRejectedValueOnce(new Error("offline")).mockResolvedValue([ST21_OPEN]);
    renderAt(<PipelinePage />);
    const alert = await within(await screen.findByRole("complementary", { name: "Views and groups" })).findByRole("alert");
    expect(alert).toHaveTextContent("Your saved views could not load. offline");
    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await within(sidebar()).findByRole("button", { name: "ST21 open" })).toBeInTheDocument();
    expect(within(sidebar()).queryByRole("alert")).toBeNull();
  });

  it("with no saved views, the sidebar says what views are for", async () => {
    vi.mocked(wsApi.listWorkspaceViews).mockResolvedValue([]);
    renderAt(<PipelinePage />);
    expect(await within(await screen.findByRole("complementary", { name: "Views and groups" })).findByText(
      "Keep the filters you use most.",
    )).toBeInTheDocument();
  });
});

describe("F12 · tracking groups", () => {
  it("lists groups with their deal counts; a click toggles the group filter", async () => {
    renderAt(<PipelinePage />);
    await ready();
    const q4 = within(sidebar()).getByRole("button", { name: "Q4 priorities 6" });
    expect(q4).toHaveAttribute("aria-pressed", "false");
    expect(within(sidebar()).getByRole("button", { name: "Strategic accounts 4" })).toBeInTheDocument();
    fireEvent.click(q4);
    await waitFor(() => expect(params().get("group")).toBe("group-q4"));
    expect(within(sidebar()).getByRole("button", { name: "Q4 priorities 6" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Remove Group: Q4 priorities" })).toBeInTheDocument();
    fireEvent.click(within(sidebar()).getByRole("button", { name: "Q4 priorities 6" }));
    await waitFor(() => expect(params().get("group")).toBeNull());
  });

  it("creates an (empty) group from the sidebar; a duplicate name in any case is refused", async () => {
    const created = { id: "group-new", name: "Strategic renewals", deal_ids: [] };
    const create = vi.spyOn(wsApi, "createWorkspaceGroup").mockResolvedValue(created);
    renderAt(<PipelinePage />);
    await ready();
    fireEvent.click(within(sidebar()).getByRole("button", { name: "＋ Create group" }));
    const dialog = await screen.findByRole("dialog", { name: "Create a tracking group" });
    expect(dialog).toHaveAccessibleDescription(
      "Pick opportunities with the list checkboxes, then add them to a group. You can create an empty group now.",
    );
    const name = within(dialog).getByRole("textbox", { name: "Group name" });
    expect(name).toHaveAttribute("placeholder", "e.g. Strategic renewals");
    fireEvent.click(within(dialog).getByRole("button", { name: "Create group" }));
    expect(within(dialog).getAllByRole("alert").map((a) => a.textContent)).toContain("Enter a group name.");
    fireEvent.change(name, { target: { value: "q4 PRIORITIES" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create group" }));
    expect(within(dialog).getAllByRole("alert").map((a) => a.textContent)).toContain("A group with this name already exists.");
    expect(create).not.toHaveBeenCalled();

    vi.mocked(wsApi.listWorkspaceGroups).mockResolvedValue([...GROUPS, created]);
    fireEvent.change(name, { target: { value: "Strategic renewals" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create group" }));
    await waitFor(() => expect(create).toHaveBeenCalledWith({ name: "Strategic renewals", deal_ids: [] }));
    expect(await screen.findByText("Created tracking group “Strategic renewals”.")).toBeInTheDocument();
    expect(await within(sidebar()).findByRole("button", { name: "Strategic renewals 0" })).toBeInTheDocument();
  });

  it("a 409 from the server reads as the duplicate message", async () => {
    vi.spyOn(wsApi, "createWorkspaceGroup").mockRejectedValue(new api.ApiError(409, null, "conflict"));
    renderAt(<PipelinePage />);
    await ready();
    fireEvent.click(within(sidebar()).getByRole("button", { name: "＋ Create group" }));
    const dialog = await screen.findByRole("dialog", { name: "Create a tracking group" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Group name" }), { target: { value: "Elsewhere" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create group" }));
    await waitFor(() =>
      expect(within(dialog).getAllByRole("alert").map((a) => a.textContent)).toContain("A group with this name already exists."),
    );
  });

  it("adds the selected deals to an existing group (first one preselected); the selection stays", async () => {
    const add = vi.spyOn(wsApi, "addDealsToGroup").mockResolvedValue(undefined);
    renderAt(<PipelinePage />);
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "fake: select two" }));
    fireEvent.click(screen.getByRole("button", { name: "fake: add to group" }));
    const dialog = await screen.findByRole("dialog", { name: "Add selected deals to a group" });
    expect(dialog).toHaveAccessibleDescription("2 selected opportunities will be included.");
    expect(within(dialog).getByRole("combobox", { name: "Existing group" })).toHaveValue("group-q4");
    expect(within(dialog).getByRole("heading", { name: "Or create a new group" })).toBeInTheDocument();
    const calls = vi.mocked(wsApi.getWorkspace).mock.calls.length;
    fireEvent.click(within(dialog).getByRole("button", { name: "Add selected" }));
    await waitFor(() => expect(add).toHaveBeenCalledWith("group-q4", ["deal-1", "deal-2"]));
    expect(await screen.findByText("Added selected opportunities to “Q4 priorities”.")).toBeInTheDocument();
    expect(screen.getByTestId("records-selected")).toHaveTextContent("2 selected");
    await waitFor(() => expect(vi.mocked(wsApi.getWorkspace).mock.calls.length).toBe(calls + 1));
  });

  it("or creates a new group holding the selected deals", async () => {
    const create = vi
      .spyOn(wsApi, "createWorkspaceGroup")
      .mockResolvedValue({ id: "group-r", name: "Renewals", deal_ids: ["deal-1", "deal-2"] });
    renderAt(<PipelinePage />);
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "fake: select two" }));
    fireEvent.click(screen.getByRole("button", { name: "fake: add to group" }));
    const dialog = await screen.findByRole("dialog", { name: "Add selected deals to a group" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Group name" }), { target: { value: "Renewals" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create group" }));
    await waitFor(() => expect(create).toHaveBeenCalledWith({ name: "Renewals", deal_ids: ["deal-1", "deal-2"] }));
    expect(await screen.findByText("Created tracking group “Renewals”.")).toBeInTheDocument();
  });

  it("with no groups yet, the add dialog only offers to create one", async () => {
    vi.mocked(wsApi.listWorkspaceGroups).mockResolvedValue([]);
    renderAt(<PipelinePage />);
    await within(await screen.findByRole("complementary", { name: "Views and groups" })).findByText("No groups yet.");
    fireEvent.click(screen.getByRole("button", { name: "fake: select two" }));
    fireEvent.click(screen.getByRole("button", { name: "fake: add to group" }));
    const dialog = await screen.findByRole("dialog", { name: "Add selected deals to a group" });
    expect(within(dialog).queryByRole("combobox", { name: "Existing group" })).toBeNull();
    expect(within(dialog).getByRole("button", { name: "Create group" })).toBeInTheDocument();
  });
});

describe("F13 · watching (page actions)", () => {
  it("Watch selected watches every selected deal, clears the selection, says so and refetches", async () => {
    const watch = vi.spyOn(wsApi, "watchDeal").mockResolvedValue(undefined);
    renderAt(<PipelinePage />);
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "fake: select two" }));
    const calls = vi.mocked(wsApi.getWorkspace).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "fake: watch selected" }));
    await waitFor(() => expect(watch).toHaveBeenCalledTimes(2));
    expect(watch.mock.calls.map((c) => c[0])).toEqual(["deal-1", "deal-2"]);
    expect(await screen.findByText("Selected opportunities added to Watching.")).toBeInTheDocument();
    expect(screen.getByTestId("records-selected")).toHaveTextContent("0 selected");
    await waitFor(() => expect(vi.mocked(wsApi.getWorkspace).mock.calls.length).toBe(calls + 1));
  });

  it("a row's star watches (or stops watching) by the deal's state and refetches; a failure says so and rejects", async () => {
    const watch = vi.spyOn(wsApi, "watchDeal").mockRejectedValueOnce(new Error("Deal not found")).mockResolvedValue(undefined);
    renderAt(<PipelinePage />);
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "fake: watch deal" }));
    expect(await screen.findByText("Watching could not change.")).toBeInTheDocument();
    expect(screen.getByText("Deal not found")).toBeInTheDocument();
    // The rejection reaches the star, so it can undo its optimistic state.
    await waitFor(() => expect(screen.getByTestId("watch-outcome")).toHaveTextContent("rejected"));
    fireEvent.click(screen.getByRole("button", { name: "fake: watch deal" }));
    await waitFor(() => expect(screen.getByTestId("watch-outcome")).toHaveTextContent("resolved"));
    expect(watch).toHaveBeenCalledTimes(2);
    expect(watch).toHaveBeenLastCalledWith("deal-1");
  });
});

describe("F14 · export", () => {
  it("shows ↓ Export view to the roles that may export and downloads the active tab with the current filters", async () => {
    me(["Finance"]);
    const download = vi.spyOn(wsApi, "downloadWorkspaceCsv").mockResolvedValue("DealGate_Pipeline_clients.csv");
    renderAt(<PipelinePage />, "/pipeline?tab=clients&bu=ST21&page=2&sort=name");
    await ready();
    fireEvent.click(await screen.findByRole("button", { name: "Export view" }));
    await waitFor(() =>
      expect(download).toHaveBeenCalledWith(expect.objectContaining({ tab: "clients", bu: ["ST21"], sort: "name" })),
    );
    expect(await screen.findByText("Downloaded DealGate_Pipeline_clients.csv.")).toBeInTheDocument();
  });

  it.each([["Presales"], ["Marketing"]])("is not offered to %s", async (role) => {
    me([role]);
    renderAt(<PipelinePage />);
    await ready();
    await waitFor(() => expect(api.getMe).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Export view" })).toBeNull();
  });

  it("a failed export says why and keeps the view", async () => {
    me(["SystemAdmin"]);
    vi.spyOn(wsApi, "downloadWorkspaceCsv").mockRejectedValue(new api.ApiError(503, null, "Export unavailable"));
    renderAt(<PipelinePage />, "/pipeline?bu=ST21");
    await ready();
    fireEvent.click(await screen.findByRole("button", { name: "Export view" }));
    expect(await screen.findByText("The export could not download.")).toBeInTheDocument();
    expect(screen.getByText("Export unavailable")).toBeInTheDocument();
    expect(params().getAll("bu")).toEqual(["ST21"]);
  });
});

describe("F19 · Create in HubSpot", () => {
  it("opens the portal's new-deal page with the portal id from /api/config, in a new tab", async () => {
    renderAt(<PipelinePage />);
    const link = await screen.findByRole("link", { name: "Create in HubSpot" });
    expect(link).toHaveAttribute("href", "https://app.hubspot.com/contacts/1234567/deal/new");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveTextContent("＋Create in HubSpot↗");
  });

  it("is hidden while the deployment has no portal id", async () => {
    vi.mocked(appConfig.useAppConfig).mockReturnValue({ hubspotPortalId: null, loading: false });
    renderAt(<PipelinePage />);
    await screen.findByRole("region", { name: "Pipeline summary" });
    expect(screen.queryByRole("link", { name: "Create in HubSpot" })).toBeNull();
  });
});

describe("F16 · the views panel on narrow screens", () => {
  it("the sidebar hides below md; the records' Views & groups button opens the panel, and a choice applies and closes it", async () => {
    renderAt(<PipelinePage />);
    await ready();
    expect(sidebar()).toHaveClass("hidden", "md:flex");
    const opener = screen.getByRole("button", { name: "Views & groups" });
    opener.focus();
    fireEvent.click(opener);
    const panel = await screen.findByRole("dialog", { name: "Your views & groups" });
    const p = within(panel);
    expect(p.getAllByRole("heading").map((h) => h.textContent)).toEqual([
      "Your views & groups",
      "Focus views",
      "Saved views",
      "Tracking groups",
    ]);
    expect(p.getByRole("button", { name: "All open opportunities · 109" })).toHaveAttribute("aria-pressed", "true");
    expect(p.getByRole("button", { name: "Needs attention · 36" })).toBeInTheDocument();
    expect(p.getByRole("button", { name: "Watching · 5" })).toBeInTheDocument();
    expect(p.getByRole("button", { name: "ST21 open" })).toBeInTheDocument();
    expect(p.getByRole("button", { name: "Q4 priorities · 6" })).toBeInTheDocument();
    expect(p.getByRole("button", { name: "＋ Save current view" })).toBeInTheDocument();
    expect(p.getByRole("button", { name: "＋ Create group" })).toBeInTheDocument();

    fireEvent.click(p.getByRole("button", { name: "Needs attention · 36" }));
    await waitFor(() => expect(params().get("attention")).toBe("any"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(opener).toHaveFocus();
  });

  it("from the panel, Save current view moves to the save dialog; closing it returns focus to Views & groups", async () => {
    vi.mocked(wsApi.listWorkspaceViews).mockResolvedValue([]);
    renderAt(<PipelinePage />);
    await screen.findByRole("region", { name: "Pipeline summary" });
    const opener = screen.getByRole("button", { name: "Views & groups" });
    opener.focus();
    fireEvent.click(opener);
    const panel = await screen.findByRole("dialog", { name: "Your views & groups" });
    expect(await within(panel).findByText("No saved views yet.")).toBeInTheDocument();
    fireEvent.click(within(panel).getByRole("button", { name: "＋ Save current view" }));
    const save = await screen.findByRole("dialog", { name: "Save your working view" });
    expect(screen.queryByRole("dialog", { name: "Your views & groups" })).toBeNull();
    fireEvent.keyDown(save, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(opener).toHaveFocus();
  });
});

describe("§3 seam · previews", () => {
  it("opens a deal preview with the assignee, moves to its client, and 'Show this client’s deals' searches all statuses", async () => {
    renderAt(<PipelinePage />, "/pipeline?bu=ST21&tab=deals");
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "fake: open deal" }));
    const deal = await screen.findByTestId("deal-preview");
    expect(deal).toHaveTextContent("Cloud modernization");
    await waitFor(() => expect(screen.getByTestId("deal-preview-assignee")).toHaveTextContent("user-1"));
    fireEvent.click(within(deal).getByRole("button", { name: "fake: open client" }));
    const client = await screen.findByTestId("client-preview");
    expect(client).toHaveTextContent("Vector Systems");
    expect(screen.queryByTestId("deal-preview")).toBeNull();
    fireEvent.click(within(client).getByRole("button", { name: "fake: show this client’s deals" }));
    await waitFor(() => expect(params().get("q")).toBe("Vector Systems"));
    expect(params().get("status")).toBe("all");
    expect(params().getAll("bu")).toEqual([]);
    expect(screen.queryByTestId("client-preview")).toBeNull();
  });

  it("the deal preview follows a watch made from it, even for a deal outside the current rows", async () => {
    vi.spyOn(wsApi, "watchDeal").mockResolvedValue(undefined);
    renderAt(<PipelinePage />);
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "fake: open deal" }));
    expect(await screen.findByTestId("deal-preview-watching")).toHaveTextContent("not watching");
    fireEvent.click(screen.getByRole("button", { name: "fake: watch deal" }));
    await waitFor(() => expect(screen.getByTestId("deal-preview-watching")).toHaveTextContent("watching"));
    expect(screen.getByTestId("deal-preview-watching")).not.toHaveTextContent("not watching");
  });
});
