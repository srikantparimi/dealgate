/**
 * S24-AG1 lane BE-D · F11 — after creating a client by hand, offer "Add the NDA and MSA now (optional)".
 *
 * New engagement hands the offer to the engagement page only when POST /clients really created the
 * client; the SOW studio shows it right after "Create new client" in the picker. The button opens the
 * shared upload dialog (mocked here: FE-B owns it) preset to that client; non-writers see it locked
 * with the reason. Names render as text.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api/engagements";
import * as clientApi from "../../api/client";
import type { UploadDialogProps } from "../../pages/v2/agreements/UploadDialog";
import { EngagementPage } from "../../pages/v2/portfolio/EngagementPage";
import { NewEngagementPage } from "../../pages/v2/portfolio/NewEngagementPage";
import { SowStudioPage } from "../../pages/v2/SowStudio";
import { Toaster } from "../../ui-v2/primitives/toaster";
import { TooltipProvider } from "../../ui-v2/primitives/tooltip";

let groups: string[] = ["SystemAdmin"];
vi.mock("../../auth/AuthProvider", () => ({ useAuth: () => ({ user: { groups } }) }));

const dialogCalls: UploadDialogProps[] = [];
vi.mock("../../pages/v2/agreements/UploadDialog", () => ({
  UploadDialog: (props: UploadDialogProps) => {
    dialogCalls.push(props);
    if (!props.open) return null;
    return (
      <div role="dialog" aria-label="Upload a document">
        <span data-testid="dialog-target">{JSON.stringify(props.target)}</span>
        <button
          type="button"
          onClick={() => props.onUploaded({ mode: "client", kind: props.target?.kind ?? "NDA", clientId: props.target?.clientId })}
        >
          Fake upload
        </button>
        <button type="button" onClick={() => props.onOpenChange(false)}>
          Fake close
        </button>
      </div>
    );
  },
}));

const HOSTILE = '<img src=x onerror="alert(1)"> & Sons';

function shell(ui: ReactNode) {
  return (
    <TooltipProvider>
      <Toaster>{ui}</Toaster>
    </TooltipProvider>
  );
}

const engagement: api.Engagement = {
  id: "e-new",
  client_id: "c-new",
  client_name: "Brand New Co",
  hubspot_deal_id: null,
  opportunity_id: null,
  name: "Support",
  type: "msp",
  start: "2026-11-01",
  end: "2027-04-30",
  total_price: null,
  monthly_fee: "42000.00",
  currency: "USD",
  additional_costs_flag: false,
  same_dates_for_all: true,
  owner_user_id: null,
  owner_name: null,
  status: "active",
  duration_months: 6,
  business_unit: "ST21",
  sales_owner: null,
  delivery_owner: null,
  closed: false,
};

const forecast: api.Forecast = {
  engagement_id: "e-new",
  duration_months: 6,
  status: "OK",
  project_floor_pct: 0.35,
  monthly_required: true,
  missing: [],
  totals: {
    hours: 0,
    labour_cost: "0.00",
    burden_cost: "0.00",
    loaded_cost: "0.00",
    additional_costs: "0.00",
    pass_through_revenue: "0.00",
    total_revenue: "0.00",
    total_cost: "0.00",
    gm: "0.00",
    gm_pct: 0,
  },
  staffing_totals: { hours: 0, revenue: "0.00", loaded_cost: "0.00", gm_pct: 0 },
  actuals: { months_with_actuals: 0, actual_revenue: "0.00", forecast_in_actual_months: "0.00", billing_loss: "0.00" },
  months: [],
  by_assignment: {},
  by_assignment_totals: {},
  allocation_months: [],
  location_check: {},
} as unknown as api.Forecast;

beforeEach(() => {
  groups = ["SystemAdmin"];
  dialogCalls.length = 0;
  try {
    sessionStorage.clear();
  } catch {
    /* jsdom */
  }
  vi.spyOn(api, "listClientOptions").mockResolvedValue([{ id: "c1", name: "Client A", source: "manual" }]);
  vi.spyOn(api, "createEngagement").mockResolvedValue(engagement);
  vi.spyOn(api, "getEngagement").mockResolvedValue(engagement);
  vi.spyOn(api, "listAllocations").mockResolvedValue([]);
  vi.spyOn(api, "listCosts").mockResolvedValue([]);
  vi.spyOn(api, "getEngagementForecast").mockResolvedValue(forecast);
  vi.spyOn(api, "getForecastSettings").mockRejectedValue(new Error("not for this role"));
  vi.spyOn(clientApi, "getPipelineFacets").mockResolvedValue({ owners: [], business_units: [] });
  vi.spyOn(clientApi, "listPipelineOpportunities").mockResolvedValue(
    { items: [], total: 0, page: 1, page_size: 100 } as unknown as Awaited<ReturnType<typeof clientApi.listPipelineOpportunities>>,
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

async function fillNewEngagement() {
  await screen.findByRole("heading", { name: "New engagement" });
  fireEvent.change(screen.getByLabelText("Client *"), { target: { value: "__new" } });
  fireEvent.change(screen.getByLabelText("New client name"), { target: { value: "Brand New Co" } });
  fireEvent.change(screen.getByLabelText("Engagement name *"), { target: { value: "Support" } });
  fireEvent.change(screen.getByLabelText("Engagement type *"), { target: { value: "msp" } });
  fireEvent.change(screen.getByLabelText("Start *"), { target: { value: "2026-11-01" } });
  fireEvent.change(screen.getByLabelText("End *"), { target: { value: "2027-04-30" } });
  fireEvent.change(screen.getByLabelText("Monthly fee"), { target: { value: "42000" } });
  fireEvent.change(screen.getByLabelText("Additional costs? *"), { target: { value: "0" } });
  fireEvent.change(screen.getByLabelText("Same start/end for everyone? *"), { target: { value: "1" } });
}

function renderNewEngagement() {
  return render(
    shell(
      <MemoryRouter initialEntries={["/engagements/new"]}>
        <Routes>
          <Route path="/engagements/new" element={<NewEngagementPage />} />
          <Route path="/engagements/:id/:tab" element={<div data-testid="engagement-landing">landed</div>} />
        </Routes>
      </MemoryRouter>,
    ),
  );
}

describe("F11 · New engagement hands the offer to the engagement page", () => {
  it("remembers the offer only when POST /clients created the client", async () => {
    vi.spyOn(api, "createClient").mockResolvedValue({ id: "c-new", name: "Brand New Co", source: "manual", created: true });
    renderNewEngagement();
    await fillNewEngagement();
    fireEvent.click(screen.getByRole("button", { name: "Create engagement" }));
    expect(await screen.findByTestId("engagement-landing")).toBeInTheDocument();
    expect(api.takeAgreementsOffer("e-new")).toEqual({ client_id: "c-new", client_name: "Brand New Co", uploaded: [] });
  });

  it("makes no offer when the name matched an existing client", async () => {
    vi.spyOn(api, "createClient").mockResolvedValue({ id: "c1", name: "Client A", source: "manual", created: false });
    renderNewEngagement();
    await fillNewEngagement();
    fireEvent.click(screen.getByRole("button", { name: "Create engagement" }));
    expect(await screen.findByTestId("engagement-landing")).toBeInTheDocument();
    expect(api.takeAgreementsOffer("e-new")).toBeNull();
  });

  it("a retry after a failed engagement reuses the new client and still offers", async () => {
    const create = vi
      .spyOn(api, "createClient")
      .mockResolvedValue({ id: "c-new", name: "Brand New Co", source: "manual", created: true });
    vi.mocked(api.createEngagement).mockRejectedValueOnce(new Error("The engagement was not created."));
    renderNewEngagement();
    await fillNewEngagement();
    fireEvent.click(screen.getByRole("button", { name: "Create engagement" }));
    expect(await screen.findByText("The engagement was not created.")).toBeInTheDocument();
    expect(screen.getByLabelText("Client *")).toHaveValue("c-new");
    fireEvent.click(screen.getByRole("button", { name: "Create engagement" }));
    expect(await screen.findByTestId("engagement-landing")).toBeInTheDocument();
    expect(create).toHaveBeenCalledTimes(1);
    expect(api.createEngagement).toHaveBeenLastCalledWith(expect.objectContaining({ client_id: "c-new" }));
    expect(api.takeAgreementsOffer("e-new")?.client_id).toBe("c-new");
  });
});

function renderEngagement() {
  return render(
    shell(
      <MemoryRouter initialEntries={["/engagements/e-new/allocations"]}>
        <Routes>
          <Route path="/engagements/:id/:tab" element={<EngagementPage />} />
        </Routes>
      </MemoryRouter>,
    ),
  );
}

describe("F11 · the engagement page offer", () => {
  it("opens the shared upload dialog preset to the new client and tracks what was added", async () => {
    api.rememberAgreementsOffer("e-new", { client_id: "c-new", client_name: HOSTILE, uploaded: [] });
    renderEngagement();
    const note = await screen.findByTestId("agreements-offer");
    // The name is text, never markup.
    expect(within(note).getByTestId("agreements-offer-client").textContent).toBe(HOSTILE);
    expect(note.querySelector("img")).toBeNull();
    const add = within(note).getByRole("button", { name: "Add the NDA and MSA now (optional)" });
    await userEvent.click(add);
    const dialog = await screen.findByRole("dialog", { name: "Upload a document" });
    expect(JSON.parse(within(dialog).getByTestId("dialog-target").textContent ?? "{}")).toEqual({
      mode: "client",
      clientId: "c-new",
      clientName: HOSTILE,
      kind: "NDA",
      lockTarget: true,
    });
    expect(dialogCalls.at(-1)?.canWrite).toBe(true);
    await userEvent.click(within(dialog).getByRole("button", { name: "Fake upload" }));
    expect(await within(note).findByRole("status")).toHaveTextContent("NDA uploaded.");
    expect(api.takeAgreementsOffer("e-new")?.uploaded).toEqual(["NDA"]);
    await waitFor(() => expect(within(note).getByRole("button", { name: "Add the MSA now (optional)" })).toHaveFocus());
    await userEvent.click(within(note).getByRole("button", { name: "Add the MSA now (optional)" }));
    const second = await screen.findByRole("dialog", { name: "Upload a document" });
    expect(JSON.parse(within(second).getByTestId("dialog-target").textContent ?? "{}").kind).toBe("MSA");
    await userEvent.click(within(second).getByRole("button", { name: "Fake upload" }));
    expect(await within(note).findByRole("status")).toHaveTextContent("NDA and MSA uploaded.");
    expect(within(note).queryByRole("button", { name: /now \(optional\)/ })).toBeNull();
    await userEvent.click(within(note).getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByTestId("agreements-offer")).toBeNull();
    expect(api.takeAgreementsOffer("e-new")).toBeNull();
  });

  it("is locked with the reason for a role that cannot change agreements", async () => {
    groups = ["Delivery"];
    api.rememberAgreementsOffer("e-new", { client_id: "c-new", client_name: "Brand New Co", uploaded: [] });
    renderEngagement();
    const note = await screen.findByTestId("agreements-offer");
    const add = within(note).getByRole("button", { name: /Add the NDA and MSA now \(optional\)/ });
    expect(add).toHaveAttribute("aria-disabled", "true");
    expect(add).toHaveAttribute("data-locked", "writer");
    expect(add).toHaveAccessibleName(/Only Legal and SystemAdmin can change agreements/);
    await userEvent.click(add);
    expect(screen.queryByRole("dialog", { name: "Upload a document" })).toBeNull();
    expect(dialogCalls).toHaveLength(0);
  });

  it("shows nothing without an offer", async () => {
    renderEngagement();
    expect(await screen.findByTestId("engagement-heading")).toBeInTheDocument();
    expect(screen.queryByTestId("agreements-offer")).toBeNull();
  });
});

const JOB = "00000000-0000-0000-0000-0000000000j1";
const OPP = "00000000-0000-0000-0000-0000000000aa";
const NEW_CLIENT = "00000000-0000-0000-0000-000000000c09";

function renderStudio() {
  return render(
    shell(
      <MemoryRouter initialEntries={[`/sows/new?jobId=${JOB}`]}>
        <Routes>
          <Route path="/sows/new" element={<SowStudioPage />} />
          <Route path="/sows/:id/staffing" element={<div data-testid="staffing-landing">Staffing</div>} />
        </Routes>
      </MemoryRouter>,
    ),
  );
}

function mockPick(created: boolean) {
  vi.spyOn(clientApi, "getSowJob").mockResolvedValue({
    id: JOB,
    status: "needs_pick",
    resolution: "needs_pick",
    error: null,
    opportunity_id: null,
    sow_version_id: null,
    file_hash: "hash",
    s3_key: "sow/x.pdf",
    needs_pick: {
      signals: { legal_name: "Picked New Client Inc" },
      candidates: [],
      create_new: { legal_name: "Picked New Client Inc", domain: null, address_lines: [] },
    },
  } as unknown as clientApi.SowUploadJobResponse);
  return vi.spyOn(clientApi, "pickSowJobClient").mockResolvedValue({
    id: JOB,
    status: "done",
    resolution: created ? "created" : "matched",
    error: null,
    opportunity_id: OPP,
    sow_version_id: "00000000-0000-0000-0000-000000000ff1",
    file_hash: "hash",
    s3_key: "sow/x.pdf",
    needs_pick: null,
    client_id: NEW_CLIENT,
    client_name: "Picked New Client Inc",
    created,
  } as unknown as clientApi.SowUploadJobResponse);
}

describe("F11 · SOW studio create new client", () => {
  it("offers the NDA and MSA for the client the pick created, then continues to staffing", async () => {
    mockPick(true);
    renderStudio();
    await screen.findByTestId("client-picker-modal");
    await userEvent.click(screen.getByTestId("picker-submit"));
    const prompt = await screen.findByTestId("new-client-agreements-prompt");
    expect(within(prompt).getByRole("heading", { name: "New client created" })).toBeInTheDocument();
    expect(within(prompt).getByTestId("new-client-name").textContent).toBe("Picked New Client Inc");
    await userEvent.click(within(prompt).getByRole("button", { name: "Add the NDA and MSA now (optional)" }));
    const dialog = await screen.findByRole("dialog", { name: "Upload a document" });
    expect(JSON.parse(within(dialog).getByTestId("dialog-target").textContent ?? "{}")).toEqual({
      mode: "client",
      clientId: NEW_CLIENT,
      clientName: "Picked New Client Inc",
      kind: "NDA",
      lockTarget: true,
    });
    await userEvent.click(within(dialog).getByRole("button", { name: "Fake upload" }));
    expect(await within(prompt).findByRole("status")).toHaveTextContent("NDA uploaded.");
    await userEvent.click(within(prompt).getByTestId("continue-to-staffing"));
    expect(await screen.findByTestId("staffing-landing")).toBeInTheDocument();
  });

  it("a matched client goes straight to staffing", async () => {
    mockPick(false);
    renderStudio();
    await screen.findByTestId("client-picker-modal");
    await userEvent.click(screen.getByTestId("picker-submit"));
    expect(await screen.findByTestId("staffing-landing")).toBeInTheDocument();
    expect(screen.queryByTestId("new-client-agreements-prompt")).toBeNull();
  });

  it("locks the offer for a role that cannot change agreements", async () => {
    groups = ["Sales"];
    mockPick(true);
    renderStudio();
    await screen.findByTestId("client-picker-modal");
    await userEvent.click(screen.getByTestId("picker-submit"));
    const prompt = await screen.findByTestId("new-client-agreements-prompt");
    const add = within(prompt).getByRole("button", { name: /Add the NDA and MSA now \(optional\)/ });
    expect(add).toHaveAttribute("aria-disabled", "true");
    expect(dialogCalls).toHaveLength(0);
    await userEvent.click(within(prompt).getByTestId("continue-to-staffing"));
    expect(await screen.findByTestId("staffing-landing")).toBeInTheDocument();
  });
});
