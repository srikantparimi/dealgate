import type { ReactNode } from "react";
import { useAuth, type AuthUser } from "../auth/AuthProvider";

/**
 * User rendered in the header. May be null in local dev where Cognito is not
 * configured; in that case we show a "dev user" hint instead of a real name.
 */
type ShellUser = Pick<AuthUser, "name" | "groups"> | null;

export function AppShell({
  user,
  nav,
  children,
}: {
  user: ShellUser;
  nav?: ReactNode;
  children: ReactNode;
}) {
  const { logout } = useAuth();
  const groups = user?.groups ?? [];
  return (
    <div style={{ fontFamily: "system-ui, sans-serif", minHeight: "100vh" }}>
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "12px 24px",
          borderBottom: "1px solid #e5e7eb",
          gap: 24,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
          <strong>DealGate</strong>
          {nav ?? null}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span style={{ color: "#6b7280" }} data-testid="shell-user">
            {user ? (
              <>
                {user.name}
                {groups.length > 0 ? ` · ${groups.join(", ")}` : ""}
              </>
            ) : (
              "Local dev"
            )}
          </span>
          <button
            type="button"
            onClick={logout}
            style={{
              fontSize: 13,
              color: "#374151",
              background: "none",
              border: "none",
              padding: 0,
              cursor: "pointer",
              textDecoration: "underline",
            }}
          >
            Sign out
          </button>
        </div>
      </header>
      <main style={{ padding: "24px", maxWidth: 960, margin: "0 auto" }}>{children}</main>
    </div>
  );
}
