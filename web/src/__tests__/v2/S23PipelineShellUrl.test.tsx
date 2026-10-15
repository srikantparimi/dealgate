// S23-PL2 F2 · one data hook and the URL as the view's memory: every filter is
// read from and written to the query string, the back button restores the
// view, one request per change (a newer view cancels the older request) and a
// 300 ms wait while typing in search. F13 (page part): the selection survives
// paging and sorting and is cleared by a filter or tab change.
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as appConfig from "../../api/appConfig";
import * as api from "../../api/client";
import * as wsApi from "../../api/pipelineWorkspace";
import { PipelinePage } from "../../pages/v2/Pipeline";
import { answerFor, currentParams, renderAt } from "./S23PipelineShellFixtures";

vi.mock("../../pages/v2/pipeline/RecordsPanel", async () => ({
  RecordsPanel: (await import("./S23PipelineShellFakes")).FakeRecordsPanel,
}));
vi.mock("../../pages/v2/pipeline/DealPreview", async () => ({
  DealPreview: (await import("./S23PipelineShellFakes")).FakeDealPreview,
}));
vi.mock("../../pages/v2/pipeline/ClientPreview", async () => ({
  ClientPreview: (await import("./S23PipelineShellFakes")).FakeClientPreview,
}));

const SEARCH = "Search deals, clients, owners or next actions";

beforeEach(() => {
  vi.spyOn(api, "getMe").mockResolvedValue({ id: "user-1", email: "e2e@example.com", name: "E2E", groups: ["Sales"] });
  vi.spyOn(appConfig, "useAppConfig").mockReturnValue({ hubspotPortalId: "1234567", loading: false });
  vi.spyOn(wsApi, "listWorkspaceViews").mockResolvedValue([]);
  vi.spyOn(wsApi, "listWorkspaceGroups").mockResolvedValue([]);
  vi.spyOn(wsApi, "getWorkspace").mockImplementation(async (query) => answerFor(query));
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

const statusSelect = () => screen.getByRole("combobox", { name: "Deal status" });
const lastQuery = () => vi.mocked(wsApi.getWorkspace).mock.lastCall?.[0];

describe("F2 · the URL holds the view", () => {
  it("reads every filter from the link, asks once with them and shows each as a chip", async () => {
    renderAt(
      <PipelinePage />,
      "/pipeline?status=won&bu=ST21&q=Bank&sort=name&page=2&date_field=created&date_preset=last30&owner=owner-jk",
    );
    expect(await screen.findByRole("button", { name: "Remove BU: ST21 (US)" })).toBeInTheDocument();
    expect(wsApi.getWorkspace).toHaveBeenCalledTimes(1);
    expect(lastQuery()).toMatchObject({
      status: "won",
      bu: ["ST21"],
      q: "Bank",
      sort: "name",
      page: 2,
      date_field: "created",
      date_preset: "last30",
      owner: ["owner-jk"],
    });
    expect(statusSelect()).toHaveValue("won");
    expect(screen.getByRole("searchbox", { name: SEARCH })).toHaveValue("Bank");
    expect(screen.getByRole("button", { name: "Remove Closed won" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Search: Bank" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Created: last 30 days" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Deal owner: Janice Krpan" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Deal owner · 1" })).toBeInTheDocument();
  });

  it("writes a change into the URL, and the browser's back button restores the view", async () => {
    renderAt(<PipelinePage />);
    await screen.findByRole("button", { name: /^Open deals/ });
    fireEvent.change(statusSelect(), { target: { value: "won" } });
    await waitFor(() => expect(currentParams(screen.getByTestId).get("status")).toBe("won"));
    await waitFor(() => expect(lastQuery()).toMatchObject({ status: "won" }));
    expect(screen.getByRole("button", { name: "Remove Closed won" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "test: browser back" }));
    await waitFor(() => expect(statusSelect()).toHaveValue("open"));
    expect(currentParams(screen.getByTestId).get("status")).toBeNull();
    await waitFor(() => expect(lastQuery()).toMatchObject({ status: "open" }));
    expect(screen.getByRole("button", { name: "Remove Status: Open (includes on hold)" })).toBeInTheDocument();
  });

  it("typing a search replaces one history entry, so back returns to the view before the search", async () => {
    renderAt(<PipelinePage />, "/pipeline?status=lost");
    await screen.findByRole("button", { name: /^Open deals/ });
    const box = screen.getByRole("searchbox", { name: SEARCH });
    for (const text of ["B", "Ba", "Ban", "Bank "]) fireEvent.change(box, { target: { value: text } });
    await waitFor(() => expect(currentParams(screen.getByTestId).get("q")).toBe("Bank"));
    // The box keeps the trailing space the URL drops, so the next word can be typed.
    expect(box).toHaveValue("Bank ");
    fireEvent.click(screen.getByRole("button", { name: "test: browser back" }));
    await waitFor(() => expect(currentParams(screen.getByTestId).get("q")).toBeNull());
    expect(currentParams(screen.getByTestId).get("status")).toBe("lost");
    await waitFor(() => expect(screen.getByRole("searchbox", { name: SEARCH })).toHaveValue(""));
  });
});

describe("F2 · one request per view", () => {
  it("asks once per change, and a newer view cancels the request still in flight", async () => {
    const signals: (AbortSignal | undefined)[] = [];
    vi.mocked(wsApi.getWorkspace).mockImplementation((query, signal) => {
      signals.push(signal);
      return signals.length === 1 ? Promise.resolve(answerFor(query)) : new Promise(() => undefined);
    });
    renderAt(<PipelinePage />);
    await screen.findByRole("button", { name: /^Open deals/ });
    expect(wsApi.getWorkspace).toHaveBeenCalledTimes(1);

    fireEvent.change(statusSelect(), { target: { value: "won" } });
    await waitFor(() => expect(wsApi.getWorkspace).toHaveBeenCalledTimes(2));
    fireEvent.change(statusSelect(), { target: { value: "lost" } });
    await waitFor(() => expect(wsApi.getWorkspace).toHaveBeenCalledTimes(3));
    expect(signals[1]?.aborted).toBe(true);
    expect(signals[2]?.aborted).toBe(false);
    expect(lastQuery()).toMatchObject({ status: "lost" });
  });

  it("waits 300 ms after the last keystroke in search, then asks once", async () => {
    renderAt(<PipelinePage />);
    await screen.findByRole("button", { name: /^Open deals/ });
    expect(wsApi.getWorkspace).toHaveBeenCalledTimes(1);
    vi.useFakeTimers();
    const box = screen.getByRole("searchbox", { name: SEARCH });
    for (const text of ["B", "Ba", "Ban", "Bank"]) fireEvent.change(box, { target: { value: text } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(299);
    });
    expect(wsApi.getWorkspace).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(wsApi.getWorkspace).toHaveBeenCalledTimes(2);
    expect(lastQuery()).toMatchObject({ q: "Bank" });
  });

  it("asks at once (no wait) for a change that is not a search", async () => {
    renderAt(<PipelinePage />);
    await screen.findByRole("button", { name: /^Open deals/ });
    vi.useFakeTimers();
    fireEvent.change(statusSelect(), { target: { value: "hold" } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(wsApi.getWorkspace).toHaveBeenCalledTimes(2);
    expect(lastQuery()).toMatchObject({ status: "hold" });
  });
});

describe("F13 · the bulk selection's lifetime (page state)", () => {
  it("survives paging and sorting; a filter or tab change clears it", async () => {
    renderAt(<PipelinePage />);
    await screen.findByRole("button", { name: /^Open deals/ });
    const selectedText = () => screen.getByTestId("records-selected").textContent;

    fireEvent.click(screen.getByRole("button", { name: "fake: select two" }));
    expect(selectedText()).toBe("2 selected");
    fireEvent.click(screen.getByRole("button", { name: "fake: next page" }));
    await waitFor(() => expect(currentParams(screen.getByTestId).get("page")).toBe("2"));
    fireEvent.click(screen.getByRole("button", { name: "fake: sort by name" }));
    await waitFor(() => expect(currentParams(screen.getByTestId).get("sort")).toBe("name"));
    expect(selectedText()).toBe("2 selected");

    fireEvent.change(statusSelect(), { target: { value: "all" } });
    await waitFor(() => expect(selectedText()).toBe("0 selected"));
    // A filter change also goes back to page 1.
    expect(currentParams(screen.getByTestId).get("page")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "fake: select two" }));
    expect(selectedText()).toBe("2 selected");
    fireEvent.click(screen.getByRole("button", { name: "fake: switch tab" }));
    await waitFor(() => expect(screen.getByTestId("records-tab")).toHaveTextContent("clients"));
    expect(selectedText()).toBe("0 selected");
  });
});
