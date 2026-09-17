export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div
      role="status"
      style={{
        border: "1px dashed #e5e7eb",
        borderRadius: 8,
        padding: 24,
        textAlign: "center",
        color: "#6b7280",
      }}
    >
      <div style={{ fontWeight: 600, color: "#374151", marginBottom: 4 }}>{title}</div>
      {hint ? <div style={{ fontSize: 14 }}>{hint}</div> : null}
    </div>
  );
}
