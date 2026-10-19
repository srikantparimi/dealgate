// S24-AG1 · regression tests for the frontend review findings (docs/bugs/s24-ag1.md): a gateway's HTML
// error page in the upload dialog, polling after one failed poll while a batch runs (and the Clients tab
// keeping its rows), and the HubSpot hints drawer staying open while Apply is in flight.
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as agreementsApi from "../../api/agreements";
import * as clientApi from "../../api/client";
import { errorText } from "../../pages/v2/agreements/UploadForm";
import { BATCH_DONE, after, renderAgreements, tonight } from "./S24FeAFixtures";

const GATEWAY_502 =
  "<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n</body>\r\n</html>\r\n";

class GatewayXhr {
  status = 0;
  responseText = "";
  upload: { onprogress: ((e: ProgressEvent) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  open() {}
  setRequestHeader() {}
  abort() {}
  send() {
    setTimeout(() => {
      this.status = 502;
      this.responseText = GATEWAY_502;
      this.onload?.();
    }, 0);
  }
}

const ME = { id: "me", email: "me@example.com", name: "Me", groups: ["SystemAdmin"] };

beforeEach(() => {
  vi.spyOn(agreementsApi, "getAgreementDocuments").mockResolvedValue({ total: 0, items: [] });
  vi.spyOn(agreementsApi, "getAgreementActivity").mockResolvedValue({ total: 0, items: [] });
  vi.spyOn(agreementsApi, "getStandardDocuments").mockResolvedValue({ NDA: null, MSA: null });
  vi.spyOn(agreementsApi, "listBatches").mockResolvedValue({ items: [] });
  vi.spyOn(clientApi, "getMe").mockResolvedValue(ME as Awaited<ReturnType<typeof clientApi.getMe>>);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("upload errors", () => {
  it("a gateway's HTML error page is never shown; the dialog says the upload failed with the status", async () => {
    vi.stubGlobal("XMLHttpRequest", GatewayXhr);
    const file = new File(["%PDF-1.4"], "a.pdf", { type: "application/pdf" });
    const err = await agreementsApi.uploadStandard("NDA", file).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(clientApi.ApiError);
    expect(errorText(err, "The upload failed. Try again.")).toBe("The upload failed. Try again. (error 502)");
  });
});

describe("batch polling", () => {
  it("keeps asking after one failed poll, and the Clients tab keeps its rows meanwhile", { timeout: 30_000 }, async () => {
    const running = () =>
      after({
        cutover: {
          set: true,
          date: "2026-10-15",
          latest_batch: { ...BATCH_DONE, status: "running", done_count: 50, target_count: 85 },
        },
      });
    let calls = 0;
    vi.spyOn(agreementsApi, "getAgreementsWorkspace").mockImplementation(async () => {
      calls += 1;
      if (calls === 2) throw new clientApi.ApiError(502, null, "Bad gateway");
      return calls >= 3 ? after() : running();
    });
    renderAgreements();
    expect(await screen.findByText(/is attaching standard copies: 50 of 85 clients done/)).toBeInTheDocument();
    const rowsBefore = screen.getAllByRole("row").length;

    // The first poll (after BATCH_POLL_MS) fails: the rows stay, with a note instead of the error state.
    await waitFor(() => expect(calls).toBe(2), { timeout: 8000 });
    expect(
      await screen.findByText(/The clients could not refresh; this is the last list loaded\./, undefined, { timeout: 3000 }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("row").length).toBe(rowsBefore);
    expect(screen.queryByText("The clients could not load.")).toBeNull();

    // The next poll still happens and succeeds: the line moves on and the note goes.
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(3), { timeout: 8000 });
    await waitFor(() => expect(screen.queryByText(/is attaching standard copies/)).toBeNull(), { timeout: 3000 });
    expect(screen.queryByText(/could not refresh/)).toBeNull();
  });
});

describe("HubSpot hints while Apply is in flight", () => {
  it("cannot be closed until the apply returns, then closes itself", async () => {
    vi.spyOn(agreementsApi, "getAgreementsWorkspace").mockImplementation(async () => tonight());
    vi.spyOn(agreementsApi, "getHubspotValues").mockResolvedValue({
      stored: true,
      items: [{ value: "Signed MSA", clients: 3, action: "ignore", would_mark: 3 }],
    });
    let releaseSave: () => void = () => undefined;
    vi.spyOn(agreementsApi, "saveHubspotMapping").mockImplementation(
      () =>
        new Promise((resolve) => {
          releaseSave = () => resolve({ stored: true, items: [] });
        }),
    );
    vi.spyOn(agreementsApi, "applyHubspotMapping").mockResolvedValue({ dry_run: false, would_mark: 3, marked: 3 });
    renderAgreements();
    await screen.findByRole("button", { name: "Cobalt Pharma" });
    fireEvent.click(screen.getByRole("button", { name: "HubSpot hints" }));
    fireEvent.change(await screen.findByLabelText(/Signed MSA/), { target: { value: "covered" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply mapping" }));
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100));
    });
    const hints = screen.getByRole("dialog", { name: "HubSpot hints" });
    // The body's Close is disabled and the drawer's × is refused while the save and apply run.
    const closes = within(hints).getAllByRole("button", { name: "Close" });
    expect(closes.some((button) => button.hasAttribute("disabled"))).toBe(true);
    for (const button of closes) fireEvent.click(button);
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100));
    });
    expect(screen.getByRole("dialog", { name: "HubSpot hints" })).toBeInTheDocument();

    await act(async () => {
      releaseSave();
      await new Promise((r) => setTimeout(r, 50));
    });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "HubSpot hints" })).toBeNull());
    expect((await screen.findAllByText("MSA marked covered for 3 clients.")).length).toBeGreaterThan(0);
  });
});
