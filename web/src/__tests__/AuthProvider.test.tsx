import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "../auth/AuthProvider";
import * as cognito from "../auth/cognito";

// Cognito id_token payload built by hand — three dots so `decodeJwtPayload`
// finds the middle segment.
function makeIdToken(claims: Record<string, unknown>): string {
  const body = btoa(JSON.stringify(claims))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  return `header.${body}.sig`;
}

const CLAIMS = {
  sub: "user-1",
  email: "alice@smartek21.com",
  name: "Alice",
  "cognito:groups": ["Finance", "SystemAdmin"],
};

function Probe() {
  const auth = useAuth();
  return (
    <div>
      <div data-testid="is-auth">{String(auth.isAuthenticated)}</div>
      <div data-testid="name">{auth.user?.name ?? "-"}</div>
      <div data-testid="role">{auth.user?.role ?? "-"}</div>
      <div data-testid="groups">{auth.user?.groups.join(",") ?? "-"}</div>
      <button type="button" onClick={() => auth.logout()}>
        logout
      </button>
    </div>
  );
}

describe("AuthProvider", () => {
  const originalLocation = window.location;

  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
    // Pretend Cognito IS configured so logout goes through the hosted-UI
    // path. We stub `window.location.assign` to observe the redirect.
    vi.spyOn(cognito, "isCognitoConfigured").mockReturnValue(true);
    // JSDOM's window.location is not directly writable; replace it wholesale.
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...originalLocation, assign: vi.fn() },
    });
  });

  afterEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
  });

  it("hydrates from sessionStorage tokens", () => {
    sessionStorage.setItem("dealgate.cognito.access_token", "atk");
    sessionStorage.setItem("dealgate.cognito.id_token", makeIdToken(CLAIMS));
    sessionStorage.setItem(
      "dealgate.cognito.expires_at",
      String(Date.now() + 3_600_000),
    );

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    expect(screen.getByTestId("is-auth").textContent).toBe("true");
    expect(screen.getByTestId("name").textContent).toBe("Alice");
    // SystemAdmin outranks Finance in ROLE_PRIORITY.
    expect(screen.getByTestId("role").textContent).toBe("SystemAdmin");
    expect(screen.getByTestId("groups").textContent).toBe("Finance,SystemAdmin");
  });

  it("reports unauthenticated when no token is stored", () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    expect(screen.getByTestId("is-auth").textContent).toBe("false");
    expect(screen.getByTestId("name").textContent).toBe("-");
  });

  it("logout clears sessionStorage and redirects", async () => {
    sessionStorage.setItem("dealgate.cognito.access_token", "atk");
    sessionStorage.setItem("dealgate.cognito.id_token", makeIdToken(CLAIMS));
    sessionStorage.setItem(
      "dealgate.cognito.expires_at",
      String(Date.now() + 3_600_000),
    );

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "logout" }));

    expect(sessionStorage.getItem("dealgate.cognito.access_token")).toBeNull();
    expect(sessionStorage.getItem("dealgate.cognito.id_token")).toBeNull();
    expect(window.location.assign).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("is-auth").textContent).toBe("false");
  });

  it("picks up tokens written after mount via the auth-changed event", () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    expect(screen.getByTestId("is-auth").textContent).toBe("false");

    act(() => {
      sessionStorage.setItem("dealgate.cognito.access_token", "atk");
      sessionStorage.setItem("dealgate.cognito.id_token", makeIdToken(CLAIMS));
      sessionStorage.setItem(
        "dealgate.cognito.expires_at",
        String(Date.now() + 3_600_000),
      );
      window.dispatchEvent(new Event("dealgate:auth-changed"));
    });

    expect(screen.getByTestId("is-auth").textContent).toBe("true");
    expect(screen.getByTestId("name").textContent).toBe("Alice");
  });
});
