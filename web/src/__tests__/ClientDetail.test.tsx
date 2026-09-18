import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import { ClientDetailPage } from "../pages/ClientDetail";

const CLIENT_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc";

const sample: apiClient.ClientDetail = {
  id: CLIENT_ID,
  name: "Acme Corp",
  hubspot_company_id: "COMP-1",
  timezone: "America/Los_Angeles",
  coverage_state: "MSA missing",
  legal_entities: [
    { id: "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee", name: "Acme Inc.", country: "US" },
  ],
  agreements: [
    {
      id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      legal_entity_id: "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
      kind: "NDA",
      effective_date: "2025-01-01",
      expiry_date: "2027-01-01",
    },
  ],
  opportunities: [
    {
      id: "dddddddd-dddd-dddd-dddd-dddddddddddd",
      hubspot_deal_id: "H-1",
      governance_status: "Intake",
      sales_stage: "Qualified",
      engagement_type: "TM",
      owner_id: null,
      next_client_action: "Send SOW",
      next_client_date: "2026-03-01",
    },
  ],
  recent_activity: [
    {
      id: "ffffffff-ffff-ffff-ffff-ffffffffffff",
      ts: "2026-09-01T10:00:00Z",
      actor_id: null,
      action: "opportunity.updated",
      entity: "opportunity",
      entity_id: "dddddddd-dddd-dddd-dddd-dddddddddddd",
      before: { engagement_type: null },
      after: { engagement_type: "TM" },
    },
  ],
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/clients/${CLIENT_ID}`]}>
      <Routes>
        <Route path="/clients/:id" element={<ClientDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ClientDetail", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the four panels", async () => {
    vi.spyOn(apiClient, "getClient").mockResolvedValue(sample);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Acme Corp")).toBeInTheDocument();
    });
    expect(
      screen.getByRole("heading", { name: "Client + entities" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Agreements" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Opportunities" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Recent activity" }),
    ).toBeInTheDocument();
  });

  it("renders the coverage chip using the coverage state color", async () => {
    vi.spyOn(apiClient, "getClient").mockResolvedValue(sample);
    renderPage();
    const chip = await screen.findByText("MSA missing");
    // Warn tone background from StatusChip (see ui/StatusChip.tsx).
    expect(chip).toHaveStyle({ background: "#fef3c7" });
  });

  it("renders a deep link into the linked deal", async () => {
    vi.spyOn(apiClient, "getClient").mockResolvedValue(sample);
    renderPage();
    const link = await screen.findByRole("link", { name: "H-1" });
    expect(link).toHaveAttribute(
      "href",
      "/deals/dddddddd-dddd-dddd-dddd-dddddddddddd",
    );
  });

  it("shows the recent activity action", async () => {
    vi.spyOn(apiClient, "getClient").mockResolvedValue(sample);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("opportunity.updated")).toBeInTheDocument();
    });
  });

  it("shows an error state when the fetch fails", async () => {
    vi.spyOn(apiClient, "getClient").mockRejectedValue(new Error("nope"));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    });
    expect(screen.getByText("nope")).toBeInTheDocument();
  });

  it("uses the block tone chip when NDA is expired", async () => {
    vi.spyOn(apiClient, "getClient").mockResolvedValue({
      ...sample,
      coverage_state: "NDA expired",
    });
    renderPage();
    const chip = await screen.findByText("NDA expired");
    // Block tone background from StatusChip.
    expect(chip).toHaveStyle({ background: "#fee2e2" });
  });

  it("uses the ok tone chip when coverage is Complete", async () => {
    vi.spyOn(apiClient, "getClient").mockResolvedValue({
      ...sample,
      coverage_state: "Complete",
    });
    renderPage();
    const chip = await screen.findByText("Complete");
    // Ok tone background from StatusChip.
    expect(chip).toHaveStyle({ background: "#d1fae5" });
  });
});
