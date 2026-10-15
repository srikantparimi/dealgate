// S23-PL2 F3 · the freshness line in its three states with the prototype's
// copy, the "Sync health" panel (the last attempt's errors in words, never the
// server's reasons with their HubSpot ids), and the SystemAdmin "Run sync now":
// "Sync started", the server's latest attempt read at the click as the
// baseline, polling sync-health every 5 s, and never treating CloudFront's
// 30-second timeout (or a network error / abort) as a failure.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as appConfig from "../../api/appConfig";
import * as api from "../../api/client";
import * as wsApi from "../../api/pipelineWorkspace";
import type { Freshness } from "../../api/pipelineWorkspace";
import { PipelinePage } from "../../pages/v2/Pipeline";
import { FreshnessLine } from "../../pages/v2/pipeline/FreshnessLine";
import { SyncHealthPanel } from "../../pages/v2/pipeline/SyncHealthPanel";
import { renderAt, tonight } from "./S23PipelineShellFixtures";

vi.mock("../../pages/v2/pipeline/RecordsPanel", async () => ({
  RecordsPanel: (await import("./S23PipelineShellFakes")).FakeRecordsPanel,
}));
vi.mock("../../pages/v2/pipeline/DealPreview", async () => ({
  DealPreview: (await import("./S23PipelineShellFakes")).FakeDealPreview,
}));
vi.mock("../../pages/v2/pipeline/ClientPreview", async () => ({
  ClientPreview: (await import("./S23PipelineShellFakes")).FakeClientPreview,
}));

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

/**
 * After a click on "Run sync now": lets the sync-health read made at the click answer and
 * React apply "Sync started" (which schedules the first poll), as the browser does at once.
 * Inside one act() React would hold that update until the act ends, after the timers ran.
 */
async function settleClick() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

// The prototype's clock: 9:00 AM PT on Oct 14, 2026.
const NOW = new Date("2026-10-14T16:00:00Z");

function freshness(overrides: Partial<Freshness>): Freshness {
  return {
    state: "fresh",
    last_success_at: "2026-10-14T09:10:00Z",
    last_attempt_at: "2026-10-14T09:10:00Z",
    last_status: "ok",
    schedule: "nightly",
    errors: [],
    error_count: 0,
    recovery: { available: true, admin_only: true },
    ...overrides,
  };
}

const FRESH = freshness({});
const STALE = freshness({
  state: "stale",
  last_success_at: "2026-10-12T09:10:00Z",
  last_attempt_at: "2026-10-12T09:10:00Z",
});
const FAILED = freshness({
  state: "failed",
  last_success_at: "2026-10-13T09:10:00Z",
  last_attempt_at: "2026-10-14T09:10:00Z",
  last_status: "failed",
  error_count: 1,
  // As hubspot_backfill.py records an UnmappedStageError: "deal: " + "stage {stage id} not mapped".
  errors: [{ hubspot_id: "77001234", reason: "deal: stage 1038193692 not mapped" }],
});

function line(f: Freshness) {
  const onInspect = vi.fn();
  const { container } = render(<FreshnessLine freshness={f} onInspect={onInspect} now={NOW} />);
  return { text: container.textContent ?? "", onInspect };
}

describe("F3 · the freshness line", () => {
  it("fresh: quiet, names the last successful sync, its age and the schedule", () => {
    const { text } = line(FRESH);
    expect(text).toContain("Deals synced Oct 14, 2:10 AM PT · 7 h ago · nightly sync");
    expect(screen.getByRole("button", { name: "Sync details" })).toBeInTheDocument();
  });

  it("stale: says how old the data is and to check sync health", () => {
    const { text } = line(STALE);
    expect(text).toContain(
      "Deal data is 2 days old. Last successful sync Oct 12, 2:10 AM PT. Check sync health before relying on these figures.",
    );
    expect(screen.getByRole("button", { name: "Inspect sync" })).toHaveTextContent("Inspect sync →");
  });

  it("failed: names the failed attempt and the last good sync", () => {
    const { text, onInspect } = line(FAILED);
    expect(text).toContain(
      "The last sync failed (Oct 14, 2:10 AM PT). Showing deals from the last good sync, Oct 13, 2:10 AM PT.",
    );
    fireEvent.click(screen.getByRole("button", { name: "Inspect sync" }));
    expect(onInspect).toHaveBeenCalledTimes(1);
  });

  it("a partly failed run reads as failed (the server's state), and no successful sync says so", () => {
    const { text } = line(freshness({ state: "failed", last_status: "partial", last_success_at: null }));
    expect(text).toContain("The last sync failed (Oct 14, 2:10 AM PT). No successful deal sync is recorded yet.");
  });

  it("never measures the intake heartbeat: the page reads freshness only from the workspace answer", async () => {
    vi.spyOn(api, "getMe").mockResolvedValue({ id: "u", email: "e2e@example.com", name: "E2E", groups: ["Sales"] });
    vi.spyOn(appConfig, "useAppConfig").mockReturnValue({ hubspotPortalId: null, loading: false });
    vi.spyOn(wsApi, "listWorkspaceViews").mockResolvedValue([]);
    vi.spyOn(wsApi, "listWorkspaceGroups").mockResolvedValue([]);
    vi.spyOn(wsApi, "getWorkspace").mockResolvedValue(tonight({ freshness: STALE }));
    const syncStatus = vi.spyOn(api, "getSyncStatus");
    renderAt(<PipelinePage />);
    expect(await screen.findByText("Deal data is", { exact: false })).toBeInTheDocument();
    expect(syncStatus).not.toHaveBeenCalled();
  });
});

describe("F3 · the Sync health panel", () => {
  function setup(f: Freshness, groups: string[]) {
    vi.spyOn(api, "getMe").mockResolvedValue({ id: "user-1", email: "e2e@example.com", name: "E2E", groups });
    vi.spyOn(appConfig, "useAppConfig").mockReturnValue({ hubspotPortalId: "1234567", loading: false });
    vi.spyOn(wsApi, "listWorkspaceViews").mockResolvedValue([]);
    vi.spyOn(wsApi, "listWorkspaceGroups").mockResolvedValue([]);
    vi.spyOn(wsApi, "getWorkspace").mockResolvedValue(tonight({ freshness: f }));
    renderAt(<PipelinePage />);
  }

  it("opens from the line and explains the failed state with reasons (never the HubSpot id)", async () => {
    setup(FAILED, ["Sales"]);
    fireEvent.click(await screen.findByRole("button", { name: "Inspect sync" }));
    const panel = await screen.findByRole("dialog", { name: "Sync health" });
    const p = within(panel);
    expect(p.getByText("Trust & freshness")).toBeInTheDocument();
    expect(p.getByText("Last successful sync").nextSibling).toHaveTextContent("Oct 13, 2:10 AM PT");
    expect(p.getByText("Last attempt").nextSibling).toHaveTextContent("Oct 14, 2:10 AM PT");
    expect(p.getByText("Last attempt result").nextSibling).toHaveTextContent("Failed");
    expect(p.getByText("Schedule").nextSibling).toHaveTextContent("Nightly");
    expect(p.getByText("HubSpot returned a stage the mapping does not know (1 deal).")).toBeInTheDocument();
    expect(panel).not.toHaveTextContent("77001234");
    expect(panel).not.toHaveTextContent("1038193692");
    expect(panel).not.toHaveTextContent("not mapped");
    expect(p.getByRole("heading", { name: "How to read this page" })).toBeInTheDocument();
    expect(panel).toHaveTextContent(
      "The line at the top of Pipeline shows the last successful sync of deals, not the last attempt.",
    );
    expect(p.getByText("successful").tagName).toBe("EM");
    // Not an administrator: no run control.
    expect(p.queryByRole("button", { name: "Run sync now" })).toBeNull();
  });

  it("a partly failed attempt reads 'Partly failed'; a fresh one 'Succeeded'", async () => {
    setup(freshness({ state: "failed", last_status: "partial", error_count: 3, errors: [] }), ["Sales"]);
    fireEvent.click(await screen.findByRole("button", { name: "Inspect sync" }));
    const panel = await screen.findByRole("dialog", { name: "Sync health" });
    expect(within(panel).getByText("Last attempt result").nextSibling).toHaveTextContent("Partly failed");
    expect(panel).toHaveTextContent("3 errors in the last attempt.");
  });

  it("Escape closes the panel and focus returns to the link that opened it", async () => {
    setup(FRESH, ["Sales"]);
    const link = await screen.findByRole("button", { name: "Sync details" });
    link.focus();
    fireEvent.click(link);
    const panel = await screen.findByRole("dialog", { name: "Sync health" });
    expect(within(panel).getByText("Last attempt result").nextSibling).toHaveTextContent("Succeeded");
    fireEvent.keyDown(panel, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(link).toHaveFocus();
  });

  it.each([
    ["a 504 from CloudFront", new api.ApiError(504, null, "API error 504")],
    ["a 502", new api.ApiError(502, null, "API error 502")],
    ["a 503", new api.ApiError(503, null, "API error 503")],
    ["a network error", new TypeError("Failed to fetch")],
    ["an aborted request", new DOMException("The operation was aborted.", "AbortError")],
  ])("Run sync now: %s is not a failure; polling sync-health decides, then the page refetches", async (_label, err) => {
    setup(FRESH, ["SystemAdmin"]);
    fireEvent.click(await screen.findByRole("button", { name: "Sync details" }));
    const panel = await screen.findByRole("dialog", { name: "Sync health" });
    const run = await within(panel).findByRole("button", { name: "Run sync now" });

    vi.useFakeTimers();
    const clickedAt = Date.now();
    const trigger = vi.spyOn(api, "triggerHubspotSync").mockRejectedValue(err);
    const health = vi
      .spyOn(api, "getSyncHealth")
      .mockResolvedValueOnce(FRESH) // read at the click: the baseline
      .mockResolvedValueOnce(FRESH) // first poll: nothing newer yet
      .mockResolvedValue(
        freshness({
          last_success_at: new Date(clickedAt + 60_000).toISOString(),
          last_attempt_at: new Date(clickedAt + 60_000).toISOString(),
        }),
      );
    const before = vi.mocked(wsApi.getWorkspace).mock.calls.length;

    fireEvent.click(run);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(trigger).toHaveBeenCalledTimes(1);
    expect(within(panel).getByRole("status")).toHaveTextContent("Sync started");
    expect(panel).not.toHaveTextContent("did not start");
    expect(run).toBeDisabled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(health).toHaveBeenCalledTimes(2);
    expect(within(panel).getByRole("status")).toHaveTextContent("Sync started");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(health).toHaveBeenCalledTimes(3);
    expect(within(panel).getByRole("status")).toHaveTextContent("Sync finished · Succeeded");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(vi.mocked(wsApi.getWorkspace).mock.calls.length).toBe(before + 1);
    // No more polling once the new attempt is in.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000);
    });
    expect(health).toHaveBeenCalledTimes(3);
  });

  it("Run sync now: a refusal (403) is shown and nothing is polled", async () => {
    setup(STALE, ["SystemAdmin"]);
    fireEvent.click(await screen.findByRole("button", { name: "Inspect sync" }));
    const panel = await screen.findByRole("dialog", { name: "Sync health" });
    const run = await within(panel).findByRole("button", { name: "Run sync now" });
    vi.useFakeTimers();
    vi.spyOn(api, "triggerHubspotSync").mockRejectedValue(new api.ApiError(403, null, "SystemAdmin role required"));
    const health = vi.spyOn(api, "getSyncHealth").mockResolvedValue(STALE);
    fireEvent.click(run);
    // The refusal arrives at once; let React apply it before time moves on.
    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(within(panel).getByRole("status")).toHaveTextContent("The sync did not start: SystemAdmin role required");
    // Only the read at the click (the baseline); nothing is polled.
    expect(health).toHaveBeenCalledTimes(1);
    expect(run).toBeEnabled();
  });

  it("Run sync now: gives up after 10 minutes without a newer attempt, without calling it a failure", async () => {
    setup(FRESH, ["SystemAdmin"]);
    fireEvent.click(await screen.findByRole("button", { name: "Sync details" }));
    const panel = await screen.findByRole("dialog", { name: "Sync health" });
    const run = await within(panel).findByRole("button", { name: "Run sync now" });
    vi.useFakeTimers();
    vi.spyOn(api, "triggerHubspotSync").mockReturnValue(new Promise(() => undefined));
    const health = vi.spyOn(api, "getSyncHealth").mockResolvedValue(FRESH);
    fireEvent.click(run);
    await settleClick();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10 * 60_000 + 5_000);
    });
    expect(health.mock.calls.length).toBeGreaterThanOrEqual(119);
    expect(within(panel).getByRole("status")).toHaveTextContent(
      "No result after 10 minutes. The sync may still be running; open this panel again later.",
    );
    const calls = health.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(health.mock.calls.length).toBe(calls);
  });
});

describe("F3 · the panel's error lines are user copy, never the server's text", () => {
  // Reasons exactly as the server records them (hubspot_backfill.py, hubspot_sync_runs.py).
  const STAGE = (deal: string, stage: string) => ({ hubspot_id: deal, reason: `deal: stage ${stage} not mapped` });

  function panel(f: Partial<Freshness>) {
    render(
      <SyncHealthPanel
        open
        onOpenChange={vi.fn()}
        canRunSync={false}
        onSynced={vi.fn()}
        freshness={freshness({ state: "failed", last_success_at: "2026-10-13T09:10:00Z", ...f })}
      />,
    );
    return screen.getByRole("dialog", { name: "Sync health" });
  }

  it("a partly failed run that refused one deal for an unknown stage reads as the prototype", () => {
    const p = panel({ last_status: "partial", error_count: 1, errors: [STAGE("77001234", "1038193692")] });
    expect(
      within(p).getByText("HubSpot returned a stage the mapping does not know (1 deal). The other deals were saved."),
    ).toBeInTheDocument();
    for (const raw of ["77001234", "1038193692", "deal:", "not mapped"]) expect(p).not.toHaveTextContent(raw);
  });

  it("counts the deals, and says the other deals were saved only when the run saved them", () => {
    const p = panel({
      last_status: "failed",
      error_count: 2,
      errors: [STAGE("77001234", "1038193692"), { hubspot_id: "77001235", reason: "deal: stage missing not mapped" }],
    });
    expect(within(p).getByText("HubSpot returned a stage the mapping does not know (2 deals).")).toBeInTheDocument();
    expect(p).not.toHaveTextContent("The other deals were saved");
    expect(p).not.toHaveTextContent("missing not mapped");
  });

  it("any other reason becomes one counted sentence without ids, and the rest are 'not listed'", () => {
    const p = panel({
      last_status: "failed",
      error_count: 9,
      errors: [
        { hubspot_id: "", reason: "deal scan: HTTP 500" },
        STAGE("77001234", "1038193692"),
        { hubspot_id: "77005678", reason: "deal: owner 31337 unavailable (HTTP 500)" },
        { hubspot_id: "31337", reason: "owner: HTTP 500" },
        { hubspot_id: "77009999", reason: "deal: ValueError" },
      ],
    });
    const box = within(p);
    expect(box.getByText("HubSpot returned a stage the mapping does not know (1 deal).")).toBeInTheDocument();
    expect(box.getByText("4 other errors in the last attempt.")).toBeInTheDocument();
    expect(box.getByText("4 more errors not listed.")).toBeInTheDocument();
    for (const raw of ["77001234", "1038193692", "77005678", "31337", "77009999", "HTTP", "ValueError", "deal scan", "deal:"]) {
      expect(p).not.toHaveTextContent(raw);
    }
  });

  it("without an unknown stage, one sentence counts every error, listed or not", () => {
    const p = panel({
      last_status: "failed",
      error_count: 3,
      errors: [
        { hubspot_id: "", reason: "run did not finish" },
        { hubspot_id: "business_unit", reason: "business unit property: HTTP 503" },
      ],
    });
    expect(within(p).getByText("3 errors in the last attempt.")).toBeInTheDocument();
    for (const raw of ["run did not finish", "business unit property", "HTTP 503", "not listed"]) {
      expect(p).not.toHaveTextContent(raw);
    }
  });

  it("uses the singular for one error", () => {
    const p = panel({ last_status: "failed", error_count: 1, errors: [{ hubspot_id: "", reason: "no completed deal sync recorded" }] });
    expect(within(p).getByText("1 error in the last attempt.")).toBeInTheDocument();
    expect(p).not.toHaveTextContent("no completed deal sync recorded");
  });
});

describe("F3 · Run sync now measures the run against the server's latest attempt at the click", () => {
  const HOUR = 3_600_000;
  const at = (t: number) => new Date(t).toISOString();

  function renderRun(loaded: Freshness) {
    const onSynced = vi.fn();
    render(<SyncHealthPanel open onOpenChange={vi.fn()} freshness={loaded} canRunSync onSynced={onSynced} />);
    return { onSynced };
  }

  it("a run that ended after the page loaded, but before the click, is not taken for the new run", async () => {
    const loadedAt = Date.now() - 7 * HOUR;
    const { onSynced } = renderRun(freshness({ last_success_at: at(loadedAt), last_attempt_at: at(loadedAt) }));
    const run = await screen.findByRole("button", { name: "Run sync now" });
    vi.useFakeTimers();
    const clickedAt = Date.now();
    // The nightly ran an hour before the click; the page never refetched.
    const nightly = freshness({ last_success_at: at(clickedAt - HOUR), last_attempt_at: at(clickedAt - HOUR) });
    vi.spyOn(api, "triggerHubspotSync").mockReturnValue(new Promise(() => undefined));
    const health = vi.spyOn(api, "getSyncHealth").mockResolvedValue(nightly);
    fireEvent.click(run);
    expect(run).toBeDisabled();
    await settleClick();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_100);
    });
    expect(screen.getByRole("status")).toHaveTextContent("Sync started");
    expect(onSynced).not.toHaveBeenCalled();
    expect(health).toHaveBeenCalledTimes(2); // the read at the click, then the first poll

    // The run the click started ends; the next poll reports it.
    health.mockResolvedValue(freshness({ last_success_at: at(clickedAt + 60_000), last_attempt_at: at(clickedAt + 60_000) }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(screen.getByRole("status")).toHaveTextContent("Sync finished · Succeeded");
    expect(onSynced).toHaveBeenCalledTimes(1);
  });

  it("reads sync health before it starts the run", async () => {
    renderRun(FRESH);
    const run = await screen.findByRole("button", { name: "Run sync now" });
    vi.useFakeTimers();
    let answer: (health: api.SyncHealth) => void = () => undefined;
    vi.spyOn(api, "getSyncHealth")
      .mockResolvedValue(FRESH)
      .mockReturnValueOnce(new Promise((resolve) => (answer = resolve)));
    const trigger = vi.spyOn(api, "triggerHubspotSync").mockReturnValue(new Promise(() => undefined));
    fireEvent.click(run);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(trigger).not.toHaveBeenCalled();
    expect(run).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("Sync started");
    await act(async () => {
      answer(FRESH);
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(trigger).toHaveBeenCalledTimes(1);
  });

  it("falls back to the attempt the page loaded when that read fails", async () => {
    const loadedAt = Date.now() - 7 * HOUR;
    const { onSynced } = renderRun(freshness({ last_success_at: at(loadedAt), last_attempt_at: at(loadedAt) }));
    const run = await screen.findByRole("button", { name: "Run sync now" });
    vi.useFakeTimers();
    const clickedAt = Date.now();
    const trigger = vi.spyOn(api, "triggerHubspotSync").mockReturnValue(new Promise(() => undefined));
    const health = vi
      .spyOn(api, "getSyncHealth")
      .mockRejectedValueOnce(new api.ApiError(502, null, "API error 502"))
      .mockResolvedValue(freshness({ last_success_at: at(clickedAt + 60_000), last_attempt_at: at(clickedAt + 60_000) }));
    fireEvent.click(run);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(trigger).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("status")).toHaveTextContent("Sync started");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(health).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("status")).toHaveTextContent("Sync finished · Succeeded");
    expect(onSynced).toHaveBeenCalledTimes(1);
  });
});
