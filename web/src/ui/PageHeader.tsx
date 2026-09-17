import type { ReactNode } from "react";

export function PageHeader({
  title,
  subtitle,
  right,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        marginBottom: 24,
        gap: 16,
      }}
    >
      <div>
        <h1 style={{ margin: 0, fontSize: 24, color: "#111827" }}>{title}</h1>
        {subtitle ? (
          <div style={{ marginTop: 4, color: "#6b7280", fontSize: 14 }}>{subtitle}</div>
        ) : null}
      </div>
      {right ? <div style={{ flexShrink: 0 }}>{right}</div> : null}
    </header>
  );
}
