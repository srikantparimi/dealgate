import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../api/client";
import { ClientListPage, coverageTone } from "../pages/ClientList";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/clients"]}>
      <ClientListPage />
    </MemoryRouter>,
  );
}

const sample: apiClient.ClientListResponse = {
  items: [
    {
      id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
      name: "Acme Corp",
      hubspot_company_id: "COMP-1",
      coverage_state: "MSA missing",
      opportunity_count: 2,
      owner_ids: [],
      owners: [],
      sources: [],
    },
  ],
  page: 1,
  size: 25,
  total: 1,
};

describe("ClientList", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders rows from listClients", async () => {
    vi.spyOn(apiClient, "listClients").mockResolvedValue(sample);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Acme Corp")).toBeInTheDocument();
    });
    expect(screen.getByText("MSA missing")).toBeInTheDocument();
    expect(screen.getByText("COMP-1")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("shows the empty state when the list is empty", async () => {
    vi.spyOn(apiClient, "listClients").mockResolvedValue({
      items: [],
      page: 1,
      size: 25,
      total: 0,
    });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("No clients yet")).toBeInTheDocument();
    });
  });

  it("shows an error state when the fetch fails", async () => {
    vi.spyOn(apiClient, "listClients").mockRejectedValue(new Error("boom"));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    });
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("maps coverage strings to the right chip tone", () => {
    expect(coverageTone("Complete")).toBe("ok");
    expect(coverageTone("NDA missing")).toBe("warn");
    expect(coverageTone("MSA missing")).toBe("warn");
    expect(coverageTone("NDA + MSA missing")).toBe("warn");
    expect(coverageTone("NDA expired")).toBe("block");
    expect(coverageTone("MSA expired")).toBe("block");
    expect(coverageTone("Awaiting signature")).toBe("warn");
    expect(coverageTone("Something else")).toBe("neutral");
  });
});
