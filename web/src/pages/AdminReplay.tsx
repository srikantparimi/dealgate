import { useCallback, useEffect, useState } from "react";
import type {
  AdminReplayHubspotRow,
  AdminReplayIntegrationEventRow,
  AdminReplayNotificationRow,
  UUID,
} from "../api/client";
import {
  ApiError,
  listAdminReplayHubspotWriteback,
  listAdminReplayIntegrationEvents,
  listAdminReplayNotifications,
  replayAdminHubspotWriteback,
  replayAdminIntegrationEvent,
  replayAdminNotification,
} from "../api/client";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { PageHeader } from "../ui/PageHeader";
import { StatusChip } from "../ui/StatusChip";
import { Table, type Column } from "../ui/Table";

/**
 * Admin DLQ + replay screen (S6). Three sections — HubSpot writeback,
 * notifications, integration events — each with a sortable table and a
 * per-row Replay button. Sorting is client-side because the tables are
 * bounded (page size = 25 by default, ops-only surface) and the server
 * pre-sorts by attempts DESC / oldest first so the default view already
 * shows the worst offenders first.
 */
type SortKey = "attempts" | "updated_at";
type SortDir = "asc" | "desc";

interface SortState {
  key: SortKey;
  dir: SortDir;
}

interface HasAttempts {
  attempts?: number;
}

interface HasTimestamps {
  next_attempt_at?: string | null;
  sent_at?: string | null;
  created_at?: string;
  received_at?: string;
  processed_at?: string | null;
}

function updatedAtOf(row: HasTimestamps): string {
  // Best-available "last touched" timestamp — prefer the most recent
  // lifecycle stamp, fall back to created_at / received_at so the sort key
  // is defined for every row type.
  return (
    row.sent_at ??
    row.next_attempt_at ??
    row.processed_at ??
    row.received_at ??
    row.created_at ??
    ""
  );
}

function sortRows<T extends HasAttempts & HasTimestamps>(
  rows: T[],
  state: SortState,
): T[] {
  const sorted = [...rows];
  sorted.sort((a, b) => {
    let cmp = 0;
    if (state.key === "attempts") {
      cmp = (a.attempts ?? 0) - (b.attempts ?? 0);
    } else {
      cmp = updatedAtOf(a).localeCompare(updatedAtOf(b));
    }
    return state.dir === "asc" ? cmp : -cmp;
  });
  return sorted;
}

function SortHeader({
  label,
  active,
  dir,
  onClick,
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
}) {
  const arrow = active ? (dir === "asc" ? " ▲" : " ▼") : "";
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        background: "transparent",
        border: "none",
        padding: 0,
        color: "inherit",
        font: "inherit",
        cursor: "pointer",
        fontWeight: 600,
      }}
    >
      {label}
      {arrow}
    </button>
  );
}

function ReplayButton({
  onClick,
  busy,
  label = "Replay",
}: {
  onClick: () => void;
  busy: boolean;
  label?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      aria-label={label}
      style={{
        background: busy ? "#9ca3af" : "#111827",
        color: "white",
        border: "none",
        padding: "6px 12px",
        borderRadius: 6,
        cursor: busy ? "wait" : "pointer",
        fontSize: 13,
      }}
    >
      {busy ? "Replaying…" : label}
    </button>
  );
}

function LastError({ text }: { text: string | null | undefined }) {
  if (!text) return <span style={{ color: "#6b7280" }}>—</span>;
  return (
    <span
      title={text}
      style={{
        display: "inline-block",
        maxWidth: 320,
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
        color: "#991b1b",
        fontSize: 12,
      }}
    >
      {text}
    </span>
  );
}

interface SectionResult<Row> {
  rows: Row[];
  loading: boolean;
  error: unknown;
  reload: () => void;
}

function useSection<Row>(
  loader: () => Promise<{ items: Row[] }>,
): SectionResult<Row> {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    loader()
      .then((res) => setRows(res.items))
      .catch((err) => {
        setError(err);
        setRows([]);
      })
      .finally(() => setLoading(false));
  }, [loader]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { rows, loading, error, reload };
}

function HubspotWritebackSection() {
  const section = useSection<AdminReplayHubspotRow>(() =>
    listAdminReplayHubspotWriteback(),
  );
  const [sort, setSort] = useState<SortState>({ key: "attempts", dir: "desc" });
  const [busy, setBusy] = useState<UUID | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  async function onReplay(id: UUID) {
    setBusy(id);
    setToast(null);
    try {
      await replayAdminHubspotWriteback(id);
      section.reload();
    } catch (err) {
      setToast(err instanceof ApiError ? err.message : "Replay failed");
    } finally {
      setBusy(null);
    }
  }

  const columns: Column<AdminReplayHubspotRow>[] = [
    {
      key: "hubspot_deal_id",
      header: "HubSpot deal",
      render: (r) => <span style={{ fontFamily: "monospace" }}>{r.hubspot_deal_id}</span>,
    },
    { key: "status", header: "Status", render: (r) => <StatusChip>{r.status}</StatusChip> },
    {
      key: "attempts",
      header: (
        <SortHeader
          label="Attempts"
          active={sort.key === "attempts"}
          dir={sort.dir}
          onClick={() => toggleSort(sort, setSort, "attempts")}
        />
      ),
      render: (r) => r.attempts,
    },
    {
      key: "updated_at",
      header: (
        <SortHeader
          label="Updated"
          active={sort.key === "updated_at"}
          dir={sort.dir}
          onClick={() => toggleSort(sort, setSort, "updated_at")}
        />
      ),
      render: (r) => (
        <span style={{ fontSize: 12, color: "#6b7280" }}>{updatedAtOf(r) || "—"}</span>
      ),
    },
    { key: "last_error", header: "Last error", render: (r) => <LastError text={r.last_error} /> },
    {
      key: "actions",
      header: "",
      render: (r) => <ReplayButton onClick={() => onReplay(r.id)} busy={busy === r.id} />,
    },
  ];

  return (
    <section aria-label="HubSpot writeback DLQ" style={{ marginBottom: 32 }}>
      <h2 style={{ fontSize: 18, color: "#111827", marginBottom: 12 }}>
        HubSpot writeback
      </h2>
      {renderBody(section, columns, sort, "No failed HubSpot writebacks.")}
      {toast ? <div style={toastStyle}>{toast}</div> : null}
    </section>
  );
}

function NotificationsSection() {
  const section = useSection<AdminReplayNotificationRow>(() =>
    listAdminReplayNotifications(),
  );
  const [sort, setSort] = useState<SortState>({ key: "attempts", dir: "desc" });
  const [busy, setBusy] = useState<UUID | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  async function onReplay(id: UUID) {
    setBusy(id);
    setToast(null);
    try {
      await replayAdminNotification(id);
      section.reload();
    } catch (err) {
      setToast(err instanceof ApiError ? err.message : "Replay failed");
    } finally {
      setBusy(null);
    }
  }

  const columns: Column<AdminReplayNotificationRow>[] = [
    { key: "subject", header: "Subject", render: (r) => r.subject },
    { key: "channel", header: "Channel", render: (r) => <StatusChip>{r.channel}</StatusChip> },
    { key: "category", header: "Category", render: (r) => r.category },
    { key: "status", header: "Status", render: (r) => <StatusChip>{r.status}</StatusChip> },
    {
      key: "attempts",
      header: (
        <SortHeader
          label="Attempts"
          active={sort.key === "attempts"}
          dir={sort.dir}
          onClick={() => toggleSort(sort, setSort, "attempts")}
        />
      ),
      render: (r) => r.attempts,
    },
    {
      key: "updated_at",
      header: (
        <SortHeader
          label="Updated"
          active={sort.key === "updated_at"}
          dir={sort.dir}
          onClick={() => toggleSort(sort, setSort, "updated_at")}
        />
      ),
      render: (r) => (
        <span style={{ fontSize: 12, color: "#6b7280" }}>{updatedAtOf(r) || "—"}</span>
      ),
    },
    { key: "last_error", header: "Last error", render: (r) => <LastError text={r.last_error} /> },
    {
      key: "actions",
      header: "",
      render: (r) => <ReplayButton onClick={() => onReplay(r.id)} busy={busy === r.id} />,
    },
  ];

  return (
    <section aria-label="Notifications DLQ" style={{ marginBottom: 32 }}>
      <h2 style={{ fontSize: 18, color: "#111827", marginBottom: 12 }}>
        Notifications
      </h2>
      {renderBody(section, columns, sort, "No failed notifications.")}
      {toast ? <div style={toastStyle}>{toast}</div> : null}
    </section>
  );
}

function IntegrationEventsSection() {
  const section = useSection<AdminReplayIntegrationEventRow>(() =>
    listAdminReplayIntegrationEvents(),
  );
  // Integration events don't carry `attempts` — treat received_at as the
  // sort surrogate and hide the attempts column entirely.
  const [sort, setSort] = useState<SortState>({ key: "updated_at", dir: "asc" });
  const [busy, setBusy] = useState<UUID | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  async function onReplay(id: UUID) {
    setBusy(id);
    setToast(null);
    try {
      await replayAdminIntegrationEvent(id);
      section.reload();
    } catch (err) {
      setToast(err instanceof ApiError ? err.message : "Replay failed");
    } finally {
      setBusy(null);
    }
  }

  const columns: Column<AdminReplayIntegrationEventRow>[] = [
    {
      key: "source_event_id",
      header: "Event id",
      render: (r) => (
        <span style={{ fontFamily: "monospace" }}>{r.source_event_id}</span>
      ),
    },
    { key: "source", header: "Source", render: (r) => <StatusChip>{r.source}</StatusChip> },
    {
      key: "received_at",
      header: (
        <SortHeader
          label="Received"
          active={sort.key === "updated_at"}
          dir={sort.dir}
          onClick={() => toggleSort(sort, setSort, "updated_at")}
        />
      ),
      render: (r) => (
        <span style={{ fontSize: 12, color: "#6b7280" }}>{r.received_at}</span>
      ),
    },
    {
      key: "processed_at",
      header: "Processed",
      render: (r) => (
        <span style={{ fontSize: 12, color: r.processed_at ? "#111827" : "#991b1b" }}>
          {r.processed_at ?? "not yet"}
        </span>
      ),
    },
    {
      key: "actions",
      header: "",
      render: (r) => <ReplayButton onClick={() => onReplay(r.id)} busy={busy === r.id} />,
    },
  ];

  return (
    <section aria-label="Integration events DLQ" style={{ marginBottom: 32 }}>
      <h2 style={{ fontSize: 18, color: "#111827", marginBottom: 12 }}>
        Integration events
      </h2>
      {renderBody(section, columns, sort, "No stuck integration events.")}
      {toast ? <div style={toastStyle}>{toast}</div> : null}
    </section>
  );
}

function toggleSort(
  current: SortState,
  setter: (next: SortState) => void,
  key: SortKey,
): void {
  if (current.key === key) {
    setter({ key, dir: current.dir === "asc" ? "desc" : "asc" });
  } else {
    setter({ key, dir: "desc" });
  }
}

function renderBody<Row extends { id: UUID } & HasAttempts & HasTimestamps>(
  section: SectionResult<Row>,
  columns: Column<Row>[],
  sort: SortState,
  emptyTitle: string,
) {
  if (section.error) {
    return <ErrorState error={section.error} retry={section.reload} />;
  }
  if (section.loading && section.rows.length === 0) {
    return <EmptyState title="Loading" hint="Fetching failed rows." />;
  }
  if (section.rows.length === 0) {
    return <EmptyState title={emptyTitle} />;
  }
  const sorted = sortRows(section.rows, sort);
  return <Table columns={columns} rows={sorted} ariaLabel={emptyTitle} />;
}

const toastStyle: React.CSSProperties = {
  marginTop: 8,
  color: "#991b1b",
  fontSize: 13,
};

export function AdminReplayPage() {
  return (
    <div>
      <PageHeader
        title="Replay"
        subtitle="Failed integration events, notifications and HubSpot writeback jobs. Every replay writes an audit row."
      />
      <HubspotWritebackSection />
      <NotificationsSection />
      <IntegrationEventsSection />
    </div>
  );
}
