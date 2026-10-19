// S24-AG1 FE-A test data · workspace answers shaped like
// docs/reference/openapi-agreements.yaml (plus the server's additive fields),
// with the prototype's numbers: "tonight" (no files, cutover not set) and
// "after" (standard v1 attached by AG-0001). Client ids are real-looking UUIDs
// so the "never a raw id" checks mean something. Plus a render helper with the
// app root's providers and a probe that exposes the URL without rendering it.
import { configure, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import type {
  ActivityRow,
  AgreementsWorkspace,
  Batch,
  Card,
  DocumentRow,
  StandardVersion,
} from "../../api/agreements";
import { AgreementsRegisterPage } from "../../pages/v2/AgreementsRegister";
import type { AgreementsClientRow } from "../../pages/v2/agreements/agreementsState";
import { Toaster } from "../../ui-v2/primitives/toaster";
import { TooltipProvider } from "../../ui-v2/primitives/tooltip";

configure({ asyncUtilTimeout: 5_000 });

export const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

export const IDS = {
  cobalt: "1b4e28ba-2fa1-41d2-883f-0016d3cca427",
  lakeside: "6fa459ea-ee8a-4ca4-894e-db77e160355e",
  hostile: "0a6f1c1e-6a7b-4c2d-9e3f-5a6b7c8d9e0f",
  cedar: "9c858901-8a57-4791-81fe-4c455b099bc9",
  agreement: "c56a4180-65aa-42ec-a945-5fd21dec0538",
};

export const HOSTILE_NAME = "<img src=x onerror=alert(1)>Acme";

export function clientRow(over: Partial<AgreementsClientRow> & Pick<AgreementsClientRow, "client_id" | "name">): AgreementsClientRow {
  return {
    relationship: "net_new",
    relationship_basis: "none",
    requirement: "required",
    nda: { state: "missing", source_label: null },
    msa: { state: "missing", source_label: null },
    needs_attention: true,
    furthest_open_stage: 2,
    business_units: [{ name: "ST21", region: "US" }],
    deal_count: 1,
    flags: [],
    provisional: true,
    on_hold: false,
    stage_text: "2 · Qualification",
    basis_text: "No earlier work found",
    business_unit_note: null,
    ...over,
  };
}

export const COBALT = clientRow({
  client_id: IDS.cobalt,
  name: "Cobalt Pharma",
  furthest_open_stage: 6,
  stage_text: "6 · Contracting",
});

export const LAKESIDE = clientRow({
  client_id: IDS.lakeside,
  name: "Lakeside Group",
  relationship: "existing",
  relationship_basis: "closed_won",
  requirement: "none",
  nda: { state: "standard", source_label: "Standard v1" },
  msa: { state: "client", source_label: "Client copy" },
  needs_attention: false,
  furthest_open_stage: 0,
  stage_text: "No active deal",
  business_units: [{ name: "IT Avalon", region: "US" }],
  deal_count: 2,
  basis_text: "Closed Won deal",
});

export const HOSTILE = clientRow({
  client_id: IDS.hostile,
  name: HOSTILE_NAME,
  requirement: "later",
  nda: { state: "due_later", source_label: null },
  msa: { state: "due_later", source_label: null },
  needs_attention: false,
  furthest_open_stage: 1,
  stage_text: "1 · Prospecting",
  business_units: [],
  business_unit_note: "Region not mapped to a business unit: Mars",
  flags: ["possible_duplicate", "test_data"],
});

/** Net new past stage 1, NDA marked covered, MSA missing: its upload starts on the MSA. */
export const CEDAR = clientRow({
  client_id: IDS.cedar,
  name: "Cedar Freight",
  nda: { state: "covered", source_label: "Marked covered" },
  msa: { state: "missing", source_label: null },
  furthest_open_stage: 4,
  stage_text: "4 · Proposal",
  business_units: [{ name: "Retro Rabbit", region: "South Africa" }],
});

export function tonightCards(): Card[] {
  return [
    { key: "clients", label: "Clients", value: 208, note: "70 existing · 138 net new", drill: {} },
    {
      key: "existing",
      label: "Existing clients",
      value: 70,
      note: "47 Closed Won · 32 with an SOW or engagement",
      drill: { relationship: "existing" },
    },
    {
      key: "net_new",
      label: "Net-new clients",
      value: 138,
      note: "Bring their own copy unless included",
      drill: { relationship: "net_new" },
    },
    {
      key: "needs_attention",
      label: "Needs attention",
      value: 21,
      note: "Net new, past stage 1, NDA or MSA missing",
      drill: { status: "attention" },
    },
    {
      key: "standard_attached",
      label: "Standard copies attached",
      value: 0,
      note: "clients · NDA 0 · MSA 0",
      drill: { status: "has_standard" },
    },
    { key: "client_copies", label: "Client copies on file", value: 0, note: "clients · NDA 0 · MSA 0", drill: { status: "has_client" } },
  ];
}

export function afterCards(): Card[] {
  return tonightCards().map((card) => {
    if (card.key === "needs_attention") return { ...card, value: 3 };
    if (card.key === "standard_attached") return { ...card, value: 83, note: "clients · NDA 80 · MSA 77" };
    if (card.key === "client_copies") return { ...card, value: 10, note: "clients · NDA 5 · MSA 7 · 1 marked covered" };
    return card;
  });
}

export const STD_NDA: StandardVersion = {
  kind: "NDA",
  version: 1,
  file_name: "SmarTek21_Standard_NDA.pdf",
  file_size: 214_000,
  uploaded_by: "Srikanth Parimi",
  uploaded_at: "2026-10-15T18:00:00Z",
  attached_clients: 80,
};

export const STD_MSA: StandardVersion = {
  kind: "MSA",
  version: 1,
  file_name: "SmarTek21_Standard_MSA.pdf",
  file_size: 388_000,
  uploaded_by: "Srikanth Parimi",
  uploaded_at: "2026-10-15T18:00:00Z",
  attached_clients: 77,
};

export const BATCH_DONE: Batch & { attached_clients: number } = {
  id: "AG-0001",
  status: "done",
  kinds: ["NDA", "MSA"],
  created_by: "Srikanth Parimi",
  created_at: "2026-10-15T18:05:00Z",
  target_count: 85,
  done_count: 85,
  attached_count: 157,
  skipped_count: 0,
  error: null,
  attached_clients: 85,
};

export function tonight(over: Partial<AgreementsWorkspace> = {}): AgreementsWorkspace {
  return {
    cutover: { set: false, date: null, latest_batch: null },
    cards: tonightCards(),
    standard: { NDA: null, MSA: null },
    total: 3,
    items: [COBALT, LAKESIDE, HOSTILE],
    can_write: true,
    is_admin: true,
    document_count: 0,
    activity_count: 0,
    ...over,
  };
}

export function after(over: Partial<AgreementsWorkspace> = {}): AgreementsWorkspace {
  return tonight({
    cutover: { set: true, date: "2026-10-15", latest_batch: BATCH_DONE },
    cards: afterCards(),
    standard: { NDA: STD_NDA, MSA: STD_MSA },
    document_count: 169,
    activity_count: 3,
    ...over,
  });
}

export const ROLES = {
  admin: { can_write: true, is_admin: true },
  legal: { can_write: true, is_admin: false },
  sales: { can_write: false, is_admin: false },
} as const;

export const DOC_STANDARD: DocumentRow = {
  client_id: IDS.lakeside,
  client_name: "Lakeside Group",
  kind: "NDA",
  file_name: "SmarTek21_Standard_NDA.pdf",
  source: "standard",
  standard_version: 1,
  batch_id: "AG-0001",
  uploaded_by: "Srikanth Parimi",
  // 22:30 PT on Oct 15 is already Oct 16 in UTC: the page shows the Pacific date.
  uploaded_at: "2026-10-16T05:30:00Z",
  agreement_id: IDS.agreement,
  version_no: 1,
};

export const DOC_CLIENT: DocumentRow = {
  client_id: IDS.lakeside,
  client_name: "Lakeside Group",
  kind: "MSA",
  file_name: "Lakeside-Group-MSA-client-copy.pdf",
  source: "client",
  standard_version: null,
  batch_id: null,
  uploaded_by: "Legal user",
  uploaded_at: "2026-10-15T20:00:00Z",
  agreement_id: "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  version_no: 2,
};

export const ACTIVITY: ActivityRow[] = [
  { at: "2026-10-15T21:00:00Z", by: "Legal user", action: "client_uploaded", text: "Uploaded client copies for 10 clients", client_id: null },
  {
    at: "2026-10-15T18:05:00Z",
    by: "Srikanth Parimi",
    action: "batch_run",
    text: "Attached standard copies to 85 clients (batch AG-0001, NDA and MSA): 67 existing and 18 net new in the pipeline",
    client_id: null,
  },
  {
    at: "2026-10-15T18:00:00Z",
    by: "Srikanth Parimi",
    action: "standard_uploaded",
    text: "Uploaded the standard NDA (v1) and the standard MSA (v1)",
    client_id: IDS.lakeside,
  },
];

function LocationProbe() {
  const location = useLocation();
  // An attribute, never text: the URL holds client ids, which the page must never show.
  return <span data-testid="location" data-search={location.search} hidden />;
}

/** The page inside the providers the app root gives it (tooltips, toasts, router). */
export function renderAgreements(path = "/agreements") {
  const view = render(
    <TooltipProvider>
      <Toaster>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route
              path="/agreements"
              element={
                <>
                  <AgreementsRegisterPage />
                  <LocationProbe />
                </>
              }
            />
          </Routes>
        </MemoryRouter>
      </Toaster>
    </TooltipProvider>,
  );
  return { ...view, params: () => new URLSearchParams(screen.getByTestId("location").getAttribute("data-search") ?? "") };
}
