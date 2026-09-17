export function ErrorState({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  const message =
    error instanceof Error ? error.message : String(error ?? "Unknown error");
  return (
    <div
      role="alert"
      style={{
        border: "1px solid #fecaca",
        background: "#fef2f2",
        color: "#991b1b",
        padding: 16,
        borderRadius: 8,
      }}
    >
      <div style={{ fontWeight: 600, marginBottom: 4 }}>Something went wrong</div>
      <div style={{ fontSize: 14, marginBottom: retry ? 12 : 0 }}>{message}</div>
      {retry ? (
        <button
          type="button"
          onClick={retry}
          style={{
            background: "#991b1b",
            color: "white",
            border: "none",
            padding: "6px 12px",
            borderRadius: 6,
            cursor: "pointer",
          }}
        >
          Retry
        </button>
      ) : null}
    </div>
  );
}
