import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import * as api from "../../api/client";
import { ProjectsActualsPage } from "../../pages/v2/ProjectsActuals";

it("shows released staffing and approved versus forecast GM without actuals controls", async () => {
  vi.spyOn(api, "listProjects").mockResolvedValue({
    items: [
      {
        id: "opp",
        package_id: "pkg",
        gm_model_id: "gm",
        title: "Reporting modernization",
        client_name: "Example company",
        owner_name: "Morgan",
        sow_version: 2,
        gm_version: 3,
        released_at: "2026-09-20",
        term_end: "2026-12-31",
        approved: { us: "0.40", india: null },
        forecast: { us: "0.38", india: null, as_of: "2026-09-25" },
        resources: [
          {
            id: "r",
            name: "Dana",
            role: "Engineer",
            location: "US",
            allocation: "0.5",
            hours: "400",
            start_date: "2026-10-01",
            end_date: "2026-12-31",
          },
        ],
      },
    ],
  });
  render(
    <MemoryRouter>
      <ProjectsActualsPage />
    </MemoryRouter>,
  );
  expect(
    await screen.findByText("Reporting modernization"),
  ).toBeInTheDocument();
  expect(screen.getByText("Dana")).toBeInTheDocument();
  expect(screen.getByText("40.0%")).toBeInTheDocument();
  expect(screen.getByText("38.0%")).toBeInTheDocument();
  expect(
    screen.queryByText(/Import actuals|Reconciliation/),
  ).not.toBeInTheDocument();
});

it("labels retained projects without linking to a deleted SOW", async () => {
  vi.spyOn(api, "listProjects").mockResolvedValue({ items: [{
    id: "retained", source_deleted: true, package_id: null, gm_model_id: null,
    title: "Retained delivery", client_name: "Example company", owner_name: "Source removed",
    sow_version: null, gm_version: null, released_at: "2026-10-01", term_end: null,
    approved: { us: null, india: null }, forecast: { us: null, india: null, as_of: null }, resources: [],
  }] });
  render(<MemoryRouter><ProjectsActualsPage /></MemoryRouter>);
  expect(await screen.findByText("Source SOW deleted; project retained")).toBeVisible();
  expect(screen.queryByRole("link", { name: "Retained delivery" })).not.toBeInTheDocument();
});
