import { useCallback, useEffect, useRef, useState } from "react";
import type { NotificationSettingRow } from "../api/client";
import {
  ApiError,
  getNotificationSettings,
  patchNotificationSetting,
} from "../api/client";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { PageHeader } from "../ui/PageHeader";

/**
 * Notification settings matrix: rows = categories, columns = channels. Each
 * toggle debounces its PATCH so a rapid on/off/on doesn't spam the API.
 */
export function NotificationSettingsPage() {
  const [categories, setCategories] = useState<string[]>([]);
  const [channels, setChannels] = useState<string[]>([]);
  const [values, setValues] = useState<Map<string, boolean>>(new Map());
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const debouncers = useRef<Map<string, number>>(new Map());

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getNotificationSettings()
      .then((res) => {
        setCategories(res.categories);
        setChannels(res.channels);
        const map = new Map<string, boolean>();
        for (const row of res.items) {
          map.set(key(row.category, row.channel), row.enabled);
        }
        setValues(map);
      })
      .catch((err) => setError(err))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    return () => {
      // Cancel pending debounces when the page unmounts.
      for (const t of debouncers.current.values()) window.clearTimeout(t);
      debouncers.current.clear();
    };
  }, [load]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 2500);
    return () => window.clearTimeout(t);
  }, [toast]);

  function toggle(category: string, channel: string, next: boolean) {
    const k = key(category, channel);
    setValues((prev) => {
      const cp = new Map(prev);
      cp.set(k, next);
      return cp;
    });
    // Debounce the PATCH so rapid clicks only send the last value.
    const existing = debouncers.current.get(k);
    if (existing) window.clearTimeout(existing);
    const t = window.setTimeout(async () => {
      debouncers.current.delete(k);
      try {
        const body: NotificationSettingRow = { category, channel, enabled: next };
        await patchNotificationSetting(body);
      } catch (err) {
        setToast(err instanceof ApiError ? err.message : "Save failed");
        // Roll back the optimistic update on failure.
        setValues((prev) => {
          const cp = new Map(prev);
          cp.set(k, !next);
          return cp;
        });
      }
    }, 350);
    debouncers.current.set(k, t);
  }

  return (
    <div>
      <PageHeader
        title="Notification settings"
        subtitle="Choose which channels receive each kind of notification."
      />
      {error ? (
        <ErrorState error={error} retry={load} />
      ) : loading && categories.length === 0 ? (
        <EmptyState title="Loading" hint="Fetching your preferences." />
      ) : (
        <table
          aria-label="Notification settings"
          style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}
        >
          <thead>
            <tr style={{ background: "#f9fafb", textAlign: "left" }}>
              <th style={cell}>Category</th>
              {channels.map((ch) => (
                <th key={ch} style={cell}>
                  {ch}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {categories.map((cat) => (
              <tr key={cat} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={cell}>{cat}</td>
                {channels.map((ch) => {
                  const k = key(cat, ch);
                  const on = values.get(k) ?? true;
                  return (
                    <td key={ch} style={cell}>
                      <label style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                        <input
                          type="checkbox"
                          aria-label={`${cat} ${ch}`}
                          checked={on}
                          onChange={(e) => toggle(cat, ch, e.target.checked)}
                        />
                        <span style={{ color: on ? "#111827" : "#6b7280" }}>
                          {on ? "on" : "off"}
                        </span>
                      </label>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {toast ? (
        <div
          role="status"
          aria-live="polite"
          style={{
            position: "fixed",
            bottom: 24,
            right: 24,
            background: "#111827",
            color: "white",
            padding: "8px 12px",
            borderRadius: 6,
            fontSize: 14,
          }}
        >
          {toast}
        </div>
      ) : null}
    </div>
  );
}

function key(category: string, channel: string): string {
  return `${category}::${channel}`;
}

const cell: React.CSSProperties = {
  padding: "8px 12px",
  borderBottom: "1px solid #e5e7eb",
};
