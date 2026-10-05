import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import * as api from "../../api/people-coverage";
import * as client from "../../api/client";
import type { DemandSource } from "../../api/people-demand";
import { CoverageEditor } from "../../components/CoverageEditor";

const plan: DemandSource = {
  plan_id: "plan",
  source_kind: "plan",
  publication_id: "plan-pub",
  publication_version_id: "plan-v1",
  account_id: "account",
  title: "Proposed staffing",
  source_version_id: "source-v1",
  source_revision: 1,
  lifecycle: "tentative",
  selected: true,
  probability: "0.70",
  state: "current",
  missing: [],
  lines: [
    {
      line_key: "plan-line",
      component_id: "build",
      assignment_id: "team",
      role: "Engineer",
      skills: ["python"],
      level: "Senior",
      location: "US",
      timezone: "America/New_York",
      quantity: 7,
      allocation: "1",
      start_date: "2026-11-01",
      end_date: "2026-11-30",
      delivery_model: "fixed_assignment",
      evidence: [],
      missing: [],
    },
  ],
};
const project: DemandSource = {
  ...plan,
  plan_id: null,
  source_kind: "project",
  project_id: "project",
  publication_id: "project-pub",
  publication_version_id: "project-v1",
  title: "Signed delivery",
  lifecycle: "committed",
  lines: [
    { ...plan.lines[0], line_key: "project-line", start_date: "2026-11-10" },
  ],
};
const mapping: api.CoverageVersion = {
  id: "root",
  version_id: "mapping-v2",
  revision: 2,
  plan_publication_id: "plan-pub",
  project_publication_id: "project-pub",
  plan_version_id: "plan-v1",
  project_version_id: "project-v1",
  mappings: [
    {
      plan_line_key: "plan-line",
      project_line_key: "project-line",
      plan_slots: [0, 1],
      project_slots: [2, 3],
      start_date: "2026-11-10",
      end_date: "2026-11-30",
    },
  ],
  reason: "Confirmed conversion",
  created_by: "opaque-owner",
  created_at: "2026-10-02",
  state: "current",
  is_reservation: false,
};
beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(client, "getMe").mockResolvedValue({
    groups: ["Delivery"],
  } as client.MeResponse);
  vi.spyOn(api, "getCoverage").mockImplementation(async (_plan, root) => ({
    items: root
      ? [mapping, { ...mapping, version_id: "mapping-v1", revision: 1 }]
      : [mapping],
    current_version_id: mapping.version_id,
    is_reservation: false,
  }));
  vi.spyOn(api, "getCoverageSources").mockResolvedValue({
    items: [plan, project],
    scope_label: "Company",
    is_reservation: false,
    schema_version: "v1",
  });
  vi.spyOn(api, "saveCoverage").mockResolvedValue({
    ...mapping,
    version_id: "mapping-v3",
    revision: 3,
  });
});
it("keeps an unavailable mapped project clearable without allowing a new mapping", async () => {
  render(<CoverageEditor plan={plan} available={[plan]} onSaved={vi.fn()} />);
  await screen.findByRole("option", { name: /Unavailable mapped project/ });
  expect(screen.getByLabelText("Replacement project")).toHaveValue("project-pub");
  expect(screen.queryByRole("button", { name: "Save coverage" })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Coverage reason"), { target: { value: "Clear archived source" } });
  fireEvent.click(screen.getByRole("button", { name: "Clear coverage" }));
  await waitFor(() => expect(api.saveCoverage).toHaveBeenCalledWith(expect.objectContaining({
    expected_mapping_version_id: "mapping-v2", expected_project_version_id: "project-v1",
    expected_plan_version_id: "plan-v1", mappings: [], reason: "Clear archived source",
  })));
});

it("prefills current explicit positions and dates without using probability", async () => {
  render(
    <CoverageEditor
      plan={plan}
      available={[plan, project]}
      onSaved={vi.fn()}
    />,
  );
  expect(
    await screen.findByRole("spinbutton", { name: "Plan first slot 1" }),
  ).toHaveValue(1);
  expect(
    screen.getByRole("spinbutton", { name: "Project first slot 1" }),
  ).toHaveValue(3);
  expect(screen.getByRole("spinbutton", { name: "Slot count 1" })).toHaveValue(
    2,
  );
  expect(screen.getByLabelText("Start date 1")).toHaveValue("2026-11-10");
  expect(
    screen.queryByRole("option", { name: "Proposed staffing" }),
  ).not.toBeInTheDocument();
});
it("sends explicit zero-based slots and current CAS even when viewing old history", async () => {
  const saved = vi.fn();
  render(<CoverageEditor plan={plan} available={[project]} onSaved={saved} />);
  await screen.findByRole("spinbutton", { name: "Slot count 1" });
  fireEvent.change(
    await screen.findByRole("combobox", { name: "Coverage history revision" }),
    { target: { value: "mapping-v1" } },
  );
  fireEvent.change(
    screen.getByRole("spinbutton", { name: "Plan first slot 1" }),
    { target: { value: "2" } },
  );
  fireEvent.change(screen.getByRole("textbox", { name: "Coverage reason" }), {
    target: { value: "Confirmed slots" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save coverage" }));
  await waitFor(() =>
    expect(api.saveCoverage).toHaveBeenCalledWith(
      expect.objectContaining({
        expected_mapping_version_id: "mapping-v2",
        mappings: [{ ...mapping.mappings[0], plan_slots: [1, 2] }],
        reason: "Confirmed slots",
      }),
    ),
  );
  await waitFor(() => expect(saved).toHaveBeenCalledOnce());
});
it("new coverage prefills source lines and intersection dates but requires explicit count", async () => {
  vi.mocked(api.getCoverage).mockResolvedValue({
    items: [],
    current_version_id: null,
    is_reservation: false,
  });
  render(
    <CoverageEditor plan={plan} available={[project]} onSaved={vi.fn()} />,
  );
  await screen.findByRole("button", { name: "Add mapping" });
  fireEvent.click(screen.getByRole("button", { name: "Add mapping" }));
  expect(screen.getByRole("spinbutton", { name: "Slot count 1" })).toHaveValue(
    null,
  );
  expect(screen.getByLabelText("Start date 1")).toHaveValue("2026-11-10");
  expect(screen.getByLabelText("End date 1")).toHaveValue("2026-11-30");
});
it("preserves conflict draft and reloads both source and mapping versions", async () => {
  vi.mocked(api.saveCoverage).mockRejectedValue(
    new client.ApiError(409, { detail: "Coverage changed" }),
  );
  const view = render(
    <CoverageEditor plan={plan} available={[project]} onSaved={vi.fn()} />,
  );
  await screen.findByRole("spinbutton", { name: "Slot count 1" });
  fireEvent.change(screen.getByRole("spinbutton", { name: "Slot count 1" }), {
    target: { value: "3" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "Coverage reason" }), {
    target: { value: "Retain edited slots" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save coverage" }));
  await screen.findByText("Coverage changed");
  vi.mocked(api.getCoverageSources).mockResolvedValue({
    items: [
      { ...plan, publication_version_id: "plan-v2" },
      { ...project, publication_version_id: "project-v2" },
    ],
    scope_label: "Company",
    is_reservation: false,
    schema_version: "v1",
  });
  vi.mocked(api.getCoverage).mockResolvedValue({
    items: [{ ...mapping, version_id: "mapping-new" }],
    current_version_id: "mapping-new",
    is_reservation: false,
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Reload latest coverage" }),
  );
  await waitFor(() => expect(api.getCoverageSources).toHaveBeenCalledOnce());
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Save coverage" })).toBeEnabled(),
  );
  expect(screen.getByRole("spinbutton", { name: "Slot count 1" })).toHaveValue(
    3,
  );
  expect(screen.getByRole("textbox", { name: "Coverage reason" })).toHaveValue(
    "Retain edited slots",
  );
  expect(screen.getByText("Coverage changed")).toBeInTheDocument();
  view.rerender(
    <CoverageEditor
      plan={{ ...plan }}
      available={[{ ...project }]}
      onSaved={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Save coverage" }));
  await waitFor(() =>
    expect(api.saveCoverage).toHaveBeenLastCalledWith(
      expect.objectContaining({
        expected_plan_version_id: "plan-v2",
        expected_project_version_id: "project-v2",
        expected_mapping_version_id: "mapping-new",
      }),
    ),
  );
});
it("clears only by a reasoned empty mapping revision", async () => {
  render(
    <CoverageEditor plan={plan} available={[project]} onSaved={vi.fn()} />,
  );
  await screen.findByRole("spinbutton", { name: "Slot count 1" });
  expect(screen.getByRole("button", { name: "Clear coverage" })).toBeDisabled();
  fireEvent.change(screen.getByRole("textbox", { name: "Coverage reason" }), {
    target: { value: "Conversion withdrawn" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Clear coverage" }));
  await waitFor(() =>
    expect(api.saveCoverage).toHaveBeenCalledWith(
      expect.objectContaining({
        mappings: [],
        expected_mapping_version_id: "mapping-v2",
        reason: "Conversion withdrawn",
      }),
    ),
  );
});
it("HR can inspect but cannot write coverage", async () => {
  vi.mocked(client.getMe).mockResolvedValue({
    groups: ["HR"],
  } as client.MeResponse);
  render(
    <CoverageEditor plan={plan} available={[project]} onSaved={vi.fn()} />,
  );
  await screen.findByRole("combobox", { name: "Coverage history revision" });
  expect(
    screen.queryByRole("button", { name: "Save coverage" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Add mapping" }),
  ).not.toBeInTheDocument();
});
it("denies unsupported roles before requesting coverage", async () => {
  vi.mocked(client.getMe).mockResolvedValue({
    id: "viewer",
    email: "viewer@example.test",
    name: "Viewer",
    groups: [],
  });
  render(
    <CoverageEditor plan={plan} available={[project]} onSaved={vi.fn()} />,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Demand planning permission required",
  );
  expect(api.getCoverage).not.toHaveBeenCalled();
});
it("preserves nonconsecutive saved slots as multiple explicit rows", async () => {
  vi.mocked(api.getCoverage).mockResolvedValue({
    items: [
      {
        ...mapping,
        mappings: [
          { ...mapping.mappings[0], plan_slots: [0, 2], project_slots: [1, 4] },
        ],
      },
    ],
    current_version_id: mapping.version_id,
    is_reservation: false,
  });
  render(
    <CoverageEditor plan={plan} available={[project]} onSaved={vi.fn()} />,
  );
  expect(
    await screen.findByRole("spinbutton", { name: "Plan first slot 2" }),
  ).toHaveValue(3);
  expect(
    screen.getByRole("spinbutton", { name: "Project first slot 2" }),
  ).toHaveValue(5);
  expect(screen.getByRole("spinbutton", { name: "Slot count 1" })).toHaveValue(
    1,
  );
  expect(screen.getByRole("spinbutton", { name: "Slot count 2" })).toHaveValue(
    1,
  );
});
it("does not replace new project history with a late previous response", async () => {
  let resolveOld!: (value: api.CoverageEnvelope) => void;
  const second = {
    ...project,
    project_id: "project-two",
    publication_id: "project-pub-two",
    title: "Second delivery",
  };
  const next = {
    ...mapping,
    id: "root-two",
    project_publication_id: "project-pub-two",
    version_id: "second-v1",
    reason: "Second history",
  };
  vi.mocked(api.getCoverage).mockImplementation(async (_plan, root) => {
    if (root === "root")
      return new Promise((resolve) => {
        resolveOld = resolve;
      });
    return {
      items: root ? [next] : [mapping, next],
      current_version_id: next.version_id,
      is_reservation: false,
    };
  });
  render(
    <CoverageEditor
      plan={plan}
      available={[project, second]}
      onSaved={vi.fn()}
    />,
  );
  await waitFor(() => expect(resolveOld).toBeTypeOf("function"));
  fireEvent.change(
    screen.getByRole("combobox", { name: "Replacement project" }),
    { target: { value: "project-pub-two" } },
  );
  await screen.findByText("Second history");
  await act(async () =>
    resolveOld({
      items: [{ ...mapping, reason: "Late history" }],
      current_version_id: mapping.version_id,
      is_reservation: false,
    }),
  );
  expect(screen.queryByText("Late history")).not.toBeInTheDocument();
});
