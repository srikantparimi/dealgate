import { useCallback, useEffect, useRef, useState } from "react";
import type { NotificationRow } from "../api/client";
import {
  ApiError,
  listInboxNotifications,
  markNotificationRead,
} from "../api/client";

/**
 * Header bell: shows unread in-app notification count and, on click, a
 * dropdown panel of the 10 latest notifications. Clicking a row marks it read
 * and shrinks the count. Polls every 60s so users get near-live updates
 * without WebSockets.
 */
export function NotificationBell() {
  const [items, setItems] = useState<NotificationRow[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await listInboxNotifications(10);
      setItems(res.items);
      setUnread(res.unread_count);
      setError(null);
    } catch (err) {
      // 401 while the auth is settling is normal; keep the bell silent.
      if (err instanceof ApiError && err.status === 401) return;
      setError(err instanceof ApiError ? err.message : "Failed to load");
    }
  }, []);

  useEffect(() => {
    void load();
    const t = window.setInterval(() => void load(), 60_000);
    return () => window.clearInterval(t);
  }, [load]);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);

  async function onRowClick(row: NotificationRow) {
    if (row.read_at) return;
    try {
      await markNotificationRead(row.id);
      setItems((prev) =>
        prev.map((r) => (r.id === row.id ? { ...r, read_at: new Date().toISOString() } : r)),
      );
      setUnread((n) => Math.max(0, n - 1));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Mark read failed");
    }
  }

  return (
    <div ref={containerRef} style={{ position: "relative" }}>
      <button
        type="button"
        aria-label={`Notifications (${unread} unread)`}
        onClick={() => setOpen((v) => !v)}
        style={{
          position: "relative",
          background: "none",
          border: "none",
          cursor: "pointer",
          fontSize: 18,
          color: "#374151",
          padding: 4,
        }}
      >
        <span aria-hidden>🔔</span>
        {unread > 0 ? (
          <span
            data-testid="unread-count"
            style={{
              position: "absolute",
              top: -2,
              right: -6,
              background: "#dc2626",
              color: "white",
              fontSize: 10,
              minWidth: 16,
              height: 16,
              borderRadius: 8,
              padding: "0 4px",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              lineHeight: 1,
            }}
          >
            {unread}
          </span>
        ) : null}
      </button>
      {open ? (
        <div
          role="dialog"
          aria-label="Notifications"
          style={{
            position: "absolute",
            top: "100%",
            right: 0,
            marginTop: 8,
            background: "white",
            border: "1px solid #e5e7eb",
            borderRadius: 6,
            boxShadow: "0 20px 40px rgba(0,0,0,0.2)",
            width: 360,
            maxHeight: 400,
            overflow: "auto",
            zIndex: 60,
          }}
        >
          {error ? (
            <div role="alert" style={{ padding: 12, color: "#991b1b" }}>
              {error}
            </div>
          ) : items.length === 0 ? (
            <div style={{ padding: 12, color: "#6b7280", fontSize: 14 }}>
              No notifications yet.
            </div>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {items.map((row) => (
                <li
                  key={row.id}
                  onClick={() => void onRowClick(row)}
                  style={{
                    padding: 12,
                    borderBottom: "1px solid #f3f4f6",
                    cursor: row.read_at ? "default" : "pointer",
                    background: row.read_at ? "white" : "#f9fafb",
                  }}
                >
                  <div style={{ fontWeight: row.read_at ? 400 : 600, fontSize: 14 }}>
                    {row.subject}
                  </div>
                  <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>
                    {row.category} · {new Date(row.created_at).toLocaleString()}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
