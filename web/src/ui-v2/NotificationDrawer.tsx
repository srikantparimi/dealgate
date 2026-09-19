import { Bell } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  listInboxNotifications,
  markNotificationRead,
  type NotificationRow,
} from "../api/client";
import { cn } from "../lib/cn";
import { Badge } from "./primitives/badge";
import { Button } from "./primitives/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "./primitives/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./primitives/tabs";

/**
 * Right-drawer notifications inbox (spec §4).
 *
 * Reuses `listInboxNotifications` + `markNotificationRead` from the
 * existing S2 API — no backend changes. Reading a notification does not
 * complete the underlying task; the row deep-links to the source record so
 * the operator finishes the work there.
 */

type FilterKey = "all" | "approvals" | "renewals" | "integrations" | "follow-ups";

const FILTERS: Array<{ key: FilterKey; label: string; match?: (row: NotificationRow) => boolean }> = [
  { key: "all", label: "All" },
  {
    key: "approvals",
    label: "Approvals",
    match: (row) => row.category.toLowerCase().includes("approval"),
  },
  {
    key: "renewals",
    label: "Renewals",
    match: (row) => row.category.toLowerCase().includes("renewal"),
  },
  {
    key: "integrations",
    label: "Integration issues",
    match: (row) =>
      row.category.toLowerCase().includes("integration") ||
      row.category.toLowerCase().includes("failure"),
  },
  {
    key: "follow-ups",
    label: "Follow-ups",
    match: (row) => row.category.toLowerCase().includes("follow"),
  },
];

export interface NotificationDrawerProps {
  className?: string;
}

export function NotificationDrawer({ className }: NotificationDrawerProps) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationRow[]>([]);
  const [unread, setUnread] = useState(0);
  const [tab, setTab] = useState<"unread" | "all">("unread");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await listInboxNotifications(50);
      setItems(res.items);
      setUnread(res.unread_count);
      setError(null);
    } catch (err) {
      // 401 during auth settle is normal — keep the bell silent.
      if (err instanceof ApiError && err.status === 401) return;
      setError(err instanceof ApiError ? err.message : "Failed to load");
    }
  }, []);

  useEffect(() => {
    void load();
    const handle = window.setInterval(() => void load(), 60_000);
    return () => window.clearInterval(handle);
  }, [load]);

  const filtered = useMemo(() => {
    const matcher = FILTERS.find((f) => f.key === filter)?.match;
    const base = tab === "unread" ? items.filter((i) => !i.read_at) : items;
    return matcher ? base.filter(matcher) : base;
  }, [items, tab, filter]);

  async function handleRowClick(row: NotificationRow) {
    if (row.read_at) return;
    try {
      await markNotificationRead(row.id);
      setItems((prev) =>
        prev.map((r) =>
          r.id === row.id ? { ...r, read_at: new Date().toISOString() } : r,
        ),
      );
      setUnread((n) => Math.max(0, n - 1));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Mark read failed");
    }
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Notifications (${unread} unread)`}
          className={cn("relative text-text-secondary", className)}
        >
          <Bell className="h-5 w-5" aria-hidden />
          {unread > 0 ? (
            <span
              data-testid="unread-count"
              className="absolute -right-0.5 -top-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-secondary text-white"
            >
              {unread}
            </span>
          ) : null}
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="flex flex-col gap-4">
        <SheetHeader>
          <SheetTitle>Notifications</SheetTitle>
          <SheetDescription>
            {unread} unread. Reading an item does not complete the underlying task.
          </SheetDescription>
        </SheetHeader>

        <Tabs value={tab} onValueChange={(v) => setTab(v as "unread" | "all")}>
          <TabsList>
            <TabsTrigger value="unread">Unread</TabsTrigger>
            <TabsTrigger value="all">All</TabsTrigger>
          </TabsList>
          <TabsContent value={tab}>
            <div className="mb-3 flex flex-wrap gap-1">
              {FILTERS.map((f) => (
                <Button
                  key={f.key}
                  variant={filter === f.key ? "primary" : "secondary"}
                  size="sm"
                  onClick={() => setFilter(f.key)}
                >
                  {f.label}
                </Button>
              ))}
            </div>
            {error ? (
              <div
                role="alert"
                className="rounded-panel border border-danger/40 bg-danger-surface p-3 text-body text-danger"
              >
                {error}
              </div>
            ) : null}
            {!error && filtered.length === 0 ? (
              <p className="p-3 text-body text-text-secondary">
                No notifications match this view.
              </p>
            ) : null}
            <ul className="flex flex-col gap-2">
              {filtered.map((row) => (
                <li key={row.id}>
                  <button
                    type="button"
                    onClick={() => void handleRowClick(row)}
                    className={cn(
                      "flex w-full flex-col items-start gap-1 rounded-panel border border-divider p-3 text-left",
                      "transition-motion focus-visible:outline-focus hover:bg-primary-subtle",
                      !row.read_at && "bg-primary-subtle/40",
                    )}
                  >
                    <div className="flex w-full items-center justify-between gap-2">
                      <span
                        className={cn(
                          "text-body text-text",
                          !row.read_at && "font-semibold",
                        )}
                      >
                        {row.subject}
                      </span>
                      <Badge tone="neutral">{row.category}</Badge>
                    </div>
                    <span className="text-secondary text-text-secondary">
                      {new Date(row.created_at).toLocaleString()}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </TabsContent>
        </Tabs>
      </SheetContent>
    </Sheet>
  );
}
