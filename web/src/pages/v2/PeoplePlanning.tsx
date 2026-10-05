import { useEffect, useId, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, RefreshCw, Upload } from "lucide-react";
import { ApiError, getMe } from "../../api/client";
import {
  getPeopleAvailability,
  getPeopleImports,
  importPeopleSupply,
  type PeopleAvailability,
  type PeopleImports,
  type SupplySource,
} from "../../api/people";
import { Button } from "../../ui-v2/primitives/button";
import { Input } from "../../ui-v2/primitives/input";
import { ResourceDemand } from "./forecast/ResourceDemand";

export function PeopleDemandPage() {
  return <main className="mx-auto min-w-0 max-w-[1600px] space-y-5 p-4 sm:p-6">
    <h1 className="text-2xl font-semibold">People planning</h1>
    <nav aria-label="People views" className="flex gap-5 border-b border-divider pb-3">
      <a href="/people" className="underline underline-offset-4">Supply</a>
      <a href="/people/demand" aria-current="page" className="font-semibold">Demand</a>
      <a href="/people/sourcing" className="underline underline-offset-4">Sourcing</a>
    </nav>
    <ResourceDemand />
  </main>;
}

function failure(error: unknown): string {
  if (error instanceof ApiError) {
    const details = error.detail as { detail?: unknown } | null;
    if (Array.isArray(details?.detail))
      return details.detail
        .map(
          (item: { loc?: unknown[]; msg?: string }) =>
            `${item.loc?.join(".") ?? "Import"}: ${item.msg ?? "Invalid value"}`,
        )
        .join("\n");
  }
  return error instanceof Error
    ? error.message
    : "People supply request failed";
}
function objectDraft(text: string): Record<string, unknown> {
  const value: unknown = JSON.parse(text);
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Roster JSON must be an object");
  return value as Record<string, unknown>;
}

export function PeoplePlanningPage() {
  const rosterId = useId();
  const [allowed, setAllowed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [supply, setSupply] = useState<PeopleAvailability | null>(null);
  const [history, setHistory] = useState<PeopleImports | null>(null);
  const [basisSources, setBasisSources] = useState<SupplySource[]>([]);
  const [source, setSource] = useState("");
  const [draft, setDraft] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const requestKey = useRef(crypto.randomUUID());
  const generation = useRef(0);
  useEffect(() => {
    let current = true;
    getMe()
      .then(async (me) => {
        if (!current) return;
        if (!me.groups.some((group) => ["HR", "SystemAdmin"].includes(group))) {
          setError("Named workforce supply requires HR or SystemAdmin");
          setLoading(false);
          return;
        }
        setAllowed(true);
        await reload();
      })
      .catch((e) => {
        if (current) {
          setError(failure(e));
          setLoading(false);
        }
      });
    return () => {
      current = false;
      generation.current += 1;
    };
  }, []);
  async function reload(page = 1, refreshBasis = true) {
    const token = ++generation.current;
    setLoading(true);
    try {
      const [next, imports] = await Promise.all([
        getPeopleAvailability(),
        getPeopleImports(page),
      ]);
      if (token !== generation.current) return;
      setSupply(next);
      setHistory(imports);
      if (refreshBasis) {
        setBasisSources(next.sources);
        setSource(
          (previous) => previous || next.sources[0]?.source_system || "",
        );
        requestKey.current = crypto.randomUUID();
      }
    } catch (e) {
      if (token === generation.current) setError(failure(e));
    } finally {
      if (token === generation.current) setLoading(false);
    }
  }
  function changeDraft(text: string) {
    setDraft(text);
    setNotice("");
    requestKey.current = crypto.randomUUID();
    try {
      const data = objectDraft(text);
      if (typeof data.source_system === "string") setSource(data.source_system);
    } catch {
      /* Display JSON validation on import, preserving corrections in progress. */
    }
  }
  async function uploadFile(file: File | undefined) {
    if (!file) return;
    try {
      const text = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () =>
          reject(new Error("Roster file could not be read"));
        reader.readAsText(file);
      });
      changeDraft(text);
    } catch (e) {
      setError(failure(e));
    }
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const values = objectDraft(draft);
      if (
        typeof values.source_system !== "string" ||
        !values.source_system.trim()
      )
        throw new Error("Roster source_system is required");
      const previous = basisSources.find(
        (item) => item.source_system === values.source_system,
      );
      const result = await importPeopleSupply({
        ...values,
        request_key: requestKey.current,
        expected_previous_batch_id: previous?.id ?? null,
        reason,
      });
      setNotice(
        `Imported revision ${result.revision}: ${result.person_count} people.`,
      );
      await reload();
    } catch (e) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }
  const currentSource = basisSources.find(
    (item) => item.source_system === source,
  );
  return (
    <main className="mx-auto min-w-0 max-w-[1600px] space-y-5 p-4 sm:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">People planning</h1>
        {allowed && (
          <Button
            variant="secondary"
            disabled={loading || busy}
            onClick={() => void reload()}
          >
            <RefreshCw className="h-4 w-4" />
            Reload source versions
          </Button>
        )}
      </header>
      {allowed && <nav aria-label="People views" className="flex gap-5 border-b border-divider pb-3">
        <a href="/people" aria-current="page" className="font-semibold">Supply</a>
        <a href="/people/demand" className="underline underline-offset-4">Demand</a>
        <a href="/people/sourcing" className="underline underline-offset-4">Sourcing</a>
      </nav>}
      {loading && <p role="status">Loading workforce supply...</p>}
      {error && (
        <p
          role="alert"
          className="whitespace-pre-wrap break-words border-l-4 border-danger p-3 text-danger"
        >
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {allowed && (
        <form
          onSubmit={submit}
          aria-label="Managed roster import"
          className="space-y-3 border-y border-divider py-4"
        >
          <h2 className="font-semibold">Managed roster import</h2>
          <fieldset disabled={busy || loading || !supply} className="space-y-3">
            <label className="block space-y-1">
              Roster file
              <input
                type="file"
                accept="application/json,.json"
                className="block w-full"
                onChange={(event) => void uploadFile(event.target.files?.[0])}
              />
            </label>
            <div className="text-secondary">
              <p>Source: {source || "Unconfirmed"}</p>
              <p>Current revision: {currentSource?.revision ?? "New source"}</p>
              <p>
                Source as of:{" "}
                {currentSource?.source_as_of ?? "Not yet imported"}
              </p>
            </div>
            <div className="space-y-1">
              <label htmlFor={rosterId}>Roster JSON</label>
              <textarea
                id={rosterId}
                className="block min-h-40 w-full rounded-md border border-divider bg-surface p-3 font-mono text-sm"
                value={draft}
                onChange={(event) => changeDraft(event.target.value)}
              />
            </div>
            <label className="block space-y-1">
              Import reason
              <Input
                value={reason}
                onChange={(event) => {
                  setReason(event.target.value);
                  requestKey.current = crypto.randomUUID();
                }}
              />
            </label>
            <Button type="submit" disabled={!draft.trim() || !reason.trim()}>
              <Upload className="h-4 w-4" />
              {busy ? "Importing..." : "Import roster"}
            </Button>
          </fieldset>
        </form>
      )}
      {allowed && supply && (
        <section aria-label="Workforce supply" className="space-y-3">
          <h2 className="font-semibold">Workforce supply</h2>
          <p className="text-secondary">
            Managed import / Gross capacity with dated commitments / Not a
            reservation
          </p>
          {supply.sources.map((item) => (
            <p key={item.id} className="break-words text-secondary">
              {item.source_system} / Revision {item.revision} / Source as of{" "}
              {item.source_as_of}
            </p>
          ))}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm [&_th]:whitespace-nowrap [&_th]:p-3 [&_td]:p-3 [&_td]:align-top [&_tbody_tr]:border-t [&_tbody_tr]:border-divider">
              <thead>
                <tr>
                  {[
                    "Person",
                    "Role / level",
                    "Skills",
                    "Location / timezone",
                    "Capacity and commitments (inclusive dates)",
                    "Source evidence",
                  ].map((label) => (
                    <th key={label}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {supply.people.map((person) => (
                  <tr key={person.version_id}>
                    <td>
                      {person.display_name}
                      <p className="text-secondary">{person.source_system}</p>
                    </td>
                    <td>
                      {person.role} / {person.level}
                    </td>
                    <td>{person.skills.join(", ") || "Unconfirmed"}</td>
                    <td>
                      {person.location}
                      <p>{person.timezone}</p>
                    </td>
                    <td>
                      {person.intervals.map((interval, index) => (
                        <p key={index}>
                          {interval.kind}: {interval.allocation} /{" "}
                          {interval.start_date} to {interval.end_date}
                          {interval.assignment_key
                            ? ` / ${interval.assignment_key}`
                            : ""}
                        </p>
                      ))}
                    </td>
                    <td>
                      {person.evidence.map((evidence, index) => (
                        <p key={index}>{evidence}</p>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!supply.people.length && <p>No workforce supply imported.</p>}
        </section>
      )}
      {allowed && history && (
        <section
          aria-label="Import history"
          className="space-y-3 border-t border-divider pt-4"
        >
          <h2 className="font-semibold">Import history / {history.total}</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm [&_th]:p-3 [&_td]:p-3 [&_tbody_tr]:border-t [&_tbody_tr]:border-divider">
              <thead>
                <tr>
                  {[
                    "Source",
                    "Revision",
                    "People",
                    "Source as of",
                    "Imported",
                    "Imported by",
                    "Reason",
                  ].map((label) => (
                    <th key={label}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {history.items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.source_system}</td>
                    <td>{item.revision}</td>
                    <td>{item.person_count}</td>
                    <td>{item.source_as_of}</td>
                    <td>{item.imported_at}</td>
                    <td>{item.imported_by_name ?? "Uploader unavailable"}</td>
                    <td>{item.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Previous import page"
              disabled={loading || busy || history.page <= 1}
              onClick={() => void reload(history.page - 1, false)}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span>Page {history.page}</span>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Next import page"
              disabled={
                loading || busy || history.page * history.size >= history.total
              }
              onClick={() => void reload(history.page + 1, false)}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </section>
      )}
    </main>
  );
}
