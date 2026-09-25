import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as apiClient from "../../api/client";
import { AuthProvider } from "../../auth/AuthProvider";
import { AppShell } from "../../ui-v2/AppShell";
import * as cognito from "../../auth/cognito";

function mockUser(groups: string[] = ["Sales"]) {
  vi.spyOn(cognito, "getIdTokenClaims").mockReturnValue({
    sub: "user-1",
    email: "alice@smartek21.com",
    name: "Alice",
    "cognito:groups": groups,
  });
  vi.spyOn(cognito, "hasStoredTokens").mockReturnValue(true);
}

function renderShell(children = <p>content</p>) {
  return render(
    <MemoryRouter initialEntries={["/deals"]}>
      <AuthProvider>
        <AppShell>{children}</AppShell>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("AppShell", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, "listInboxNotifications").mockResolvedValue({
      items: [],
      unread_count: 0,
    });
    // Default: authenticated Sales user so the primary nav renders.
    mockUser(["Sales"]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the primary navigation, header and children", async () => {
    renderShell(<p data-testid="page-content">Hello</p>);

    await waitFor(() => {
      // Two nav landmarks: 'Primary' (sidebar) and 'Breadcrumb' (header).
      expect(
        screen.getByRole("navigation", { name: /primary/i }),
      ).toBeInTheDocument();
    });

    expect(
      screen.getByRole("navigation", { name: /breadcrumb/i }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("page-content")).toHaveTextContent("Hello");
    // Global search trigger present.
    expect(
      screen.getByRole("button", { name: /open global search/i }),
    ).toBeInTheDocument();
    // Notifications bell.
    expect(
      screen.getByRole("button", { name: /notifications/i }),
    ).toBeInTheDocument();
    // Profile menu.
    expect(
      screen.getByRole("button", { name: /open profile menu/i }),
    ).toBeInTheDocument();
  });

  it("hides the Settings nav item for non-admin roles", async () => {
    renderShell();

    // Sales does not have SystemAdmin/Finance/Legal/CEO, so Settings hides.
    await waitFor(() => {
      expect(
        screen.getByRole("link", { name: /command center/i }),
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("link", { name: /^settings$/i }),
    ).not.toBeInTheDocument();
  });

  it("shows the Settings nav item when the user is a SystemAdmin", async () => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient, "listInboxNotifications").mockResolvedValue({
      items: [],
      unread_count: 0,
    });
    mockUser(["SystemAdmin"]);

    renderShell();

    await waitFor(() => {
      expect(
        screen.getByRole("link", { name: /^settings$/i }),
      ).toBeInTheDocument();
    });
  });

  it("focus lands on interactive controls in a logical order", async () => {
    renderShell();
    const user = userEvent.setup();

    // Tab to the first focusable interactive element — should be inside the
    // navigation drawer trigger (mobile) or sidebar link (desktop). We just
    // verify that Tab moves focus, i.e. no interactive control is missing
    // a tab index.
    await waitFor(() => {
      expect(
        screen.getAllByRole("link").length,
      ).toBeGreaterThan(0);
    });
    await user.tab();
    expect(document.activeElement).not.toBe(document.body);
  });
});
