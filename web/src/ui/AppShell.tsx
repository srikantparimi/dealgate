import type { ReactNode } from "react";

type User = { name: string; role: string };

export function AppShell({
  user,
  nav,
  children,
}: {
  user: User;
  nav?: ReactNode;
  children: ReactNode;
}) {
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
        <span style={{ color: "#6b7280" }}>
          {user.name} · {user.role}
        </span>
      </header>
      <main style={{ padding: "24px", maxWidth: 960, margin: "0 auto" }}>{children}</main>
    </div>
  );
}
