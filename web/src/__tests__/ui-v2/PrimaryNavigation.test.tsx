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
      <PrimaryNavigation groups={groups} />
    </MemoryRouter>,
  );
}

describe("PrimaryNavigation", () => {
  it("groups nav items by the approved Command Center sections", () => {
    const ids = NAV_GROUPS.map((g) => g.id);
    expect(ids).toEqual([
      "workspace",
      "business",
      "supporting",
      "administration",
    ]);
  });

  it("renders business and supporting work for a Sales user", () => {
    renderNav(["Sales"]);
    expect(
      screen.getByRole("link", { name: /command center/i }),
    ).toHaveAttribute("href", "/command");
    expect(
      screen.getByRole("link", { name: /^pipeline$/i }),
    ).toHaveAttribute("href", "/pipeline");
    expect(
      screen.getByRole("link", { name: /sows & approvals/i }),
    ).toHaveAttribute("href", "/sows");
    expect(
      screen.getByRole("link", { name: /^reports$/i }),
    ).toHaveAttribute("href", "/reports");
    // Settings requires SystemAdmin/Finance/Legal/CEO.
    expect(
      screen.queryByRole("link", { name: /settings/i }),
    ).not.toBeInTheDocument();
  });

  it("shows Settings for privileged roles", () => {
    renderNav(["Finance"]);
    expect(
      screen.getByRole("link", { name: /settings/i }),
    ).toHaveAttribute("href", "/settings");
  });

  it("shows managed People to HR without requiring administrator access", () => {
    renderNav(["HR"]);
    expect(screen.getByRole("link", { name: "People" })).toHaveAttribute("href", "/people");
  });

  it("does not offer named workforce supply to Sales", () => {
    renderNav(["Sales"]);
    expect(screen.queryByRole("link", { name: "People" })).not.toBeInTheDocument();
  });

  it("filterItems respects requireAny gating", () => {
    const admin = NAV_GROUPS.find((g) => g.id === "administration")!.items;
    expect(filterItems(admin, [])).toEqual([]);
    expect(filterItems(admin, ["Sales"]).map((item) => item.to)).toEqual([
      "/import/forecast-model",
    ]);
    expect(filterItems(admin, ["CEO"]).length).toBeGreaterThan(0);
  });
});
