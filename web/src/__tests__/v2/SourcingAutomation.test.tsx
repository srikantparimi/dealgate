import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SourcingAutomation } from "../../components/SourcingAutomation";
import * as api from "../../api/sourcing-automation";

vi.mock("../../api/sourcing-automation", () => ({ getAutomationRule: vi.fn(), saveAutomationRule: vi.fn(),
  getAutomationJobs: vi.fn(), getAutomationHistory: vi.fn(), retryAutomationJob: vi.fn() }));
const initial: api.AutomationRule = { state: "unconfigured", domain: "sourcing_refresh", enabled: false,
  id: null, revision: null, source_scope: "authorized_sources" };
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getAutomationRule).mockResolvedValue(initial);
  vi.mocked(api.getAutomationJobs).mockResolvedValue({ items: [], last_success_at: null });
  vi.mocked(api.getAutomationHistory).mockResolvedValue({ items: [], current_version_id: null });
});

describe("Sourcing automation controls", () => {
  it("starts disabled and requires an explicit reason before saving", async () => {
    render(<SourcingAutomation />);
    const toggle = await screen.findByRole("checkbox", { name: "Automatic sourcing refresh" });
    await waitFor(() => expect(toggle).not.toBeDisabled());
    expect(toggle).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Save automation" })).toBeDisabled();
    fireEvent.click(toggle);
    fireEvent.change(screen.getByLabelText("Automation change reason"), { target: { value: "Reviewed source processing" } });
    vi.mocked(api.saveAutomationRule).mockResolvedValue({ ...initial, id: "rule-1", revision: 1, enabled: true, state: "configured" });
    fireEvent.click(screen.getByRole("button", { name: "Save automation" }));
    await waitFor(() => expect(api.saveAutomationRule).toHaveBeenCalledWith({ expected_version_id: null,
      enabled: true, reason: "Reviewed source processing", request_key: expect.any(String) }));
    expect(await screen.findByText("Automation revision 1 saved")).toBeVisible();
  });

  it("preserves the draft and original CAS after a conflicting save", async () => {
    vi.mocked(api.getAutomationRule).mockResolvedValue({ ...initial, id: "rule-1", revision: 1, state: "configured" });
    vi.mocked(api.saveAutomationRule).mockRejectedValue(new Error("Automation rule changed; reload before saving"));
    render(<SourcingAutomation />);
    const toggle = await screen.findByRole("checkbox", { name: "Automatic sourcing refresh" });
    await waitFor(() => expect(toggle).not.toBeDisabled());
    fireEvent.click(toggle);
    fireEvent.change(screen.getByLabelText("Automation change reason"), { target: { value: "Keep this reason" } });
    fireEvent.click(screen.getByRole("button", { name: "Save automation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Automation rule changed");
    expect(toggle).toBeChecked();
    expect(screen.getByLabelText("Automation change reason")).toHaveValue("Keep this reason");
    expect(api.saveAutomationRule).toHaveBeenCalledWith(expect.objectContaining({ expected_version_id: "rule-1" }));
    expect(api.getAutomationRule).toHaveBeenCalledTimes(1);
  });

  it("does not enable settings after a failed load", async () => {
    vi.mocked(api.getAutomationRule).mockRejectedValue(new Error("Unavailable"));
    render(<SourcingAutomation />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unavailable");
    expect(screen.getByRole("checkbox", { name: "Automatic sourcing refresh" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save automation" })).toBeDisabled();
  });

  it("shows persisted job failure and submits a reasoned retry with exact attempts", async () => {
    const job: api.AutomationJob = { id: "job-1", status: "failed", attempts: 2, source_id: "source-1",
      source_version: "version-1", event_key: "source-event", rule_version_id: "rule-1", next_attempt_at: "2026-10-02T16:00:00Z",
      completed_at: null, created_at: "2026-10-02T15:00:00Z", last_error: "Source refresh failed", result_version_id: null, can_retry: true };
    vi.mocked(api.getAutomationJobs).mockResolvedValue({ items: [job], last_success_at: null });
    vi.mocked(api.retryAutomationJob).mockResolvedValue({ ...job, status: "pending", can_retry: false });
    render(<SourcingAutomation />);
    expect(await screen.findByText("Source refresh failed")).toBeVisible();
    expect(screen.getByRole("button", { name: "Retry job-1" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Retry reason job-1"), { target: { value: "Inputs repaired" } });
    fireEvent.click(screen.getByRole("button", { name: "Retry job-1" }));
    await waitFor(() => expect(api.retryAutomationJob).toHaveBeenCalledWith("job-1", { expected_attempts: 2, reason: "Inputs repaired" }));
    expect(await screen.findByText("Job queued")).toBeVisible();
  });
});
