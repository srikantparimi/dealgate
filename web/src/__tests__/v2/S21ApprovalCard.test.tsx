import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import * as api from "../../api/client";
import { SowApprovalsPage } from "../../pages/v2/SowApprovals";

vi.mock("../../auth/AuthProvider", () => ({ useAuth: () => ({ user: { groups: ["SystemAdmin"] } }) }));

const pkg = (id: string) => ({ id, opportunity_id: "same-deal", sow_version_id: `version-${id}`,
  gm_model_id: `gm-${id}`, package_hash: `hash-${id}`, status: "pending_delivery_hr",
  submitted_at: "2026-10-01T00:00:00Z", submitted_by: "owner", released_at: null,
  voided_at: null, voided_reason: null, policy_version_id: null,
  approvals: [], sow_title: `SOW ${id}` }) as api.ApprovalPackage;

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "listAgreements").mockResolvedValue({ items: [] } as never);
  vi.spyOn(api, "listDraftSows").mockResolvedValue({ drafts: [] });
});

it("in-review deep link loads every page and renders exact package identities", async () => {
  vi.spyOn(api, "listApprovalPackages").mockImplementation(async filters => ({
    items: filters?.page === 2 ? [pkg("third")] : [pkg("first"), pkg("second")],
    total: 3, page: filters?.page ?? 1, size: 2, population_revision: "revision-a",
  }));
  render(<MemoryRouter initialEntries={["/sows?status=in_review"]}><SowApprovalsPage /></MemoryRouter>);
  await screen.findByTestId("sow-card-third");
  expect(screen.getAllByTestId(/^sow-card-/).map(el => el.getAttribute("data-testid"))).toEqual([
    "sow-card-first", "sow-card-second", "sow-card-third",
  ]);
  expect(api.listApprovalPackages).toHaveBeenCalledWith(expect.objectContaining({ status: "in_review", page: 2, population_revision: "revision-a" }));
  expect(api.listDraftSows).not.toHaveBeenCalled();
  expect(screen.getByRole("tab", { name: "In review" })).toHaveAttribute("aria-selected", "true");
});

it("changed pagination is an explicit error rather than a partial approval board", async () => {
  vi.spyOn(api, "listApprovalPackages").mockImplementation(async filters => ({
    items: [pkg(filters?.page === 2 ? "second" : "first")],
    total: filters?.page === 2 ? 4 : 2, page: filters?.page ?? 1, size: 1, population_revision: "revision-a",
  }));
  render(<MemoryRouter initialEntries={["/sows?status=in_review"]}><SowApprovalsPage /></MemoryRouter>);
  await screen.findByRole("alert");
  expect(screen.queryAllByTestId(/^sow-card-/)).toHaveLength(0);
  expect(screen.queryByText("No SOW packages yet.")).not.toBeInTheDocument();
});

it("equal-count membership changes cannot combine different page revisions", async () => {
  vi.spyOn(api, "listApprovalPackages").mockImplementation(async filters => ({
    items: [pkg(filters?.page === 2 ? "replacement" : "first")], total: 2,
    page: filters?.page ?? 1, size: 1, population_revision: filters?.page === 2 ? "revision-b" : "revision-a",
  }));
  render(<MemoryRouter initialEntries={["/sows?status=in_review&population_revision=revision-a"]}><SowApprovalsPage /></MemoryRouter>);
  await screen.findByRole("alert");
  expect(api.listApprovalPackages).toHaveBeenCalledWith(expect.objectContaining({ page: 1, population_revision: "revision-a" }));
  expect(screen.queryAllByTestId(/^sow-card-/)).toHaveLength(0);
});
