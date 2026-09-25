import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listProjects, type ProjectRow } from "../../api/client";
import { PageHeader } from "../../ui-v2/PageHeader";
import { ErrorState } from "../../ui-v2/ErrorState";
import { EmptyState } from "../../ui-v2/EmptyState";
import { Input } from "../../ui-v2/primitives/input";
import { fmtCount, fmtPercent } from "./projects/format";

export function ProjectsActualsPage() {
  const [rows, setRows] = useState<ProjectRow[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listProjects()
      .then((r) => {
        if (!cancelled) setRows(r.items);
      })
      .catch((e) => {
        if (!cancelled) setError(e);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [retry]);
  const filtered = rows.filter((r) =>
    `${r.title} ${r.client_name} ${r.owner_name}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  return (
    <div>
      <PageHeader
        title="Projects"
        actions={
          <Input
            aria-label="Search projects"
            placeholder="Search projects"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        }
      />
      {loading ? (
        <p role="status">Loading projects...</p>
      ) : error ? (
        <ErrorState
          title="Could not load projects"
          description={String(error)}
          onRetry={() => setRetry((n) => n + 1)}
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          title="No running projects"
          description="No released SOWs match this view."
        />
      ) : (
        filtered.map((row) => (
          <section
            key={row.id}
            className="border-b border-divider py-6"
            aria-label={row.title}
          >
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <Link
                  className="text-section font-semibold text-primary break-words"
                  to={`/sows/${row.id}`}
                >
                  {row.title}
                </Link>
                <p className="mt-1 text-body text-text-secondary">
                  {row.client_name} · {row.owner_name}
                </p>
                <p className="mt-1 text-secondary text-text-secondary">
                  SOW v{row.sow_version} · GM v{row.gm_version} · Released{" "}
                  {row.released_at.slice(0, 10)}
                  {row.term_end ? ` · Ends ${row.term_end}` : ""}
                </p>
              </div>
              <table className="text-body" aria-label={`${row.title} GM`}>
                <thead>
                  <tr className="text-left text-text-secondary">
                    <th className="pr-4">GM</th>
                    <th className="pr-4">Approved</th>
                    <th>Forecast</th>
                  </tr>
                </thead>
                <tbody>
                  {(["us", "india"] as const).map((region) => (
                    <tr key={region}>
                      <th className="pr-4 text-left font-medium">
                        {region === "us" ? "US" : "India"}
                      </th>
                      <td className="pr-4 tnum">
                        {fmtPercent(row.approved[region]) ?? "Unavailable"}
                      </td>
                      <td className="tnum">
                        {fmtPercent(row.forecast[region]) ?? "Unavailable"}
                      </td>
                    </tr>
                  ))}
                </tbody>
                {row.forecast.as_of && (
                  <tfoot>
                    <tr>
                      <td
                        colSpan={3}
                        className="pt-1 text-secondary text-text-secondary"
                      >
                        Forecast as of {row.forecast.as_of}
                      </td>
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
            <div className="mt-5 overflow-x-auto">
              <table
                className="w-full text-body"
                aria-label={`${row.title} resources`}
              >
                <thead>
                  <tr className="border-b border-divider text-left text-text-secondary">
                    {[
                      "Resource",
                      "Role",
                      "Location",
                      "Allocation",
                      "Hours",
                      "Dates",
                    ].map((h) => (
                      <th key={h} className="py-2 pr-4 font-medium">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {row.resources.map((r) => (
                    <tr key={r.id} className="border-b border-divider">
                      <td className="py-3 pr-4">{r.name ?? "To hire"}</td>
                      <td className="pr-4">{r.role}</td>
                      <td className="pr-4">{r.location}</td>
                      <td className="pr-4 tnum">{fmtPercent(r.allocation)}</td>
                      <td className="pr-4 tnum">
                        {r.hours == null
                          ? "Unavailable"
                          : fmtCount(Number(r.hours))}
                      </td>
                      <td className="whitespace-nowrap">
                        {r.start_date} to {r.end_date}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {row.resources.length === 0 && (
                <p className="py-3 text-text-secondary">
                  No resources recorded in this approved baseline.
                </p>
              )}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
