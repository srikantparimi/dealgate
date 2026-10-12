import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  clearTokens,
  getIdTokenClaims,
  hasStoredTokens,
  isCognitoConfigured,
  login as cognitoLogin,
  logout as cognitoLogout,
  type IdTokenClaims,
} from "./cognito";

export interface AuthUser {
  sub: string;
  email: string;
  name: string;
  groups: string[];
  role: string;
}

export interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  tokenReady: boolean;
  login: (returnTo?: string) => Promise<void>;
  logout: () => void;
}

/** Roles the API recognises, in priority order for display. */
const ROLE_PRIORITY = [
  "SystemAdmin",
  "CEO",
  "Finance",
  "Legal",
  "HR",
  "Delivery",
  "Presales",
  "SalesLeader",
  "Sales",
  "Marketing",
];

function pickPrimaryRole(groups: string[]): string {
  for (const r of ROLE_PRIORITY) {
    if (groups.includes(r)) return r;
  }
  return groups[0] ?? "User";
}

function claimsToUser(claims: IdTokenClaims | null): AuthUser | null {
  if (!claims || !claims.sub) return null;
  const groups = Array.isArray(claims["cognito:groups"])
    ? (claims["cognito:groups"] as string[])
    : [];
  return {
    sub: claims.sub,
    email: claims.email ?? "",
    // In this pool `cognito:username` is the sub UUID, so a user without
    // a `name` attribute used to read as a raw UUID in the header. Email
    // is always present on our ID tokens — prefer it over the username.
    name: claims.name ?? claims.email ?? claims["cognito:username"] ?? "User",
    groups,
    role: pickPrimaryRole(groups),
  };
}

/**
 * Local-dev identity. Only when Cognito is NOT configured (so never in a
 * deployed build): the `X-Test-User` fallback already decides identity on
 * the API side, and `VITE_TEST_GROUPS` lets the SPA render the same
 * role-gated controls the API will accept (e.g. the Playwright harness).
 */
function devUser(): AuthUser | null {
  if (isCognitoConfigured()) return null;
  const email = import.meta.env.VITE_TEST_USER as string | undefined;
  if (!email) return null;
  const groups = ((import.meta.env.VITE_TEST_GROUPS as string | undefined) ?? "")
    .split(",")
    .map((g) => g.trim())
    .filter(Boolean);
  return { sub: `local:${email}`, email, name: email.split("@")[0], groups, role: pickPrimaryRole(groups) };
}

function resolveUser(): AuthUser | null {
  return claimsToUser(getIdTokenClaims()) ?? devUser();
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() =>
    resolveUser(),
  );
  const [tokenReady, setTokenReady] = useState<boolean>(() => hasStoredTokens());

  // Keep state in sync if another tab logs in/out, or if the tokens land
  // during the callback flow after this provider has already mounted.
  useEffect(() => {
    function refresh() {
      setUser(resolveUser());
      setTokenReady(hasStoredTokens());
    }
    window.addEventListener("storage", refresh);
    window.addEventListener("dealgate:auth-changed", refresh);
    return () => {
      window.removeEventListener("storage", refresh);
      window.removeEventListener("dealgate:auth-changed", refresh);
    };
  }, []);

  const login = useCallback(async (returnTo?: string) => {
    if (!isCognitoConfigured()) {
      // Local-dev shortcut: pretend we're logged in with a dev identity so
      // pages still render against the `X-Test-User` fallback.
      return;
    }
    await cognitoLogin(returnTo);
  }, []);

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
    setTokenReady(false);
    if (isCognitoConfigured()) {
      cognitoLogout();
    } else if (typeof window !== "undefined") {
      window.location.assign("/");
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: Boolean(user),
      tokenReady,
      login,
      logout,
    }),
    [user, tokenReady, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return ctx;
}

/**
 * Fire this after `handleCallback` so mounted providers refresh from
 * sessionStorage without needing a full reload.
 */
export function notifyAuthChanged(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event("dealgate:auth-changed"));
}
