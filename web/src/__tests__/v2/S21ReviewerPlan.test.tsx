import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import * as api from "../../api/client";
import { ApprovalsTab } from "../../pages/v2/sow-workspace/ReviewStream";
import { SubmitApprovalDialog } from "../../pages/v2/sow-workspace/SubmitApprovalDialog";
import type { WorkspaceSnapshot } from "../../pages/v2/sow-workspace/readiness";
import * as loader from "../../pages/v2/sow-workspace/dataLoader";
import { SowWorkspacePage } from "../../pages/v2/SowWorkspace";

const snap = { deal: { id: "deal" }, sow: { id: "sow-version" }, gmModel: { id: "gm-version" }, approvalHistory: [], approvalPackage: null } as unknown as WorkspaceSnapshot;
const functions = ["delivery", "hr", "sales", "finance", "legal"];
const plan = { sow_version_id: "sow-version", sow_version: 3, gm_model_id: "gm-version", gm_version: 2,
  rows: functions.map(fn => ({ function: fn, label: fn === "delivery" ? "Delivery" : fn.toUpperCase(),
    approver_id: `${fn}-default`, due_date: "2026-11-03", use_sla: true,
    members: [{ id: `${fn}-default`, name: `${fn} reviewer` }, { id: `${fn}-alternative`, name: `${fn} alternative` }] })), executive: null } as unknown as api.SubmissionPlan;

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "getSubmissionPlan").mockResolvedValue(structuredClone(plan));
  vi.spyOn(api, "submitApprovalPackage").mockResolvedValue({} as never);
});

it("opens planned functions and eligible reviewers directly on unsubmitted Approvals", async () => {
  const refresh = vi.fn().mockResolvedValue(undefined);
  render(<MemoryRouter><ApprovalsTab snap={snap} canSubmit refresh={refresh} /></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "Planned reviewers" })).toBeVisible();
  await screen.findByRole("option", { name: "delivery alternative" });
  expect(screen.getAllByRole("combobox")).toHaveLength(5);
  expect(api.submitApprovalPackage).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Delivery approver"), { target: { value: "delivery-alternative" } });
  fireEvent.click(screen.getByRole("button", { name: "Confirm submission" }));
  await waitFor(() => expect(api.submitApprovalPackage).toHaveBeenCalledWith("deal", {
    sow_version_id: "sow-version", gm_model_id: "gm-version",
    assignments: Object.fromEntries(functions.map(fn => [fn, { approver_id: fn === "delivery" ? "delivery-alternative" : `${fn}-default`, due_date: "2026-11-03", use_sla: true }])),
  }));
  await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
});

it("does not expose a submission editor to a reader without submission authority", () => {
  render(<MemoryRouter><ApprovalsTab snap={snap} canSubmit={false} /></MemoryRouter>);
  expect(screen.queryByRole("button", { name: "Confirm submission" })).not.toBeInTheDocument();
  expect(api.getSubmissionPlan).not.toHaveBeenCalled();
});

it("retains selections and presents server rejection without claiming submission", async () => {
  const refresh = vi.fn();
  vi.mocked(api.submitApprovalPackage).mockRejectedValue(new api.ApiError(422, "Reviewer is no longer eligible"));
  render(<MemoryRouter><ApprovalsTab snap={snap} canSubmit refresh={refresh} /></MemoryRouter>);
  await screen.findByRole("option", { name: "delivery alternative" });
  fireEvent.change(screen.getByLabelText("Delivery approver"), { target: { value: "delivery-alternative" } });
  fireEvent.click(screen.getByRole("button", { name: "Confirm submission" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Reviewer is no longer eligible");
  expect(screen.getByLabelText("Delivery approver")).toHaveValue("delivery-alternative");
  expect(refresh).not.toHaveBeenCalled();
});

it("keeps the existing dialog on the same real plan and submission contract", async () => {
  const submitted = vi.fn(), close = vi.fn();
  render(<SubmitApprovalDialog id="deal" open onOpenChange={close} onSubmitted={submitted} />);
  expect(screen.getByRole("dialog", { name: "Submit for approval" })).toBeVisible();
  await screen.findByRole("option", { name: "delivery reviewer" });
  fireEvent.click(screen.getByRole("button", { name: "Confirm submission" }));
  await waitFor(() => expect(submitted).toHaveBeenCalledTimes(1));
  expect(close).toHaveBeenCalledWith(false);
  expect(api.submitApprovalPackage).toHaveBeenCalledTimes(1);
});

it("a submission resolving during another workspace load cannot refresh the old route", async () => {
  const workspace = (id: string) => ({ ...snap, deal: { id, owner_id: "owner" },
    sow: { id: `${id}-sow`, extracted_fields: { sow_title: { value: `Workspace ${id}` } } },
    gmModel: { id: `${id}-gm`, resource_lines: [], cost_lines: [], completeness_issues: [], computed: { complete: true, policy: { requires_ceo: false } } }, agreements: [], signedSow: null } as unknown as WorkspaceSnapshot);
  let finishB!: (value: Awaited<ReturnType<typeof loader.loadWorkspace>>) => void;
  const pendingB = new Promise<Awaited<ReturnType<typeof loader.loadWorkspace>>>(resolve => { finishB = resolve; });
  vi.spyOn(loader, "loadWorkspace").mockImplementation(id => id === "b" ? pendingB : Promise.resolve({ snap: workspace("a"), degradedEndpoints: [] }));
  vi.spyOn(api, "getMe").mockResolvedValue({ id: "owner", name: "Owner", email: "owner@example.test", groups: ["Sales"] });
  let finishSubmit!: (value: api.ApprovalPackage) => void;
  vi.mocked(api.submitApprovalPackage).mockReturnValue(new Promise(resolve => { finishSubmit = resolve; }));
  render(<MemoryRouter initialEntries={["/sows/a/approvals"]}><Link to="/sows/b/approvals">Other workspace</Link><Routes><Route path="/sows/:id/:tab" element={<SowWorkspacePage />} /></Routes></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: "Confirm submission" }));
  await waitFor(() => expect(api.submitApprovalPackage).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("link", { name: "Other workspace" }));
  await waitFor(() => expect(loader.loadWorkspace).toHaveBeenCalledWith("b"));
  const reads = vi.mocked(loader.loadWorkspace).mock.calls.length;
  await act(async () => finishSubmit({} as never));
  expect(loader.loadWorkspace).toHaveBeenCalledTimes(reads);
  await act(async () => finishB({ snap: workspace("b"), degradedEndpoints: [] }));
  await waitFor(() => expect(api.getSubmissionPlan).toHaveBeenLastCalledWith("b"));
  expect(screen.getByRole("heading", { name: "Workspace b" })).toBeVisible();
});

it("a matching in-review package suppresses another submission editor", () => {
  const current = { ...snap, approvalHistory: [{ id: "package", sow_version_id: "sow-version", gm_model_id: "gm-version",
    package_hash: "hash", status: "pending_delivery_hr", approvals: [], assignments: [] }] } as unknown as WorkspaceSnapshot;
  render(<MemoryRouter><ApprovalsTab snap={current} canSubmit /></MemoryRouter>);
  expect(screen.queryByRole("region", { name: "Planned reviewers" })).not.toBeInTheDocument();
  expect(api.getSubmissionPlan).not.toHaveBeenCalled();
});

it("shows approved, active and queued review status after submission", () => {
  const current = {
    ...snap,
    approvalHistory: [{
      id: "package",
      sow_version_id: "sow-version",
      gm_model_id: "gm-version",
      package_hash: "0123456789abcdef",
      status: "pending_delivery_hr",
      submitted_at: "2026-10-07T08:00:00Z",
      submitted_by_name: "Account owner",
      approvals: [{
        id: "delivery-decision",
        function: "delivery",
        decision: "approve",
        reason: "Staffing and delivery plan confirmed",
        approver_name: "Delivery reviewer",
        decided_at: "2026-10-07T09:00:00Z",
      }],
      assignments: [
        { function: "delivery", approver_name: "Delivery reviewer", due_date: "2026-10-09", active: false, blocked: false, can_decide: false },
        { function: "hr", approver_name: "HR reviewer", due_date: "2026-10-09", active: true, blocked: false, can_decide: false },
        { function: "finance", approver_name: "Finance reviewer", due_date: "2026-10-09", active: false, blocked: false, can_decide: false },
        { function: "legal", approver_name: "Legal reviewer", due_date: "2026-10-09", active: false, blocked: false, can_decide: false },
      ],
      floors: { requires_ceo: false },
    }],
  } as unknown as WorkspaceSnapshot;

  render(<MemoryRouter><ApprovalsTab snap={current} canSubmit /></MemoryRouter>);

  expect(screen.getByText("Delivery · Approved")).toBeVisible();
  expect(screen.getByText("HR · Pending with HR reviewer")).toBeVisible();
  expect(screen.getByText("Finance · Queued for Finance reviewer")).toBeVisible();
  expect(screen.getByText("Legal · Queued for Legal reviewer")).toBeVisible();
  expect(screen.getByText("pending delivery hr")).toBeVisible();
});

it("an older plan response cannot replace the new source version's plan", async () => {
  let release!: (value: api.SubmissionPlan) => void;
  vi.mocked(api.getSubmissionPlan).mockReturnValueOnce(new Promise(resolve => { release = resolve; }));
  vi.mocked(api.getSubmissionPlan).mockResolvedValueOnce({ ...plan, gm_model_id: "new-gm", gm_version: 3 });
  const { rerender } = render(<MemoryRouter><ApprovalsTab snap={snap} canSubmit /></MemoryRouter>);
  const newer = { ...snap, gmModel: { ...snap.gmModel, id: "new-gm" } } as WorkspaceSnapshot;
  rerender(<MemoryRouter><ApprovalsTab snap={newer} canSubmit /></MemoryRouter>);
  await screen.findByText("Frozen package: SOW v3 · GM v3");
  await act(async () => release(plan));
  expect(screen.getByText("Frozen package: SOW v3 · GM v3")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Confirm submission" }));
  await waitFor(() => expect(api.submitApprovalPackage).toHaveBeenCalledWith("deal", expect.objectContaining({ gm_model_id: "new-gm" })));
});
