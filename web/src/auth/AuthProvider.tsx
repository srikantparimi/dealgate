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
    name: claims.name ?? claims["cognito:username"] ?? claims.email ?? "User",
    groups,
    role: pickPrimaryRole(groups),
  };
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() =>
    claimsToUser(getIdTokenClaims()),
  );
  const [tokenReady, setTokenReady] = useState<boolean>(() => hasStoredTokens());

  // Keep state in sync if another tab logs in/out, or if the tokens land
  // during the callback flow after this provider has already mounted.
  useEffect(() => {
    function refresh() {
      setUser(claimsToUser(getIdTokenClaims()));
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
