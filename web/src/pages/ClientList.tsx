import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { ClientListResponse, ClientListRow } from "../api/client";
import { listClients } from "../api/client";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { PageHeader } from "../ui/PageHeader";
import { Table, type Column } from "../ui/Table";

type OwnerFilter = "me" | "all";

export function ClientListPage() {
  const navigate = useNavigate();
  const [owner, setOwner] = useState<OwnerFilter>("all");
  const [search, setSearch] = useState("");
  const [data, setData] = useState<ClientListResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    const query: Parameters<typeof listClients>[0] = {};
    if (owner === "me") query.owner = "me";
    if (search.trim()) query.search = search.trim();
    listClients(query)
      .then((res) => setData(res))
      .catch((err) => {
        setError(err);
        setData(null);
      })
      .finally(() => setLoading(false));
  }, [owner, search]);

  useEffect(() => {
    load();
  }, [load]);

  const columns: Column<ClientListRow>[] = [
    { key: "name", header: "Client", render: (r) => r.name },
    {
      key: "hubspot",
      header: "HubSpot",
      render: (r) => r.hubspot_company_id ?? "—",
    },
    {
      key: "opps",
      header: "Opportunities",
      render: (r) => String(r.opportunity_count),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Clients"
        subtitle="Entities and opportunities. NDA/MSA lives on the Agreements page."
        right={
          <div style={{ display: "flex", gap: 8 }}>
            <input
              aria-label="Client search"
              placeholder="Search by name"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ padding: 6 }}
            />
            <select
              aria-label="Owner filter"
              value={owner}
              onChange={(e) => setOwner(e.target.value as OwnerFilter)}
            >
              <option value="all">All clients</option>
              <option value="me">My clients</option>
            </select>
          </div>
        }
      />
      {error ? (
        <ErrorState error={error} retry={load} />
      ) : loading && !data ? (
        <EmptyState title="Loading" hint="Fetching clients." />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title="No clients yet"
          hint="HubSpot companies show up as their first deal syncs."
        />
      ) : (
        <Table
          ariaLabel="Clients"
          columns={columns}
          rows={data.items}
          onRowClick={(row) => navigate(`/clients/${row.id}`)}
        />
      )}
    </div>
  );
}
