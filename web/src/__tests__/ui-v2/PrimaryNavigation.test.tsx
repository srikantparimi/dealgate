import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import {
  filterItems,
  NAV_GROUPS,
  PrimaryNavigation,
} from "../../ui-v2/PrimaryNavigation";

function renderNav(groups: string[]) {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <PrimaryNavigation groups={groups} showLegacy={false} />
    </MemoryRouter>,
  );
}

describe("PrimaryNavigation", () => {
  it("groups nav items by the five spec sections", () => {
    const ids = NAV_GROUPS.map((g) => g.id);
    expect(ids).toEqual([
      "workspace",
      "growth",
      "commitments",
      "operations",
      "administration",
    ]);
  });

  it("renders workspace + growth + commitments items for a Sales user", () => {
    renderNav(["Sales"]);
    expect(
      screen.getByRole("link", { name: /command center/i }),
    ).toHaveAttribute("href", "/command");
    expect(
      screen.getByRole("link", { name: /pipeline clients/i }),
    ).toHaveAttribute("href", "/pipeline");
    expect(
      screen.getByRole("link", { name: /sow approvals/i }),
    ).toHaveAttribute("href", "/sows");
    expect(
      screen.getByRole("link", { name: /reporting/i }),
    ).toHaveAttribute("href", "/reports");
    // Settings requires SystemAdmin/Finance/Legal/CEO.
    expect(
      screen.queryByRole("link", { name: /settings & controls/i }),
    ).not.toBeInTheDocument();
  });

  it("shows Settings for privileged roles", () => {
    renderNav(["Finance"]);
    expect(
      screen.getByRole("link", { name: /settings & controls/i }),
    ).toHaveAttribute("href", "/settings");
  });

  it("filterItems respects requireAny gating", () => {
    const admin = NAV_GROUPS.find((g) => g.id === "administration")!.items;
    expect(filterItems(admin, [])).toEqual([]);
    expect(filterItems(admin, ["Sales"])).toEqual([]);
    expect(filterItems(admin, ["CEO"]).length).toBeGreaterThan(0);
  });
});
