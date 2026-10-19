// S24-AG1 F8 (was S17/S21 "agreement versions") · the old register lives on as
// the Documents tab of the NDA & MSA page: every stored file with its version
// history and per-version download, Replace through the upload dialog (the same
// checks, note and progress as every upload), and Download through the audited
// route. Write controls are locked with a reason, never hidden (F1), and no raw
// id is shown anywhere (F12): the old "Cleanup receipt {job id}" link is gone
// (a client copy's removal now lives in the client panel).
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as agreementsApi from "../../api/agreements";
import * as clientApi from "../../api/client";
import { DOC_CLIENT, DOC_STANDARD, IDS, ROLES, UUID_RE, after, renderAgreements } from "./S24FeAFixtures";

vi.mock("../../pages/v2/agreements/UploadDialog", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../pages/v2/agreements/UploadDialog")>()),
  UploadDialog: (await import("./S24FeAStandIns")).UploadDialogStandIn,
}));
vi.mock("../../pages/v2/agreements/ClientAgreementsPanel", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../pages/v2/agreements/ClientAgreementsPanel")>()),
  ClientAgreementsPanel: (await import("./S24FeAStandIns")).ClientAgreementsPanelStandIn,
}));
vi.mock("../../pages/v2/agreements/AttachWizard", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../pages/v2/agreements/AttachWizard")>()),
  AttachWizard: (await import("./S24FeAStandIns")).AttachWizardStandIn,
}));
vi.mock("../../pages/v2/agreements/UndoBatchDialog", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../pages/v2/agreements/UndoBatchDialog")>()),
  UndoBatchDialog: (await import("./S24FeAStandIns")).UndoBatchDialogStandIn,
}));
vi.mock("../../pages/v2/agreements/HubspotHintsDialog", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../pages/v2/agreements/HubspotHintsDialog")>()),
  HubspotHintsDialog: (await import("./S24FeAStandIns")).HubspotHintsDialogStandIn,
}));

let role: keyof typeof ROLES = "legal";

beforeEach(() => {
  role = "legal";
  vi.spyOn(agreementsApi, "getAgreementsWorkspace").mockImplementation(async () => after({ ...ROLES[role] }));
  vi.spyOn(agreementsApi, "getAgreementDocuments").mockResolvedValue({ total: 2, items: [DOC_CLIENT, DOC_STANDARD] });
  vi.spyOn(agreementsApi, "getAgreementActivity").mockResolvedValue({ total: 0, items: [] });
  vi.spyOn(clientApi, "listAgreementVersions").mockResolvedValue({
    items: [
      {
        version_no: 2,
        filename: "revision.pdf",
        file_size: 2,
        file_hash: null,
        uploaded_by: "u-legal",
        uploaded_by_name: "Legal",
        uploaded_at: "2026-10-01T17:00:00Z",
      },
      {
        version_no: 1,
        filename: "old.pdf",
        file_size: 2,
        file_hash: null,
        uploaded_by: "u-author",
        uploaded_by_name: "Original author",
        uploaded_at: "2026-09-01T17:00:00Z",
      },
    ],
  });
});

afterEach(() => vi.restoreAllMocks());

it("shows the version history of a document and downloads a historical version without replacing anything", async () => {
  vi.spyOn(clientApi, "getAgreementVersionDownloadUrl").mockResolvedValue({ url: "https://example.test/old", filename: "old.pdf" });
  const replace = vi.spyOn(clientApi, "replaceAgreement");
  const open = vi.spyOn(window, "open").mockImplementation(() => null);
  renderAgreements("/agreements?tab=documents");
  fireEvent.click(await screen.findByRole("button", { name: "History of Lakeside Group MSA" }));
  const drawer = await screen.findByRole("dialog", { name: "MSA document history" });
  expect(await within(drawer).findByText("v2: revision.pdf")).toBeInTheDocument();
  expect(within(drawer).getByText("v1: old.pdf")).toBeInTheDocument();
  expect(within(drawer).getByText("Original author · Sep 1, 2026")).toBeInTheDocument();
  fireEvent.click(within(drawer).getByRole("button", { name: "Download version 1" }));
  await waitFor(() => expect(open).toHaveBeenCalledWith("https://example.test/old", "_blank", "noopener,noreferrer"));
  expect(clientApi.getAgreementVersionDownloadUrl).toHaveBeenCalledWith(DOC_CLIENT.agreement_id, 1);
  expect(replace).not.toHaveBeenCalled();
});

it("a failed history load says so inside the drawer", async () => {
  vi.mocked(clientApi.listAgreementVersions).mockRejectedValue(new Error("History unavailable"));
  renderAgreements("/agreements?tab=documents");
  fireEvent.click(await screen.findByRole("button", { name: "History of Lakeside Group NDA" }));
  const drawer = await screen.findByRole("dialog", { name: "NDA document history" });
  expect(await within(drawer).findByRole("alert")).toHaveTextContent("History unavailable");
});

it("Replace goes through the upload dialog for that client and kind (a new version, never a raw file input)", async () => {
  renderAgreements("/agreements?tab=documents");
  fireEvent.click(await screen.findByRole("button", { name: "Replace Lakeside Group MSA" }));
  const dialog = screen.getByRole("dialog", { name: "Upload dialog stand-in" });
  expect(dialog).toHaveAttribute("data-mode", "client");
  expect(dialog).toHaveAttribute("data-client", IDS.lakeside);
  expect(dialog).toHaveAttribute("data-client-name", "Lakeside Group");
  expect(dialog).toHaveAttribute("data-kind", "MSA");
  expect(dialog).toHaveAttribute("data-lock-target", "true");
  expect(screen.queryByLabelText("Replacement file")).toBeNull();
});

it("readers keep history and download; every write control stays visible, locked with the reason", async () => {
  role = "sales";
  renderAgreements("/agreements?tab=documents");
  await screen.findByRole("table", { name: "Documents" });
  for (const kind of ["MSA", "NDA"]) {
    expect(screen.getByRole("button", { name: `History of Lakeside Group ${kind}` })).not.toHaveAttribute("aria-disabled");
    expect(screen.getByRole("button", { name: `Download Lakeside Group ${kind}` })).not.toHaveAttribute("aria-disabled");
    expect(screen.getByRole("button", { name: `Replace Lakeside Group ${kind}` })).toHaveAttribute("aria-disabled", "true");
  }
  expect(screen.getByRole("button", { name: /Upload document/ })).toHaveAttribute("data-locked", "writer");
});

it("never shows a raw id: no cleanup-receipt link with a job id, no client or agreement id", async () => {
  renderAgreements("/agreements?tab=documents");
  await screen.findByRole("table", { name: "Documents" });
  expect(screen.queryByText(/Cleanup receipt/)).toBeNull();
  expect(document.body.textContent ?? "").not.toMatch(UUID_RE);
});
