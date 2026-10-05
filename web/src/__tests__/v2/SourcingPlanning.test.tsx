import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import * as api from "../../api/people-sourcing";
import * as client from "../../api/client";
import { SourcingPlanningPage } from "../../pages/v2/SourcingPlanning";

const rules: api.SourcingRules = {
  state: "configured",
  id: "rules-1",
  revision: 1,
  rules: [{ skill: "python", location: "US", lead_days: 45 }],
};
const source = {
  plan_id: "plan-1",
  publication_id: "publication-1",
  publication_version_id: "demand-1",
  account_name: "Company X",
  title: "Company X staffing",
  state: "current",
} as api.SourcingSource;
const draft: api.SourcingDraft = {
  id: "draft-v1",
  draft_id: "draft",
  revision: 1,
  demand_version_id: "demand-1",
  rule_version_id: "rules-1",
  source_watermark: "watermark",
  reason: "Confirmed sourcing",
  created_by: "private-owner",
  created_at: "2026-10-01T12:00:00Z",
  is_reservation: false,
  snapshot: {
    title: "Company X staffing",
    probability: "0.70",
    lifecycle: "tentative",
    source_version_id: "source-1",
    source_url: null,
    complete: true,
    missing: [],
    calculation_version: "v1",
    is_reservation: false,
    rows: [
      {
        id: "demand-line",
        role: "Engineer",
        skills: ["python"],
        level: "Senior",
        location: "US",
        timezone: "America/New_York",
        quantity: 7,
        retained_quantity: 2,
        incremental_quantity: 5,
        matched_quantity: 3,
        gap_quantity: 4,
        continuity_gap_quantity: 1,
        incremental_gap_quantity: 3,
        gap_fte: "2.000001",
        start: "2026-11-01",
        end_exclusive: "2026-12-01",
        sourcing_by: "2026-09-17",
        missing: ["continuity_unresolved"],
      },
    ],
  },
};
beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(client, "getMe").mockResolvedValue({
    groups: ["HR"],
  } as client.MeResponse);
  vi.spyOn(api, "getSourcingRules").mockResolvedValue(rules);
  vi.spyOn(api, "getSourcingSources").mockResolvedValue({ items: [source] });
  vi.spyOn(api, "getSourcingHistory").mockResolvedValue({
    items: [draft],
    current_version_id: draft.id,
    state: "current",
  });
  vi.spyOn(api, "saveSourcingRules").mockResolvedValue({
    ...rules,
    id: "rules-2",
    revision: 2,
  });
  vi.spyOn(api, "prepareSourcingDraft").mockResolvedValue({
    ...draft,
    id: "draft-v2",
    revision: 2,
  });
});
it("selects retained project publication independently of null plan identity", async () => {
  vi.mocked(api.getSourcingSources).mockResolvedValue({ items: [{
    ...source, plan_id: null, source_id: "retained-project", source_kind: "project", project_id: "retained-project",
  }] });
  render(<SourcingPlanningPage />);
  await screen.findByDisplayValue("python");
  expect(screen.getByLabelText("Published source")).toHaveValue("retained-project");
  await waitFor(() => expect(api.getSourcingHistory).toHaveBeenCalledWith("publication-1", 1));
  fireEvent.change(screen.getByLabelText("Draft reason"), { target: { value: "Retained project review" } });
  fireEvent.click(screen.getByRole("button", { name: "Prepare sourcing draft" }));
  await waitFor(() => expect(api.prepareSourcingDraft).toHaveBeenCalledWith(expect.objectContaining({
    publication_id: "publication-1", expected_demand_version_id: "demand-1",
  })));
});
it("gates named sourcing before any data request", async () => {
  vi.mocked(client.getMe).mockResolvedValue({
    groups: ["Delivery"],
  } as client.MeResponse);
  render(<SourcingPlanningPage />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "HR or SystemAdmin",
  );
  expect(api.getSourcingRules).not.toHaveBeenCalled();
  expect(api.getSourcingSources).not.toHaveBeenCalled();
});
it("shows empty unconfigured rules with no suggested values", async () => {
  vi.mocked(api.getSourcingRules).mockResolvedValue({
    state: "unconfigured",
    id: null,
    revision: null,
    rules: [],
  });
  render(<SourcingPlanningPage />);
  await screen.findByText("Unconfigured");
  expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Add rule" }));
  expect(screen.getByRole("spinbutton", { name: "Lead days 1" })).toHaveValue(
    null,
  );
  expect(
    screen.getByRole("button", { name: "Prepare sourcing draft" }),
  ).toBeDisabled();
});
it("edits and removes rule rows and saves with current CAS and reason", async () => {
  render(<SourcingPlanningPage />);
  await screen.findByDisplayValue("python");
  fireEvent.click(screen.getByRole("button", { name: "Add rule" }));
  fireEvent.click(screen.getByRole("button", { name: "Remove rule 2" }));
  fireEvent.change(screen.getByRole("spinbutton", { name: "Lead days 1" }), {
    target: { value: "30" },
  });
  fireEvent.change(
    screen.getByRole("textbox", { name: "Rule change reason" }),
    { target: { value: "HR reviewed lead time" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Save rules" }));
  await waitFor(() =>
    expect(api.saveSourcingRules).toHaveBeenCalledWith(
      expect.objectContaining({
        expected_version_id: "rules-1",
        rules: [{ skill: "python", location: "US", lead_days: 30 }],
        reason: "HR reviewed lead time",
        request_key: expect.any(String),
      }),
    ),
  );
});
it("keeps populated rule draft and conflict through explicit reload then uses new CAS", async () => {
  vi.mocked(api.saveSourcingRules).mockRejectedValue(
    new client.ApiError(409, { detail: "Rules changed" }),
  );
  render(<SourcingPlanningPage />);
  await screen.findByDisplayValue("python");
  fireEvent.change(screen.getByRole("spinbutton", { name: "Lead days 1" }), {
    target: { value: "60" },
  });
  fireEvent.change(
    screen.getByRole("textbox", { name: "Rule change reason" }),
    { target: { value: "Longer sourcing window" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Save rules" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Rules changed");
  vi.mocked(api.getSourcingRules).mockResolvedValue({
    ...rules,
    id: "rules-new",
  });
  fireEvent.click(screen.getByRole("button", { name: "Reload latest" }));
  await waitFor(() => expect(api.getSourcingRules).toHaveBeenCalledTimes(2));
  expect(screen.getByRole("spinbutton", { name: "Lead days 1" })).toHaveValue(
    60,
  );
  expect(
    screen.getByRole("textbox", { name: "Rule change reason" }),
  ).toHaveValue("Longer sourcing window");
  expect(screen.getByRole("alert")).toHaveTextContent("Rules changed");
  fireEvent.click(screen.getByRole("button", { name: "Save rules" }));
  await waitFor(() =>
    expect(api.saveSourcingRules).toHaveBeenLastCalledWith(
      expect.objectContaining({ expected_version_id: "rules-new" }),
    ),
  );
});
it("shows cost-free history and prepares with all current versions", async () => {
  render(<SourcingPlanningPage />);
  expect(await screen.findByText("2026-09-17")).toBeInTheDocument();
  expect(screen.getByText("2.000001")).toBeInTheDocument();
  expect(
    within(screen.getAllByRole("row")[1])
      .getAllByRole("cell")
      .slice(2, 10)
      .map((cell) => cell.textContent),
  ).toEqual(["7", "2", "5", "3", "4", "1", "3", "2.000001"]);
  expect(screen.getByText("Win probability: 70.0%")).toBeInTheDocument();
  expect(screen.queryByText("private-owner")).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("textbox", { name: "Draft reason" }), {
    target: { value: "Confirmed staffing dates" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare sourcing draft" }),
  );
  await waitFor(() =>
    expect(api.prepareSourcingDraft).toHaveBeenCalledWith(
      expect.objectContaining({
        publication_id: "publication-1",
        expected_demand_version_id: "demand-1",
        expected_rule_version_id: "rules-1",
        expected_draft_version_id: "draft-v1",
        reason: "Confirmed staffing dates",
      }),
    ),
  );
});
it("cannot prepare from a stale demand publication", async () => {
  vi.mocked(api.getSourcingSources).mockResolvedValue({
    items: [{ ...source, state: "stale" }],
  });
  render(<SourcingPlanningPage />);
  await screen.findByDisplayValue("python");
  fireEvent.change(screen.getByRole("textbox", { name: "Draft reason" }), {
    target: { value: "Confirmed" },
  });
  expect(
    screen.getByRole("button", { name: "Prepare sourcing draft" }),
  ).toBeDisabled();
});
it("ignores stale history after another source is selected", async () => {
  let resolveOld!: (value: api.SourcingHistory) => void;
  vi.mocked(api.getSourcingSources).mockResolvedValue({
    items: [
      source,
      {
        ...source,
        plan_id: "plan-2",
        publication_id: "publication-2",
        title: "Another source",
      },
    ],
  });
  vi.mocked(api.getSourcingHistory)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve;
        }),
    )
    .mockResolvedValue({
      items: [],
      current_version_id: null,
      state: "missing",
    });
  render(<SourcingPlanningPage />);
  await waitFor(() => expect(api.getSourcingHistory).toHaveBeenCalledOnce());
  fireEvent.change(screen.getByRole("combobox", { name: "Published source" }), {
    target: { value: "plan-2" },
  });
  await screen.findByText("No sourcing drafts");
  await act(async () =>
    resolveOld({
      items: [draft],
      current_version_id: draft.id,
      state: "current",
    }),
  );
  expect(screen.queryByText("2026-09-17")).not.toBeInTheDocument();
});
it("preserves draft reason after conflict and reloads all source versions", async () => {
  vi.mocked(api.prepareSourcingDraft).mockRejectedValue(
    new client.ApiError(409, { detail: "Allocation changed" }),
  );
  render(<SourcingPlanningPage />);
  await screen.findByText("2026-09-17");
  fireEvent.change(screen.getByRole("textbox", { name: "Draft reason" }), {
    target: { value: "Reviewed sourcing" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare sourcing draft" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Allocation changed",
  );
  vi.mocked(api.getSourcingRules).mockResolvedValue({
    ...rules,
    id: "rules-new",
  });
  vi.mocked(api.getSourcingSources).mockResolvedValue({
    items: [{ ...source, publication_version_id: "demand-new" }],
  });
  vi.mocked(api.getSourcingHistory).mockResolvedValue({
    items: [draft],
    current_version_id: "draft-new",
    state: "stale",
  });
  fireEvent.click(screen.getByRole("button", { name: "Reload latest" }));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Prepare sourcing draft" }),
    ).toBeEnabled(),
  );
  expect(screen.getByRole("textbox", { name: "Draft reason" })).toHaveValue(
    "Reviewed sourcing",
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Allocation changed");
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare sourcing draft" }),
  );
  await waitFor(() =>
    expect(api.prepareSourcingDraft).toHaveBeenLastCalledWith(
      expect.objectContaining({
        expected_demand_version_id: "demand-new",
        expected_rule_version_id: "rules-new",
        expected_draft_version_id: "draft-new",
      }),
    ),
  );
});
it("shows a history failure without substituting an empty successful draft list", async () => {
  vi.mocked(api.getSourcingHistory).mockRejectedValue(
    new Error("Draft history unavailable"),
  );
  render(<SourcingPlanningPage />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Draft history unavailable",
  );
  expect(screen.queryByText("No sourcing drafts")).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Prepare sourcing draft" }),
  ).toBeDisabled();
});
it("pages immutable history without treating the selected historical revision as current CAS", async () => {
  vi.mocked(api.getSourcingHistory)
    .mockResolvedValueOnce({
      items: Array.from({ length: 50 }, (_, index) => ({
        ...draft,
        id: `v-${index}`,
        revision: 60 - index,
      })),
      current_version_id: "current-60",
      state: "current",
    })
    .mockResolvedValue({
      items: [{ ...draft, id: "old-10", revision: 10 }],
      current_version_id: "current-60",
      state: "current",
    });
  render(<SourcingPlanningPage />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Next history page" }),
  );
  await waitFor(() =>
    expect(api.getSourcingHistory).toHaveBeenLastCalledWith("publication-1", 2),
  );
  await screen.findByText("Revision 10 - 2026-10-01T12:00:00Z");
  fireEvent.change(screen.getByRole("textbox", { name: "Draft reason" }), {
    target: { value: "Refreshed after history review" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare sourcing draft" }),
  );
  await waitFor(() =>
    expect(api.prepareSourcingDraft).toHaveBeenCalledWith(
      expect.objectContaining({ expected_draft_version_id: "current-60" }),
    ),
  );
});
