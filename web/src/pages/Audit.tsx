import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  AuditFilters,
  AuditListResponse,
  AuditListRow,
  VerifyAuditResponse,
} from "../api/client";
import { listAudit, verifyAudit } from "../api/client";
import { DateRangePicker } from "../ui/DateRangePicker";
import { DiffCell } from "../ui/DiffCell";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { FilterBar, Pager } from "../ui/FilterBar";
import { PageHeader } from "../ui/PageHeader";
import { StatusChip } from "../ui/StatusChip";
import { Table, type Column } from "../ui/Table";

type EntityOption = "" | "opportunity" | "task" | "agreement" | "user";

const ENTITY_OPTIONS: { value: EntityOption; label: string }[] = [
  { value: "", label: "All entities" },
  { value: "opportunity", label: "opportunity" },
  { value: "task", label: "task" },
  { value: "agreement", label: "agreement" },
  { value: "user", label: "user" },
];

const PAGE_SIZE = 25;

function dateToStart(d: string): string | undefined {
  return d ? `${d}T00:00:00Z` : undefined;
}
function dateToEnd(d: string): string | undefined {
  return d ? `${d}T23:59:59Z` : undefined;
}

function formatTs(ts: string): string {
  // Show the ISO timestamp trimmed to seconds so the column stays scannable.
  try {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return ts;
    return d.toISOString().replace("T", " ").slice(0, 19) + " UTC";
  } catch {
    return ts;
  }
}

export function AuditPage() {
  const [entity, setEntity] = useState<EntityOption>("");
  const [entityId, setEntityId] = useState<string>("");
  const [actorEmail, setActorEmail] = useState<string>("");
  const [range, setRange] = useState<{ since: string; until: string }>({
    since: "",
    until: "",
  });
  const [page, setPage] = useState<number>(1);

  const [data, setData] = useState<AuditListResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<VerifyAuditResponse | null>(
    null,
  );

  const filters = useMemo<AuditFilters>(() => {
    const f: AuditFilters = { page, size: PAGE_SIZE };
    if (entity) f.entity = entity;
    if (entityId.trim()) f.entity_id = entityId.trim();
    if (range.since) f.since = dateToStart(range.since);
    if (range.until) f.until = dateToEnd(range.until);
    // actor_email is a client-side hint until /admin/users lands; the API
    // filters on `actor_id` only, so we do not send `actor_email` here.
    return f;
  }, [entity, entityId, range.since, range.until, page]);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    listAudit(filters)
      .then((res) => {
        // If a client-side actor email filter is set, narrow the rendered
        // rows client-side — the API cannot filter on email today.
        const trimmed = actorEmail.trim().toLowerCase();
        const items = trimmed
          ? res.items.filter((r) => (r.actor_email ?? "").toLowerCase().includes(trimmed))
          : res.items;
        setData({ ...res, items });
      })
      .catch((err) => {
        setError(err);
        setData(null);
      })
      .finally(() => setLoading(false));
  }, [filters, actorEmail]);

  useEffect(() => {
    load();
  }, [load]);

  async function runVerify() {
    setVerifying(true);
    setVerifyResult(null);
    try {
      const result = await verifyAudit({
        entity: filters.entity,
        entity_id: filters.entity_id,
      });
      setVerifyResult(result);
    } catch (err) {
      setVerifyResult({
        ok: false,
        first_broken_row: null,
        checked: 0,
        message: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setVerifying(false);
    }
  }

  const total = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const columns: Column<AuditListRow>[] = [
    { key: "when", header: "When", render: (r) => formatTs(r.ts) },
    {
      key: "actor",
      header: "Actor",
      render: (r) => r.actor_email ?? r.actor_id ?? "system",
    },
    { key: "action", header: "Action", render: (r) => r.action },
    { key: "entity", header: "Entity", render: (r) => r.entity },
    { key: "entity_id", header: "Entity ID", render: (r) => r.entity_id },
    {
      key: "diff",
      header: "Diff",
      render: (r) => <DiffCell before={r.before} after={r.after} />,
    },
  ];

  return (
    <div>
      <PageHeader
        title="Audit log"
        subtitle="Every state change: actor, timestamp, before/after, chain hash."
        right={
          <button
            type="button"
            onClick={runVerify}
            disabled={verifying}
            style={{
              background: "#111827",
              color: "white",
              border: "none",
              padding: "8px 16px",
              borderRadius: 6,
              cursor: verifying ? "wait" : "pointer",
            }}
          >
            {verifying ? "Verifying…" : "Verify chain"}
          </button>
        }
      />

      <FilterBar>
        <label style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, color: "#6b7280" }}>
          Entity
          <select
            aria-label="Entity filter"
            value={entity}
            onChange={(e) => {
              setEntity(e.target.value as EntityOption);
              setPage(1);
            }}
          >
            {ENTITY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, color: "#6b7280" }}>
          Entity ID
          <input
            type="text"
            aria-label="Entity ID filter"
            value={entityId}
            onChange={(e) => {
              setEntityId(e.target.value);
              setPage(1);
            }}
            placeholder="e.g. O-123"
          />
        </label>
        <label style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, color: "#6b7280" }}>
          Actor email
          <input
            type="text"
            aria-label="Actor email filter"
            value={actorEmail}
            onChange={(e) => setActorEmail(e.target.value)}
            placeholder="user@smartek21.com"
            list="audit-actor-options"
          />
          <datalist id="audit-actor-options" />
        </label>
        <DateRangePicker
          since={range.since}
          until={range.until}
          onChange={(next) => {
            setRange(next);
            setPage(1);
          }}
        />
      </FilterBar>

      {verifyResult ? (
        <div
          role="status"
          aria-label="Verification result"
          style={{ marginBottom: 16, display: "flex", gap: 8, alignItems: "center" }}
        >
          <StatusChip tone={verifyResult.ok ? "ok" : "block"}>
            {verifyResult.ok
              ? "Chain valid"
              : verifyResult.first_broken_row
                ? `Chain broken at ${verifyResult.first_broken_row}`
                : "Chain broken"}
          </StatusChip>
          <span style={{ color: "#374151", fontSize: 14 }}>{verifyResult.message}</span>
        </div>
      ) : null}

      {error ? (
        <ErrorState error={error} retry={load} />
      ) : loading && !data ? (
        <EmptyState title="Loading" hint="Fetching audit events." />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title="No audit events"
          hint="Nothing matches the current filters."
        />
      ) : (
        <>
          <Table ariaLabel="Audit events" columns={columns} rows={data.items} />
          <Pager
            page={data.page}
            pageCount={pageCount}
            onChange={(next) => {
              if (next >= 1 && next <= pageCount) setPage(next);
            }}
          />
        </>
      )}
    </div>
  );
}
