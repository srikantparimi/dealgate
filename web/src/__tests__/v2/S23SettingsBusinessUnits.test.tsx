// S23-PL2 F18 · Settings → Business units: edit the HubSpot region →
// business unit map, see unmapped region values with their deal counts, save.
// A business unit is always shown with its region (US holds two of them).
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../../api/client";
import type { RegionMap } from "../../api/client";
import { SettingsShellPage } from "../../pages/v2/SettingsShell";
import { BusinessUnitsSection } from "../../pages/v2/settings/BusinessUnitsSection";

const useAuthMock = vi.fn();
vi.mock("../../auth/AuthProvider", () => ({ useAuth: () => useAuthMock() }));

const MAP: RegionMap = {
  rows: [
    { hubspot_value: "South Africa", business_unit: "Retro Rabbit", region: "South Africa", note: null },
    { hubspot_value: "US", business_unit: "ST21", region: "US", note: null },
    { hubspot_value: "US - IT Avalon", business_unit: "IT Avalon", region: "US", note: null },
    { hubspot_value: "US - IT Avalon (Staffing)", business_unit: "IT Avalon", region: "US", note: "Staffing" },
  ],
  unmapped_on_deals: [{ hubspot_value: "US - Other", deals: 2 }],
  deals_without_region: 1,
  business_units: ["ST21", "IT Avalon", "Retro Rabbit"],
};

/** A mapping row, named by the HubSpot value it had when it appeared (stable while editing). */
function row(label: string): HTMLElement {
  return screen.getByRole("row", { name: `Mapping for ${label}` });
}

beforeEach(() => {
  vi.restoreAllMocks();
  useAuthMock.mockReturnValue({ user: { sub: "u1", email: "admin@example.test", name: "Admin", groups: ["SystemAdmin"] } });
  vi.spyOn(api, "getBusinessUnitMap").mockResolvedValue(structuredClone(MAP));
});

describe("BusinessUnitsSection", () => {
  it("opens pre-filled with every mapping, each business unit shown with its region", async () => {
    render(<BusinessUnitsSection />);
    expect(await screen.findByDisplayValue("US - IT Avalon (Staffing)")).toBeInTheDocument();
    expect(within(row("US - IT Avalon (Staffing)")).getByText("IT Avalon · US · Staffing")).toBeInTheDocument();
    expect(within(row("US")).getByText("ST21 · US")).toBeInTheDocument();
    expect(within(row("South Africa")).getByText("Retro Rabbit · South Africa")).toBeInTheDocument();
    expect(screen.getByText(/US covers two different business units, ST21 and IT Avalon/)).toBeInTheDocument();
  });

  it("lists unmapped HubSpot values with their deal counts and maps one", async () => {
    render(<BusinessUnitsSection />);
    const unmapped = await screen.findByRole("region", { name: "Unmapped HubSpot values" });
    expect(within(unmapped).getByText("US - Other")).toBeInTheDocument();
    expect(within(unmapped).getByText("2 deals")).toBeInTheDocument();
    expect(screen.getByText(/^1 deal has no HubSpot region\./)).toBeInTheDocument();
    fireEvent.click(within(unmapped).getByRole("button", { name: "Map US - Other" }));
    fireEvent.click(within(unmapped).getByRole("button", { name: "Map US - Other" })); // once is enough
    expect(screen.getAllByDisplayValue("US - Other")).toHaveLength(1);
    // The admin decides the business unit and region; nothing is guessed.
    const save = screen.getByRole("button", { name: "Save mapping" });
    expect(save).toBeDisabled();
    fireEvent.change(within(row("US - Other")).getByLabelText("Business unit for US - Other"), {
      target: { value: "ST21" },
    });
    expect(save).toBeDisabled();
    fireEvent.change(within(row("US - Other")).getByLabelText("Region for US - Other"), { target: { value: "US" } });
    expect(save).toBeEnabled();
    expect(within(row("US - Other")).getByText("ST21 · US")).toBeInTheDocument();
  });

  it("saves the edited map and shows the server's result", async () => {
    const saved: RegionMap = {
      ...structuredClone(MAP),
      rows: MAP.rows.map((r) => (r.hubspot_value === "US" ? { ...r, business_unit: "IT Avalon" } : r)),
      unmapped_on_deals: [],
    };
    const save = vi.spyOn(api, "saveBusinessUnitMap").mockResolvedValue(saved);
    render(<BusinessUnitsSection />);
    const select = await screen.findByLabelText("Business unit for US");
    expect(screen.getByRole("button", { name: "Save mapping" })).toBeDisabled(); // nothing changed yet
    fireEvent.change(select, { target: { value: "IT Avalon" } });
    expect(within(row("US")).getByText("IT Avalon · US")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save mapping" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save.mock.calls[0][0]).toEqual(saved.rows);
    expect(await screen.findByRole("status")).toHaveTextContent("Saved. Every deal shows the new business units now.");
    expect(screen.queryByRole("region", { name: "Unmapped HubSpot values" })).toBeNull();
  });

  it("shows the server's message when it refuses the map", async () => {
    vi.spyOn(api, "saveBusinessUnitMap").mockRejectedValue(
      new api.ApiError(422, { detail: "“US” is mapped twice. Each HubSpot value maps to one business unit." },
        "“US” is mapped twice. Each HubSpot value maps to one business unit."),
    );
    render(<BusinessUnitsSection />);
    fireEvent.change(await screen.findByLabelText("Note for US"), { target: { value: "Core" } });
    fireEvent.click(screen.getByRole("button", { name: "Save mapping" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("“US” is mapped twice.");
  });

  it("flags a value mapped twice before saving", async () => {
    render(<BusinessUnitsSection />);
    fireEvent.click(await screen.findByRole("button", { name: "Add mapping" }));
    const added = row("new row 5");
    fireEvent.change(within(added).getByLabelText("HubSpot value for new row 5"), { target: { value: "US" } });
    fireEvent.change(within(added).getByLabelText("Business unit for new row 5"), { target: { value: "IT Avalon" } });
    fireEvent.change(within(added).getByLabelText("Region for new row 5"), { target: { value: "US" } });
    expect(screen.getByText("“US” is listed twice.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save mapping" })).toBeDisabled();
  });

  it("removes a mapping", async () => {
    const save = vi.spyOn(api, "saveBusinessUnitMap").mockResolvedValue(structuredClone(MAP));
    render(<BusinessUnitsSection />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove the mapping for South Africa" }));
    fireEvent.click(screen.getByRole("button", { name: "Save mapping" }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save.mock.calls[0][0].map((r) => r.hubspot_value)).toEqual(["US", "US - IT Avalon", "US - IT Avalon (Staffing)"]);
  });

  it("explains a missing permission instead of failing", async () => {
    vi.mocked(api.getBusinessUnitMap).mockRejectedValue(new api.ApiError(403, { detail: "insufficient role" }));
    render(<BusinessUnitsSection />);
    expect(await screen.findByText("You don't have access to this section.")).toBeInTheDocument();
  });
});

describe("Settings navigation", () => {
  function renderAt(path: string) {
    render(
      <MemoryRouter initialEntries={[path]}>
        <Routes><Route path="/settings/:section?" element={<SettingsShellPage />} /></Routes>
      </MemoryRouter>,
    );
  }

  it("serves the section at /settings/business-units for a SystemAdmin", async () => {
    renderAt("/settings/business-units");
    const nav = await screen.findByRole("navigation", { name: /Settings sections/i });
    expect(within(nav).getByRole("link", { name: /Business units/ })).toHaveAttribute("href", "/settings/business-units");
    expect(await screen.findByDisplayValue("US - IT Avalon (Staffing)")).toBeInTheDocument();
  });

  it("hides the section from other roles", async () => {
    useAuthMock.mockReturnValue({ user: { sub: "u2", email: "rep@example.test", name: "Rep", groups: ["Sales"] } });
    renderAt("/settings/business-units");
    const nav = await screen.findByRole("navigation", { name: /Settings sections/i });
    expect(within(nav).queryByRole("link", { name: /Business units/ })).toBeNull();
    expect(screen.getByText("You don't have access to this section.")).toBeInTheDocument();
  });
});
