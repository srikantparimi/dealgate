import type { ReactNode } from "react";
import { useEffect } from "react";

/**
 * Right-anchored slide-out panel. Same close semantics as `Modal` (backdrop
 * click + Escape). Wider than a modal because drawers usually host multiple
 * sub-panels (edit + history).
 */
export function Drawer({
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
        zIndex: 50,
        display: "flex",
        justifyContent: "flex-end",
      }}
      onClick={onClose}
    >
      <aside
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "white",
          width: 480,
          maxWidth: "90vw",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          boxShadow: "-20px 0 40px rgba(0,0,0,0.2)",
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
        <div style={{ padding: 16, flex: 1, overflow: "auto" }}>{children}</div>
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
      </aside>
    </div>
  );
}
