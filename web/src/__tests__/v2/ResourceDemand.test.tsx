import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api/people-demand";
import * as client from "../../api/client";
import { ResourceDemand } from "../../pages/v2/forecast/ResourceDemand";

const source: api.DemandSource = {
  plan_id: "plan-one",
  account_id: "account-one",
  account_name: "Company X",
  title: "Implementation staffing",
  source_url: "/forecast?view=opportunities&account_id=account-one",
  source_version_id: "source-one",
  source_revision: 1,
  lifecycle: "tentative",
  selected: true,
  probability: "0.70",
  publication_version_id: "publication-one",
  state: "current",
  missing: [],
  lines: [
    {
      line_key: "line-one",
      component_id: "component-one",
      assignment_id: "assignment-one",
      role: "Engineer",
      skills: ["python"],
      level: "Senior",
      location: "India",
      timezone: "Asia/Kolkata",
      quantity: 5,
      allocation: "0.500001",
      start_date: "2026-11-01",
      end_date: "2027-04-30",
      delivery_model: "fixed_assignment",
      evidence: ["SOW page 2", "HR review"],
      missing: [],
    },
  ],
};
function result(items = [source]): api.DemandSources {
  return {
    items,
    scope_label: "Company demand",
    is_reservation: false,
    schema_version: "people-demand-v1",
  };
}
beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(client, "getMe").mockResolvedValue({
    groups: ["Delivery"],
  } as client.MeResponse);
  vi.spyOn(api, "getDemandSources").mockResolvedValue(result());
  vi.spyOn(api, "publishDemand").mockResolvedValue({
    publication_id: "publication",
    version_id: "new-publication",
    revision: 2,
    source_version_id: "source-one",
    missing: [],
    is_reservation: false,
  });
});
describe("Resource demand source publication", () => {
  it("reveals the requested source anchor after asynchronous demand loads", async () => {
    const scroll = vi.spyOn(HTMLElement.prototype, "scrollIntoView");
    window.history.replaceState(null, "", "/people/demand#demand-plan-one");
    try {
      render(<ResourceDemand />);
      await screen.findByRole("region", { name: source.title });
      await waitFor(() => expect(scroll).toHaveBeenCalledTimes(1));
      expect(scroll.mock.instances[0]).toBe(screen.getByRole("region", { name: source.title }));
      fireEvent.click(screen.getByRole("button", { name: "Reload sources" }));
      await waitFor(() => expect(api.getDemandSources).toHaveBeenCalledTimes(2));
      expect(scroll).toHaveBeenCalledTimes(1);
    } finally {
      window.history.replaceState(null, "", "/");
      scroll.mockRestore();
    }
  });
  it("filters full staffing intervals with inclusive end dates without losing unresolved sources or editor inputs", async () => {
    const earlier = { ...source.lines[0], line_key: "earlier", role: "Earlier engineer",
      start_date: "2026-11-01", end_date: "2026-12-31" };
    vi.mocked(api.getDemandSources).mockResolvedValue(result([
      { ...source, lines: [source.lines[0], earlier] },
      { ...source, plan_id: "outside", title: "Outside period", lines: [earlier] },
      { ...source, plan_id: "boundary", title: "Ends at period start",
        lines: [{ ...earlier, end_date: "2027-01-01" }] },
      { ...source, plan_id: "unknown", title: "Unknown dates",
        lines: [{ ...earlier, start_date: null }] },
      { ...source, plan_id: "pending", title: "Pending staffing", state: "pending", lines: [] },
      { ...source, plan_id: "stale", title: "Stale outside period", state: "stale", lines: [earlier] },
      { ...source, plan_id: "malformed", title: "Malformed dates", lines: [{ ...earlier, start_date: "2026-02-30" }] },
      { ...source, plan_id: "reversed", title: "Reversed dates", lines: [{ ...earlier, start_date: "2027-03-01" }] },
    ]));
    render(<ResourceDemand period={{ start: "2027-01-01", end_exclusive: "2027-02-01" }} />);
    await screen.findByText("Implementation staffing");
    expect(screen.queryByText("Outside period")).not.toBeInTheDocument();
    for (const title of ["Ends at period start", "Unknown dates", "Pending staffing", "Stale outside period", "Malformed dates", "Reversed dates"])
      expect(screen.getByText(title)).toBeInTheDocument();
    const region = screen.getByRole("region", { name: "Implementation staffing" });
    expect(region).not.toHaveTextContent("Earlier engineer");
    expect(region).toHaveTextContent("2026-11-01 to 2027-04-30");
    fireEvent.click(region.querySelector("button")!);
    expect(screen.getByLabelText("Skills for Earlier engineer")).toHaveValue("python");
    fireEvent.change(screen.getByLabelText("Skills for Earlier engineer"), { target: { value: "typescript" } });
    fireEvent.change(screen.getByLabelText("Publication reason"), { target: { value: "Confirm earlier assignment" } });
    fireEvent.click(screen.getByRole("button", { name: "Publish latest source" }));
    await waitFor(() => expect(api.publishDemand).toHaveBeenCalledWith(expect.objectContaining({
      enrichments: { earlier: { skills: ["typescript"], evidence: ["SOW page 2", "HR review"] } },
    })));
  });
  it("retains forecast context when drilling into a plan without retaining pagination", async () => {
    render(<ResourceDemand forecastSearch="scenario=upside&future_quarters=4&as_of=2026-11-15&month=2027-01-01&view=resources&page=2" />);
    const link = await screen.findByRole("link", { name: "Implementation staffing" });
    const target = new URL(link.getAttribute("href")!, "http://localhost");
    expect(target.pathname).toBe("/forecast");
    expect(Object.fromEntries(target.searchParams)).toEqual({
      view: "opportunities", account_id: "account-one", scenario: "upside",
      future_quarters: "4", as_of: "2026-11-15", month: "2027-01-01",
    });
  });
  it("publishes a retained project using its own identity, never a fake plan", async () => {
    vi.mocked(api.getDemandSources).mockResolvedValue(result([{
      ...source, source_id: "project-one", source_kind: "project", project_id: "project-one",
      plan_id: null, state: "pending", publication_version_id: null, lines: [],
      lifecycle: "committed", probability: "1", missing: ["current_source_publication"],
    }]));
    render(<ResourceDemand />);
    fireEvent.click(await screen.findByRole("button", { name: "Publish demand" }));
    fireEvent.change(screen.getByLabelText("Publication reason"), { target: { value: "Retained delivery capability" } });
    fireEvent.click(screen.getByRole("button", { name: "Publish latest source" }));
    await waitFor(() => expect(api.publishDemand).toHaveBeenCalled());
    const sent = vi.mocked(api.publishDemand).mock.calls[0][0];
    expect(sent.project_id).toBe("project-one");
    expect(sent).not.toHaveProperty("plan_id");
    expect(sent.expected_source_version_id).toBe("source-one");
    expect(screen.getByRole("region", { name: "Implementation staffing" })).toHaveAttribute("id", "demand-project-one");
  });
  it("shows source facts without financial weighting or editable headcount", async () => {
    render(<ResourceDemand />);
    expect(await screen.findByText("Company X")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Implementation staffing" }),
    ).toHaveAttribute("href", source.source_url);
    expect(screen.getByText("0.500001")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("Win probability: 70.0%")).toBeInTheDocument();
    expect(screen.getByText("2026-11-01 to 2027-04-30")).toBeInTheDocument();
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });
  it("publishes a pending source with empty enrichments and both CAS values", async () => {
    vi.mocked(api.getDemandSources).mockResolvedValue(
      result([
        {
          ...source,
          state: "pending",
          publication_version_id: null,
          lines: [],
          missing: ["current_source_publication"],
        },
      ]),
    );
    const refreshed = vi.fn();
    render(<ResourceDemand onRefresh={refreshed} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Publish demand" }),
    );
    fireEvent.change(screen.getByLabelText("Publication reason"), {
      target: { value: "Confirmed source staffing" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Publish latest source" }),
    );
    await waitFor(() =>
      expect(api.publishDemand).toHaveBeenCalledWith(
        expect.objectContaining({
          plan_id: "plan-one",
          expected_source_version_id: "source-one",
          expected_publication_version_id: null,
          enrichments: {},
          reason: "Confirmed source staffing",
          request_key: expect.any(String),
        }),
      ),
    );
    await waitFor(() => expect(refreshed).toHaveBeenCalledOnce());
  });
  it("prefills capability and evidence, sends only changed enrichment without hidden continuity", async () => {
    render(<ResourceDemand />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Revise demand" }),
    );
    expect(screen.getByLabelText("Skills for Engineer")).toHaveValue("python");
    expect(screen.getByLabelText("Level for Engineer")).toHaveValue("Senior");
    expect(screen.getByLabelText("Evidence for Engineer")).toHaveValue(
      "SOW page 2\nHR review",
    );
    expect(
      screen.getByRole("textbox", { name: "Skills for Engineer" }),
    ).toHaveValue("python");
    expect(
      screen.getByRole("textbox", { name: "Level for Engineer" }),
    ).toHaveValue("Senior");
    expect(
      screen.getByRole("textbox", { name: "Evidence for Engineer" }),
    ).toHaveValue("SOW page 2\nHR review");
    fireEvent.change(screen.getByLabelText("Skills for Engineer"), {
      target: { value: "python\ntypescript" },
    });
    fireEvent.change(screen.getByLabelText("Publication reason"), {
      target: { value: "HR confirmed skills" },
    });
    expect(
      screen.getByRole("textbox", { name: "Publication reason" }),
    ).toHaveValue("HR confirmed skills");
    fireEvent.click(
      screen.getByRole("button", { name: "Publish latest source" }),
    );
    await waitFor(() =>
      expect(api.publishDemand).toHaveBeenCalledWith(
        expect.objectContaining({
          expected_publication_version_id: "publication-one",
          enrichments: {
            "line-one": {
              skills: ["python", "typescript"],
              evidence: ["SOW page 2", "HR review"],
            },
          },
        }),
      ),
    );
  });
  it("preserves draft and visible conflict through an explicit source reload", async () => {
    vi.mocked(api.publishDemand).mockRejectedValue(
      new client.ApiError(
        409,
        { detail: "Source version changed" },
        "Source version changed",
      ),
    );
    render(<ResourceDemand />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Revise demand" }),
    );
    fireEvent.change(screen.getByLabelText("Skills for Engineer"), {
      target: { value: "typescript" },
    });
    fireEvent.change(screen.getByLabelText("Publication reason"), {
      target: { value: "Skills correction" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Publish latest source" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Source version changed",
    );
    vi.mocked(api.getDemandSources).mockResolvedValue(
      result([
        {
          ...source,
          source_version_id: "source-two",
          publication_version_id: "publication-two",
          lines: [{ ...source.lines[0], level: "Principal" }],
        },
      ]),
    );
    fireEvent.click(screen.getByRole("button", { name: "Reload sources" }));
    await waitFor(() => expect(api.getDemandSources).toHaveBeenCalledTimes(2));
    expect(screen.getByLabelText("Skills for Engineer")).toHaveValue(
      "typescript",
    );
    expect(screen.getByLabelText("Publication reason")).toHaveValue(
      "Skills correction",
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Source version changed",
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Publish latest source" }),
    );
    await waitFor(() =>
      expect(api.publishDemand).toHaveBeenLastCalledWith(
        expect.objectContaining({
          expected_source_version_id: "source-two",
          expected_publication_version_id: "publication-two",
          enrichments: {
            "line-one": {
              skills: ["typescript"],
              evidence: ["SOW page 2", "HR review"],
            },
          },
        }),
      ),
    );
  });
  it("hides writes for HR and filters authorized rows by account", async () => {
    vi.mocked(client.getMe).mockResolvedValue({
      groups: ["HR"],
    } as client.MeResponse);
    vi.mocked(api.getDemandSources).mockResolvedValue(
      result([
        source,
        {
          ...source,
          plan_id: "other",
          account_id: "account-two",
          title: "Other account",
        },
      ]),
    );
    render(<ResourceDemand accountId="account-one" />);
    expect(await screen.findByText("Selected account demand")).toBeInTheDocument();
    await screen.findByText("Company X");
    expect(screen.queryByText("Other account")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Revise demand" }),
    ).not.toBeInTheDocument();
  });
  it("checks role before requesting demand and distinguishes errors from empty lists", async () => {
    vi.mocked(client.getMe).mockResolvedValue({
      groups: ["Unrecognized"],
    } as client.MeResponse);
    render(<ResourceDemand />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Demand planning permission required",
    );
    expect(api.getDemandSources).not.toHaveBeenCalled();
    expect(screen.queryByText("No demand sources")).not.toBeInTheDocument();
  });
  it("shows unresolved source facts without invented zero values", async () => {
    vi.mocked(api.getDemandSources).mockResolvedValue(
      result([
        {
          ...source,
          account_name: undefined,
          missing: ["line:line-one:allocation"],
          lines: [
            {
              ...source.lines[0],
              allocation: null,
              quantity: null,
              start_date: null,
              missing: ["allocation", "start_date"],
            },
          ],
        },
      ]),
    );
    render(<ResourceDemand />);
    expect(await screen.findByText("Account unavailable")).toBeInTheDocument();
    expect(screen.getAllByText("Unknown").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Unknown to 2027-04-30")).toBeInTheDocument();
    expect(screen.queryByText("account-one")).not.toBeInTheDocument();
  });
  it("ignores an older response after an explicit reload", async () => {
    let resolveOlder!: (value: api.DemandSources) => void;
    vi.mocked(api.getDemandSources).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOlder = resolve;
        }),
    );
    render(<ResourceDemand />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Reload sources" }),
    );
    await screen.findByText("Company X");
    await act(async () =>
      resolveOlder(result([{ ...source, title: "Obsolete response" }])),
    );
    expect(screen.queryByText("Obsolete response")).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Implementation staffing" }),
    ).toBeInTheDocument();
  });
  it("reports source failure without claiming an empty list", async () => {
    vi.mocked(api.getDemandSources).mockRejectedValue(
      new Error("Demand service unavailable"),
    );
    render(<ResourceDemand />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Demand service unavailable",
    );
    expect(screen.queryByText("No demand sources")).not.toBeInTheDocument();
  });
  it("retains the idempotency key when the unchanged publication is retried", async () => {
    vi.mocked(api.publishDemand).mockRejectedValue(
      new Error("Connection interrupted"),
    );
    render(<ResourceDemand />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Revise demand" }),
    );
    fireEvent.change(screen.getByLabelText("Publication reason"), {
      target: { value: "Confirmed staffing" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Publish latest source" }),
    );
    await screen.findByText("Connection interrupted");
    fireEvent.click(
      screen.getByRole("button", { name: "Publish latest source" }),
    );
    await waitFor(() => expect(api.publishDemand).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.publishDemand).mock.calls[0][0].request_key).toBe(
      vi.mocked(api.publishDemand).mock.calls[1][0].request_key,
    );
  });
});
