import { useEffect, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { useAuth } from "./AuthProvider";
import { isCognitoConfigured } from "./cognito";

/**
 * Gate a subtree behind a real Cognito session.
 *
 * When Cognito is not configured (local dev with no env vars), we treat every
 * user as authenticated so the app still runs against the FastAPI
 * `X-Test-User` fallback.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated, login } = useAuth();
  const location = useLocation();

  const shouldGate = isCognitoConfigured() && !isAuthenticated;

  useEffect(() => {
    if (!shouldGate) return;
    void login(location.pathname + location.search);
  }, [shouldGate, login, location.pathname, location.search]);

  if (shouldGate) return null;
  return <>{children}</>;
}
