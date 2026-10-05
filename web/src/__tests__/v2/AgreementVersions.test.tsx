import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { AgreementsRegisterPage } from "../../pages/v2/AgreementsRegister";
import * as api from "../../api/client";
vi.mock("../../api/client", () => ({
  getMe: vi.fn(),
  listAgreements: vi.fn(),
  listClients: vi.fn(),
  uploadAgreement: vi.fn(),
  deleteAgreement: vi.fn(),
  getAgreementDownloadUrl: vi.fn(),
  listAgreementVersions: vi.fn(),
  replaceAgreement: vi.fn(),
  getAgreementVersionDownloadUrl: vi.fn(),
  getDeletionJob: vi.fn(),
  retryDeletionJob: vi.fn(),
}));
afterEach(cleanup);
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getMe).mockResolvedValue({
    groups: ["Legal"],
  } as api.MeResponse);
  vi.mocked(api.listClients).mockResolvedValue({
    items: [{ id: "a", name: "Alpha" }],
  } as api.ClientListResponse);
  vi.mocked(api.listAgreements).mockResolvedValue({
    items: [
      {
        id: "doc",
        client_id: "a",
        client_name: "Alpha",
        kind: "NDA",
        filename: "original.pdf",
        file_size: 2,
        uploaded_by_name: "Legal",
        uploaded_at: "2026-10-01",
        version_no: 2,
      },
    ] as api.AgreementRow[],
  });
  vi.mocked(api.listAgreementVersions).mockResolvedValue({
    items: [
      {
        version_no: 2,
        filename: "original.pdf",
        uploaded_by_name: "Legal",
        uploaded_at: "2026-10-01",
      },
    ] as api.AgreementFileVersion[],
  });
});

it("keeps a durable cleanup receipt and exposes failure, retry and completion", async () => {
  const pending = {
    job_id: "cleanup",
    status: "pending",
    source_deleted: true,
    counts: { agreements: 1, files: 2 },
    last_error: null,
    sow_title: "original.pdf",
    attempts: 0,
    next_attempt_at: null,
    completed_at: null,
    state: "deleted",
    reason: "Agreement deleted; file cleanup pending",
    subject_type: "agreement",
  } satisfies api.DeletionJobResponse;
  vi.mocked(api.deleteAgreement).mockResolvedValue(pending);
  vi.mocked(api.getDeletionJob)
    .mockResolvedValueOnce({
      ...pending,
      status: "failed",
      last_error: "Storage unavailable",
    })
    .mockResolvedValueOnce({ ...pending, status: "done" });
  vi.mocked(api.retryDeletionJob).mockResolvedValue(pending);
  render(
    <MemoryRouter>
      <AgreementsRegisterPage />
    </MemoryRouter>,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Delete original.pdf" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Delete" }));
  expect(await screen.findByText("File cleanup pending")).toBeTruthy();
  expect(
    screen
      .getByRole("link", { name: "Cleanup receipt cleanup" })
      .getAttribute("href"),
  ).toBe("/deletions/cleanup");
  fireEvent.click(screen.getByRole("button", { name: "Refresh cleanup" }));
  expect(await screen.findByText("File cleanup failed")).toBeTruthy();
  expect(screen.getByText("Storage unavailable")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Retry cleanup" }));
  await waitFor(() =>
    expect(api.retryDeletionJob).toHaveBeenCalledWith("cleanup"),
  );
  await screen.findByText("File cleanup pending");
  fireEvent.click(screen.getByRole("button", { name: "Refresh cleanup" }));
  expect(await screen.findByText("File cleanup complete")).toBeTruthy();
});
it("preselects scoped upload and keeps mutation controls hidden for readers", async () => {
  vi.mocked(api.getMe).mockResolvedValue({
    groups: ["Sales"],
  } as api.MeResponse);
  render(
    <MemoryRouter
      initialEntries={["/agreements?client_id=a&kind=NDA&upload=1"]}
    >
      <AgreementsRegisterPage />
    </MemoryRouter>,
  );
  await screen.findByText("original.pdf");
  expect(screen.queryByRole("button", { name: "Upload" })).toBeNull();
  expect(
    screen.queryByRole("button", { name: "Replace original.pdf" }),
  ).toBeNull();
});

it("does not require client-directory permission to show Marketing agreement documents", async () => {
  vi.mocked(api.getMe).mockResolvedValue({
    groups: ["Marketing"],
  } as api.MeResponse);
  vi.mocked(api.listClients).mockRejectedValue(
    new Error("403: client directory forbidden"),
  );
  render(
    <MemoryRouter initialEntries={["/agreements?client_id=a"]}>
      <AgreementsRegisterPage />
    </MemoryRouter>,
  );
  expect(await screen.findByText("original.pdf")).toBeTruthy();
  expect(api.listClients).not.toHaveBeenCalled();
  expect(
    screen.getByRole("button", { name: "History original.pdf" }),
  ).toBeTruthy();
  expect(
    screen.getByRole("button", { name: "Download original.pdf" }),
  ).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Upload" })).toBeNull();
  expect(
    screen.queryByRole("button", { name: "Delete original.pdf" }),
  ).toBeNull();
  expect(
    screen.queryByRole("button", { name: "Replace original.pdf" }),
  ).toBeNull();
});
it("shows version history and preserves replacement file after conflict", async () => {
  vi.mocked(api.replaceAgreement).mockRejectedValue(
    new Error("409: refresh latest version"),
  );
  render(
    <MemoryRouter initialEntries={["/agreements?client_id=a&kind=NDA"]}>
      <AgreementsRegisterPage />
    </MemoryRouter>,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Replace original.pdf" }),
  );
  const file = new File(["new"], "revision.pdf", { type: "application/pdf" });
  fireEvent.change(screen.getByLabelText("Replacement file"), {
    target: { files: [file] },
  });
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Save replacement" }),
    ).toBeEnabled(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Save replacement" }));
  await screen.findByText("409: refresh latest version");
  expect(api.replaceAgreement).toHaveBeenCalledWith("doc", 2, file);
  expect(screen.getByLabelText("Replacement file")).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", { name: "Reload latest version" }),
  );
  await waitFor(() =>
    expect(api.listAgreementVersions).toHaveBeenCalledTimes(2),
  );
});

it("submits an additional document with the prebound client and kind", async () => {
  render(
    <MemoryRouter
      initialEntries={["/agreements?client_id=a&kind=MSA&upload=1"]}
    >
      <AgreementsRegisterPage />
    </MemoryRouter>,
  );
  const input = await screen.findByLabelText("Agreement file");
  expect((screen.getByLabelText("Client") as HTMLSelectElement).value).toBe(
    "a",
  );
  expect(
    (screen.getByRole("radio", { name: "MSA" }) as HTMLInputElement).checked,
  ).toBe(true);
  expect(
    (screen.getByRole("radio", { name: "NDA" }) as HTMLInputElement).checked,
  ).toBe(false);
  const file = new File(["msa"], "msa.pdf", { type: "application/pdf" });
  fireEvent.change(input, { target: { files: [file] } });
  const dialog = screen.getByRole("dialog");
  const button = Array.from(dialog.querySelectorAll("button")).find(
    (b) => b.textContent === "Upload",
  )!;
  fireEvent.click(button);
  await waitFor(() =>
    expect(api.uploadAgreement).toHaveBeenCalledWith("a", "MSA", file),
  );
});

it("downloads the selected historical revision without replacing the root", async () => {
  vi.mocked(api.listAgreementVersions).mockResolvedValue({
    items: [
      {
        version_no: 1,
        filename: "old.pdf",
        uploaded_by_name: "Original author",
        uploaded_at: "2026-09-01",
      },
    ] as api.AgreementFileVersion[],
  });
  vi.mocked(api.getAgreementVersionDownloadUrl).mockResolvedValue({
    url: "https://example.test/old",
    filename: "old.pdf",
  });
  const open = vi.spyOn(window, "open").mockImplementation(() => null);
  render(
    <MemoryRouter>
      <AgreementsRegisterPage />
    </MemoryRouter>,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "History original.pdf" }),
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Download version 1" }),
  );
  await waitFor(() =>
    expect(open).toHaveBeenCalledWith(
      "https://example.test/old",
      "_blank",
      "noopener,noreferrer",
    ),
  );
  expect(api.getAgreementVersionDownloadUrl).toHaveBeenCalledWith("doc", 1);
  expect(api.replaceAgreement).not.toHaveBeenCalled();
  open.mockRestore();
});
