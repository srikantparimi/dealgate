import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import { AgreementsPanel } from "../pages/AgreementsPanel";

const LE_ID = "11111111-1111-1111-1111-111111111111";
const A1_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";

const list: apiClient.AgreementListResponse = {
  items: [
    {
      id: A1_ID,
      legal_entity_id: LE_ID,
      kind: "NDA",
      state: "drafting",
      owner_email: "legal@smartek21.com",
      next_action: "Draft NDA",
      due_date: "2026-10-15",
      effective_from: null,
      expiry: null,
      notice_days: null,
      evidence_s3_key: null,
      signatories: null,
      created_at: "2026-09-17T10:00:00Z",
      updated_at: "2026-09-17T10:00:00Z",
    },
  ],
  allowed_states: [
    "missing",
    "requested",
    "drafting",
    "under_review",
    "sent",
    "partially_signed",
    "executed",
    "expired",
    "terminated",
    "superseded",
  ],
};

describe("AgreementsPanel", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, "listAgreements").mockResolvedValue(list);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders rows from listAgreements", async () => {
    render(<AgreementsPanel legalEntityId={LE_ID} />);
    await waitFor(() => {
      expect(screen.getByText("NDA")).toBeInTheDocument();
    });
    expect(screen.getByText("Draft NDA")).toBeInTheDocument();
    expect(screen.getByText("legal@smartek21.com")).toBeInTheDocument();
    // State chip renders the state as-is.
    expect(screen.getByText("drafting")).toBeInTheDocument();
  });

  it("opens the add-agreement modal and submits create", async () => {
    const created: apiClient.AgreementRow = {
      id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      legal_entity_id: LE_ID,
      kind: "MSA",
      state: "drafting",
      owner_email: "legal@smartek21.com",
      next_action: "Kick off",
      due_date: "2026-11-01",
      effective_from: null,
      expiry: null,
      notice_days: null,
      evidence_s3_key: null,
      signatories: null,
      created_at: "2026-09-17T10:05:00Z",
      updated_at: "2026-09-17T10:05:00Z",
    };
    const spy = vi.spyOn(apiClient, "createAgreement").mockResolvedValue(created);

    render(<AgreementsPanel legalEntityId={LE_ID} />);
    await waitFor(() => expect(screen.getByText("NDA")).toBeInTheDocument());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /add agreement/i }));

    // Modal fields visible.
    const kindSelect = await screen.findByLabelText("Type");
    await user.selectOptions(kindSelect, "MSA");
    await user.type(screen.getByLabelText("Owner email"), "legal@smartek21.com");
    await user.type(screen.getByLabelText("Next action"), "Kick off");
    await user.type(screen.getByLabelText("Due date"), "2026-11-01");

    await user.click(screen.getByRole("button", { name: /^create$/i }));

    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    expect(spy.mock.calls[0][0]).toEqual({
      legal_entity_id: LE_ID,
      type: "MSA",
      state: "drafting",
      owner_email: "legal@smartek21.com",
      next_action: "Kick off",
      due_date: "2026-11-01",
    });

    // The new row is optimistically prepended.
    await waitFor(() => expect(screen.getByText("MSA")).toBeInTheDocument());
  });

  it("uploads evidence: signs URL, PUTs the file, then patches the row", async () => {
    const signed: apiClient.UploadUrlResponse = {
      url: "https://stub-agreements.local/put/agreements/xxx/nda.pdf?stub=1",
      s3_key: "agreements/xxx/nda.pdf",
      method: "PUT",
      expires_in: 300,
      required_headers: { "Content-Type": "application/pdf" },
    };
    const uploadSpy = vi.spyOn(apiClient, "getUploadUrl").mockResolvedValue(signed);
    const patchSpy = vi.spyOn(apiClient, "patchAgreement").mockResolvedValue({
      ...list.items[0],
      evidence_s3_key: signed.s3_key,
    });
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(null, { status: 200 }));

    render(<AgreementsPanel legalEntityId={LE_ID} />);
    await waitFor(() => expect(screen.getByText("NDA")).toBeInTheDocument());

    const user = userEvent.setup();
    // Row click → drawer opens.
    await user.click(screen.getByText("NDA"));

    // Grab the hidden <input type=file> that FileDropzone renders.
    const fileInput = (await screen.findByLabelText(
      "Evidence file",
    )) as HTMLInputElement;
    const file = new File(["hello"], "nda.pdf", { type: "application/pdf" });
    await user.upload(fileInput, file);

    await waitFor(() => expect(uploadSpy).toHaveBeenCalledTimes(1));
    expect(uploadSpy.mock.calls[0][0]).toBe(A1_ID);
    expect(uploadSpy.mock.calls[0][1]).toEqual({
      filename: "nda.pdf",
      content_type: "application/pdf",
    });

    // Direct PUT to the pre-signed URL.
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
    const putCall = fetchSpy.mock.calls[0];
    expect(putCall[0]).toBe(signed.url);
    expect((putCall[1] as RequestInit).method).toBe("PUT");

    // Then the row is confirmed via PATCH.
    await waitFor(() => expect(patchSpy).toHaveBeenCalledTimes(1));
    expect(patchSpy.mock.calls[0][0]).toBe(A1_ID);
    expect(patchSpy.mock.calls[0][1]).toEqual({ evidence_s3_key: signed.s3_key });
  });
});
