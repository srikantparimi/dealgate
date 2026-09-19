import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../../auth/AuthProvider";
import * as cognito from "../../auth/cognito";
import { PreferencesProvider, usePreferences } from "../../ui-v2/preferences";
import { ProfileMenu } from "../../ui-v2/ProfileMenu";

/**
 * Focus of these tests: appearance + density preferences and role/name
 * rendering on the trigger. The full dropdown-panel interaction is not
 * exercised here because Radix Popper depends on layout metrics jsdom
 * does not provide; we cover the underlying persistence contract by
 * driving `usePreferences` directly and confirming the localStorage
 * side-effect.
 */

function Probe() {
  const p = usePreferences();
  return (
    <div>
      <span data-testid="appearance">{p.appearance}</span>
      <span data-testid="density">{p.density}</span>
      <button type="button" onClick={() => p.setAppearance("dark")}>
        set-dark
      </button>
      <button type="button" onClick={() => p.setDensity("compact")}>
        set-compact
      </button>
    </div>
  );
}

function renderMenu() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <PreferencesProvider>
          <ProfileMenu
            user={{
              sub: "u1",
              email: "alice@smartek21.com",
              name: "Alice Adams",
              groups: ["Sales"],
              role: "Sales",
            }}
          />
          <Probe />
        </PreferencesProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("ProfileMenu", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.spyOn(cognito, "hasStoredTokens").mockReturnValue(true);
    vi.spyOn(cognito, "getIdTokenClaims").mockReturnValue({
      sub: "u1",
      email: "alice@smartek21.com",
      name: "Alice Adams",
      "cognito:groups": ["Sales"],
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("shows the accessible trigger with the user's initials and a chevron", () => {
    renderMenu();
    const trigger = screen.getByRole("button", { name: /open profile menu/i });
    expect(trigger).toBeInTheDocument();
    // Initials rendered as 'AA' for Alice Adams.
    expect(trigger).toHaveTextContent("AA");
    expect(trigger).toHaveTextContent(/alice adams/i);
  });

  it("persists Appearance changes to localStorage and reflects them in state", async () => {
    renderMenu();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^set-dark$/i }));

    await waitFor(() => {
      expect(window.localStorage.getItem("dealgate:v2:appearance")).toBe(
        "dark",
      );
    });
    expect(screen.getByTestId("appearance")).toHaveTextContent("dark");
    // Global attribute updated by the effect in the provider.
    await waitFor(() => {
      expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    });
  });

  it("persists Density changes to localStorage and reflects them in state", async () => {
    renderMenu();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /^set-compact$/i }));

    await waitFor(() => {
      expect(window.localStorage.getItem("dealgate:v2:density")).toBe(
        "compact",
      );
    });
    expect(screen.getByTestId("density")).toHaveTextContent("compact");
    await waitFor(() => {
      expect(document.documentElement.getAttribute("data-density")).toBe(
        "compact",
      );
    });
  });

  it("reads a previously stored appearance on mount", async () => {
    window.localStorage.setItem("dealgate:v2:appearance", "light");
    window.localStorage.setItem("dealgate:v2:density", "compact");
    renderMenu();
    // Ensure initial values reflect storage.
    expect(screen.getByTestId("appearance")).toHaveTextContent("light");
    expect(screen.getByTestId("density")).toHaveTextContent("compact");
    await act(async () => {});
  });
});
