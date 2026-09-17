import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { notifyAuthChanged } from "../auth/AuthProvider";
import { handleCallback } from "../auth/cognito";

/**
 * Landing route for the Cognito hosted-UI redirect. Exchanges the code for
 * tokens, then navigates back to the URL the user originally requested.
 */
export function AuthCallback() {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    handleCallback()
      .then((returnTo) => {
        if (cancelled) return;
        notifyAuthChanged();
        navigate(returnTo || "/", { replace: true });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  if (error) {
    return (
      <main style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
        <h1>Sign-in failed</h1>
        <p style={{ color: "#b91c1c" }}>{error}</p>
        <p>
          <a href="/">Return to home</a>
        </p>
      </main>
    );
  }
  return (
    <main style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <p>Signing you in…</p>
    </main>
  );
}
