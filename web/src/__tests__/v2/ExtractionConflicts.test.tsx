import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ExtractionConflicts } from "../../components/ExtractionConflicts";
import * as api from "../../api/extraction-conflicts";

vi.mock("../../api/extraction-conflicts", () => ({ getExtractionConflicts: vi.fn(), resolveExtractionConflict: vi.fn() }));
const conflict: api.ExtractionConflict = { field: "price", review_token: "source-review-token",
  current: { value: "250.00", provenance: "manual", status: "confirmed", page_ref: 1 },
  candidate: { value: "999.00", provenance: "extracted", status: "unconfirmed", page_ref: 2 } };
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getExtractionConflicts).mockResolvedValue({ items: [conflict] });
});

it("requires an explicit choice and reason, then saves the exact source token", async () => {
  const onResolved = vi.fn();
  vi.mocked(api.resolveExtractionConflict).mockResolvedValue({ items: [] });
  render(<ExtractionConflicts versionId="version-1" onResolved={onResolved} />);
  expect(await screen.findByText("250.00")).toBeVisible();
  expect(screen.getByText("999.00")).toBeVisible();
  const save = screen.getByRole("button", { name: "Save review" });
  expect(save).toBeDisabled();
  fireEvent.click(screen.getByRole("radio", { name: "Accept new extraction" }));
  expect(save).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Review reason"), { target: { value: "Checked the fee clause" } });
  fireEvent.click(save);
  await waitFor(() => expect(api.resolveExtractionConflict).toHaveBeenCalledWith("version-1", "price", {
    review_token: conflict.review_token, decision: "accept_candidate", reason: "Checked the fee clause" }));
  expect(onResolved).toHaveBeenCalledOnce();
  expect(await screen.findByText("No unresolved extraction conflicts")).toBeVisible();
});

it("preserves choice and reason on stale review and waits for explicit reload", async () => {
  vi.mocked(api.resolveExtractionConflict).mockRejectedValue(new Error("Extraction review changed; reload the source conflict"));
  render(<ExtractionConflicts versionId="version-1" onResolved={vi.fn()} />);
  fireEvent.click(await screen.findByRole("radio", { name: "Keep confirmed value" }));
  fireEvent.change(screen.getByLabelText("Review reason"), { target: { value: "Keep checked source" } });
  fireEvent.click(screen.getByRole("button", { name: "Save review" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Extraction review changed");
  expect(screen.getByLabelText("Review reason")).toHaveValue("Keep checked source");
  expect(screen.getByRole("radio", { name: "Keep confirmed value" })).toBeChecked();
  expect(api.getExtractionConflicts).toHaveBeenCalledTimes(1);
});

it("shows unavailable evidence as an error, never an empty successful queue", async () => {
  vi.mocked(api.getExtractionConflicts).mockRejectedValue(new Error("not authorised"));
  render(<ExtractionConflicts versionId="version-1" onResolved={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("not authorised");
  expect(screen.queryByText("No unresolved extraction conflicts")).not.toBeInTheDocument();
});

const sibling = { ...conflict, field: "currency", review_token: "currency-v1",
  current: { ...conflict.current, value: "USD" }, candidate: { ...conflict.candidate, value: "CAD" } };
function reviewForm(field: string) {
  const form = screen.getByRole("heading", { name: field, level: 3 }).closest("form");
  if (!form) throw new Error("Expected field review form");
  return { form, controls: within(form) };
}
function draftReview(field: string, reason: string) {
  const { controls } = reviewForm(field);
  fireEvent.click(controls.getByRole("radio", { name: "Accept new extraction" }));
  fireEvent.change(controls.getByLabelText("Review reason"), { target: { value: reason } });
}

it("invalidates a sibling draft when another save returns a changed review token", async () => {
  vi.mocked(api.getExtractionConflicts).mockResolvedValue({ items: [conflict, sibling] });
  const changed = { ...sibling, review_token: "currency-v2", candidate: { ...sibling.candidate, value: "EUR" } };
  vi.mocked(api.resolveExtractionConflict).mockResolvedValueOnce({ items: [changed] }).mockResolvedValue({ items: [] });
  render(<ExtractionConflicts versionId="version-1" onResolved={vi.fn()} />);
  await screen.findByText("CAD");
  draftReview("currency", "Reviewed CAD clause");
  draftReview("price", "Reviewed price clause");
  fireEvent.click(reviewForm("price").controls.getByRole("button", { name: "Save review" }));
  await screen.findByText("EUR");
  const { controls, form } = reviewForm("currency");
  expect(controls.getByRole("radio", { name: "Accept new extraction" })).not.toBeChecked();
  expect(controls.getByLabelText("Review reason")).toHaveValue("");
  expect(controls.getByRole("button", { name: "Save review" })).toBeDisabled();
  fireEvent.submit(form);
  expect(api.resolveExtractionConflict).toHaveBeenCalledTimes(1);
  draftReview("currency", "Reviewed new EUR evidence");
  fireEvent.click(controls.getByRole("button", { name: "Save review" }));
  await waitFor(() => expect(api.resolveExtractionConflict).toHaveBeenLastCalledWith("version-1", "currency", {
    review_token: "currency-v2", decision: "accept_candidate", reason: "Reviewed new EUR evidence" }));
});

it("preserves sibling choices and reasons while their exact review token is unchanged", async () => {
  vi.mocked(api.getExtractionConflicts).mockResolvedValue({ items: [conflict, sibling] });
  vi.mocked(api.resolveExtractionConflict).mockResolvedValue({ items: [sibling] });
  render(<ExtractionConflicts versionId="version-1" onResolved={vi.fn()} />);
  await screen.findByText("CAD");
  draftReview("currency", "Confirmed same CAD evidence");
  draftReview("price", "Checked price");
  fireEvent.click(reviewForm("price").controls.getByRole("button", { name: "Save review" }));
  await waitFor(() => expect(screen.queryByRole("heading", { name: "price", level: 3 })).not.toBeInTheDocument());
  expect(reviewForm("currency").controls.getByLabelText("Review reason")).toHaveValue("Confirmed same CAD evidence");
  expect(reviewForm("currency").controls.getByRole("radio", { name: "Accept new extraction" })).toBeChecked();
});

it("removes absent sibling drafts so a later same-token conflict starts unreviewed", async () => {
  vi.mocked(api.getExtractionConflicts).mockResolvedValueOnce({ items: [conflict, sibling] }).mockResolvedValue({ items: [sibling] });
  vi.mocked(api.resolveExtractionConflict).mockResolvedValue({ items: [] });
  render(<ExtractionConflicts versionId="version-1" onResolved={vi.fn()} />);
  await screen.findByText("CAD");
  draftReview("currency", "Draft before removal");
  draftReview("price", "Price reviewed");
  fireEvent.click(reviewForm("price").controls.getByRole("button", { name: "Save review" }));
  await screen.findByText("No unresolved extraction conflicts");
  fireEvent.click(screen.getByRole("button", { name: "Reload conflicts" }));
  await screen.findByText("CAD");
  expect(reviewForm("currency").controls.getByLabelText("Review reason")).toHaveValue("");
  expect(reviewForm("currency").controls.getByRole("button", { name: "Save review" })).toBeDisabled();
});

it("preserves an unchanged-token draft on reload but clears it when the version changes", async () => {
  const view = render(<ExtractionConflicts versionId="version-1" onResolved={vi.fn()} />);
  await screen.findByText("999.00");
  draftReview("price", "Same reviewed evidence");
  fireEvent.click(screen.getByRole("button", { name: "Reload conflicts" }));
  await waitFor(() => expect(api.getExtractionConflicts).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(screen.getByRole("button", { name: "Save review" })).toBeEnabled());
  expect(screen.getByLabelText("Review reason")).toHaveValue("Same reviewed evidence");
  view.rerender(<ExtractionConflicts versionId="version-2" onResolved={vi.fn()} />);
  await waitFor(() => expect(api.getExtractionConflicts).toHaveBeenLastCalledWith("version-2"));
  expect(screen.getByLabelText("Review reason")).toHaveValue("");
  expect(screen.getByRole("button", { name: "Save review" })).toBeDisabled();
});
