import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../auth/AuthProvider";
import { RequireAuth } from "../auth/RequireAuth";
import * as cognito from "../auth/cognito";

function renderGuarded() {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={["/deals"]}>
        <Routes>
          <Route
            path="/deals"
            element={
              <RequireAuth>
                <div>Protected content</div>
              </RequireAuth>
            }
          />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

describe("RequireAuth", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("renders nothing and calls login() when unauthenticated", async () => {
    vi.spyOn(cognito, "isCognitoConfigured").mockReturnValue(true);
    const login = vi.spyOn(cognito, "login").mockResolvedValue(undefined);

    renderGuarded();

    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(login).toHaveBeenCalledTimes(1);
    });
    expect(login.mock.calls[0][0]).toBe("/deals");
  });

  it("renders children when Cognito is not configured (local dev)", () => {
    vi.spyOn(cognito, "isCognitoConfigured").mockReturnValue(false);
    renderGuarded();
    expect(screen.getByText("Protected content")).toBeInTheDocument();
  });
});
