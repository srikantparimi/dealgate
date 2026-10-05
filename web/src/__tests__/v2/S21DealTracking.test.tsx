import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import * as api from "../../api/client";
import { DealDetailPage } from "../../pages/v2/DealDetail";

vi.mock("../../ui-v2/WatchStar", () => ({ WatchStar: () => null }));

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "getPipelineOpportunity").mockResolvedValue({ opportunity_id: "deal", name: "Tracking deal", attention_flags: [], sow_count: 0 } as never);
  vi.spyOn(api, "getPipelineFacets").mockResolvedValue({ owners: [{ id: "crm-owner", name: "CRM owner", email: null }], business_units: [] });
  vi.spyOn(api, "getDealTimeline").mockResolvedValue({ items: [] });
  vi.spyOn(api, "listNextActions").mockResolvedValue({ items: [], can_create: true, assignees: [{ id: "registered-user", name: "Registered user" }] } as never);
  vi.spyOn(api, "listDealComments").mockResolvedValue({ items: [], latest: null, can_create: true } as never);
});

function openDeal() {
  render(<MemoryRouter initialEntries={["/deals/deal"]}><Link to="/deals/other">Other deal</Link><Routes><Route path="/deals/:id" element={<DealDetailPage />} /></Routes></MemoryRouter>);
}

it("offers comment and action creation on the deal using registered assignees", async () => {
  openDeal();
  fireEvent.click(await screen.findByRole("button", { name: "Add comment" }));
  expect(screen.getByLabelText("Comment")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Add action" }));
  expect(screen.getByLabelText("Action title")).toBeVisible();
  const select = screen.getByLabelText("Assignee");
  expect(within(select).getByRole("option", { name: "Registered user" })).toHaveValue("registered-user");
  expect(within(select).queryByRole("option", { name: "CRM owner" })).not.toBeInTheDocument();
});

it("shows CRM attribution and escaped content with no mutation controls", async () => {
  const note = { id: "crm-note", body: "<script>bad()</script>", source: "hubspot_note", author_name_fallback: "CRM Author", created_at: "2026-10-02T12:00:00Z", can_edit: false };
  vi.mocked(api.listDealComments).mockResolvedValue({ items: [note], latest: note, can_create: false } as never);
  openDeal();
  const region = await screen.findByRole("region", { name: "Comments" });
  expect(within(region).getByText("CRM Author")).toBeVisible();
  expect(within(region).getByText("HubSpot note")).toBeVisible();
  expect(within(region).getByText("<script>bad()</script>")).toBeVisible();
  expect(region.querySelector("script")).toBeNull();
  expect(within(region).queryByRole("button", { name: /Edit|Pin|Delete/ })).not.toBeInTheDocument();
});

it("submits creation and refreshes the deal activity without changing context", async () => {
  vi.spyOn(api, "createDealComment").mockResolvedValue({} as never);
  vi.spyOn(api, "createNextAction").mockResolvedValue({} as never);
  openDeal();
  fireEvent.click(await screen.findByRole("button", { name: "Add comment" }));
  fireEvent.change(screen.getByLabelText("Comment"), { target: { value: "Client confirmed timing" } });
  fireEvent.click(screen.getByRole("button", { name: "Save comment" }));
  await waitFor(() => expect(api.createDealComment).toHaveBeenCalledWith("deal", "Client confirmed timing"));
  await waitFor(() => expect(api.getDealTimeline).toHaveBeenCalledTimes(2));
  fireEvent.click(screen.getByRole("button", { name: "Add action" }));
  fireEvent.change(screen.getByLabelText("Action title"), { target: { value: "Confirm delivery" } });
  fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-11-02" } });
  fireEvent.click(screen.getByRole("button", { name: "Save action" }));
  await waitFor(() => expect(api.createNextAction).toHaveBeenCalledWith({ opportunity_id: "deal", title: "Confirm delivery", assignee_user_id: "registered-user", due_date: "2026-11-02" }));
  await waitFor(() => expect(api.getDealTimeline).toHaveBeenCalledTimes(3));
  expect(screen.getByTestId("deal-heading")).toHaveTextContent("Tracking deal");
});

it("retains an unsaved comment after conflict and never retries against a new revision", async () => {
  const row = { id: "comment", body: "Original", source: "internal", author_name: "Author", created_at: "2026-10-02T12:00:00Z", revision: "revision-1", can_edit: true };
  vi.mocked(api.listDealComments).mockResolvedValue({ items: [row], latest: row, can_create: true } as never);
  vi.spyOn(api, "patchDealComment").mockRejectedValue(new api.ApiError(409, "stale"));
  openDeal();
  fireEvent.click(await screen.findByRole("button", { name: "Edit comment" }));
  fireEvent.change(screen.getByLabelText("Comment"), { target: { value: "Unsaved wording" } });
  fireEvent.click(screen.getByRole("button", { name: "Save comment" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("This record changed");
  expect(screen.getByLabelText("Comment")).toHaveValue("Unsaved wording");
  expect(api.patchDealComment).toHaveBeenCalledTimes(1);
  expect(api.patchDealComment).toHaveBeenCalledWith("comment", { expected_revision: "revision-1", body: "Unsaved wording" });
  vi.mocked(api.listDealComments).mockResolvedValue({ items: [{ ...row, body: "Other person's change", revision: "revision-2" }], latest: row } as never);
  fireEvent.click(screen.getByRole("button", { name: "Reload tracking" }));
  await screen.findByText("Other person's change");
  expect(api.patchDealComment).toHaveBeenCalledTimes(1);
  expect(screen.getByLabelText("Comment")).toHaveValue("Unsaved wording");
});

it("includes displayed revisions when pinning comments and completing actions", async () => {
  const comment = { id: "comment", body: "Comment", source: "internal", author_name: "Author", created_at: "2026-10-02T12:00:00Z", revision: "comment-v1", can_edit: true, pinned: false };
  const action = { id: "action", title: "Follow up", owner_user_id: "registered-user", status: "open", revision: "action-v1", can_edit: true };
  vi.mocked(api.listDealComments).mockResolvedValue({ items: [comment], latest: comment } as never);
  vi.mocked(api.listNextActions).mockResolvedValue({ items: [action], assignees: [{ id: "registered-user", name: "Registered user" }] } as never);
  vi.spyOn(api, "patchDealComment").mockResolvedValue({ ...comment, pinned: true } as never);
  vi.spyOn(api, "patchNextAction").mockResolvedValue({ ...action, status: "complete" } as never);
  openDeal();
  fireEvent.click(await screen.findByRole("button", { name: "Pin comment" }));
  await waitFor(() => expect(api.patchDealComment).toHaveBeenCalledWith("comment", { expected_revision: "comment-v1", pinned: true }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Mark complete" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "Mark complete" }));
  await waitFor(() => expect(api.patchNextAction).toHaveBeenCalledWith("action", { expected_revision: "action-v1", status: "complete" }));
});

it("a delayed post-mutation refresh cannot put the old deal's controls under a new heading", async () => {
  vi.spyOn(api, "createDealComment").mockResolvedValue({} as never);
  openDeal();
  fireEvent.click(await screen.findByRole("button", { name: "Add comment" }));
  let release!: (value: api.DealCommentList) => void;
  const held = new Promise<api.DealCommentList>(resolve => { release = resolve; });
  vi.mocked(api.listDealComments).mockImplementation(id => id === "deal" ? held : Promise.resolve({ items: [], latest: null }));
  fireEvent.change(screen.getByLabelText("Comment"), { target: { value: "Old deal text" } });
  fireEvent.click(screen.getByRole("button", { name: "Save comment" }));
  await waitFor(() => expect(api.listDealComments).toHaveBeenCalledTimes(2));
  vi.mocked(api.getPipelineOpportunity).mockResolvedValue({ opportunity_id: "other", name: "Other deal heading", attention_flags: [], sow_count: 0 } as never);
  fireEvent.click(screen.getByRole("link", { name: "Other deal" }));
  await screen.findByRole("heading", { name: "Other deal heading" });
  await act(async () => release({ items: [{ id: "stale", body: "Old deal text", source: "internal", can_edit: true, created_at: "2026-10-02T12:00:00Z" }], latest: null } as never));
  expect(screen.queryByText("Old deal text")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Edit comment" })).not.toBeInTheDocument();
});

it("a mutation that finishes after navigation cannot start an old-deal refresh", async () => {
  let finish!: (value: api.DealCommentRow) => void;
  vi.spyOn(api, "createDealComment").mockReturnValue(new Promise(resolve => { finish = resolve; }));
  openDeal();
  fireEvent.click(await screen.findByRole("button", { name: "Add comment" }));
  fireEvent.change(screen.getByLabelText("Comment"), { target: { value: "Late mutation" } });
  fireEvent.click(screen.getByRole("button", { name: "Save comment" }));
  await waitFor(() => expect(api.createDealComment).toHaveBeenCalled());
  vi.mocked(api.getPipelineOpportunity).mockResolvedValue({ opportunity_id: "other", name: "Other deal heading", attention_flags: [], sow_count: 0 } as never);
  fireEvent.click(screen.getByRole("link", { name: "Other deal" }));
  await screen.findByRole("heading", { name: "Other deal heading" });
  const reads = vi.mocked(api.listDealComments).mock.calls.length;
  await act(async () => finish({} as never));
  expect(api.listDealComments).toHaveBeenCalledTimes(reads);
});
