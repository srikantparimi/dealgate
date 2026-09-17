import type { ReactNode } from "react";
import { useEffect } from "react";

/**
 * Centered modal dialog with a fixed backdrop. Escape and backdrop-click both
 * dismiss. Content owns its own form + buttons — this is a shell only.
 *
 * Purely presentational: no data hooks, no page-level state. Callers control
 * the open state and render the body / footer they need.
 */
export function Modal({
  open,
  title,
  onClose,
  children,
  footer,
  ariaLabel,
}: {
  open: boolean;
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  ariaLabel?: string;
}) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={ariaLabel ?? (typeof title === "string" ? title : undefined)}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15, 23, 42, 0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 50,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "white",
          borderRadius: 8,
          minWidth: 420,
          maxWidth: 560,
          maxHeight: "85vh",
          overflow: "auto",
          boxShadow: "0 20px 40px rgba(0,0,0,0.2)",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <header
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "12px 16px",
            borderBottom: "1px solid #e5e7eb",
          }}
        >
          <h2 style={{ margin: 0, fontSize: 16, color: "#111827" }}>{title}</h2>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              fontSize: 18,
              cursor: "pointer",
              color: "#6b7280",
            }}
          >
            ×
          </button>
        </header>
        <div style={{ padding: 16 }}>{children}</div>
        {footer ? (
          <footer
            style={{
              display: "flex",
              justifyContent: "flex-end",
              gap: 8,
              padding: "12px 16px",
              borderTop: "1px solid #e5e7eb",
              background: "#f9fafb",
            }}
          >
            {footer}
          </footer>
        ) : null}
      </div>
    </div>
  );
}
