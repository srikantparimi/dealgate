import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Download, Plus, Upload, Save } from "lucide-react";
import {
  createAgreement,
  getClient,
  getDownloadUrl,
  getMe,
  listAgreements,
  listClients,
  patchAgreement,
  type AgreementRow,
  type AgreementState,
} from "../../api/client";
import { PageHeader } from "../../ui-v2/PageHeader";
import { ErrorState } from "../../ui-v2/ErrorState";
import { EmptyState } from "../../ui-v2/EmptyState";
import { StatusBadge } from "../../ui-v2/StatusBadge";
import { Button } from "../../ui-v2/primitives/button";
import { Input } from "../../ui-v2/primitives/input";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "../../ui-v2/primitives/sheet";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "../../ui-v2/primitives/dialog";
import { UploadAgreementDialog } from "./agreements/UploadAgreementDialog";

const label = (state: string) =>
  state === "sent"
    ? "Sent for signature"
    : state.charAt(0).toUpperCase() + state.slice(1).replace(/_/g, " ");
const stateOf = (row: AgreementRow) => row.display_state ?? row.state;

export function AgreementsRegisterPage() {
  const [params] = useSearchParams();
  const [rows, setRows] = useState<AgreementRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [canEdit, setCanEdit] = useState(false);
  const [view, setView] = useState("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<AgreementRow | null>(null);
  const [upload, setUpload] = useState<AgreementRow | null>(null);
  const [adding, setAdding] = useState(false);
  const [entities, setEntities] = useState<{ id: string; name: string }[]>([]);
  const [entity, setEntity] = useState("");
  const [kind, setKind] = useState<"NDA" | "MSA">("NDA");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const entityFilter = params.get("entity");
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      listAgreements(entityFilter ? { legal_entity_id: entityFilter } : {}),
      getMe(),
    ])
      .then(([response, me]) => {
        if (!cancelled) {
          setRows(response.items);
          setCanEdit(
            me.groups.some((g) => ["Legal", "SystemAdmin"].includes(g)),
          );
        }
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [revision, entityFilter]);
  const reload = () => {
    setSelected(null);
    setUpload(null);
    setAdding(false);
    setRevision((n) => n + 1);
  };
  async function add() {
    setBusy(true);
    setError(null);
    try {
      const clients = [];
      let page = 1;
      while (true) {
        const response = await listClients({ page, size: 200 });
        clients.push(...response.items);
        if (clients.length >= response.total || !response.items.length) break;
        page++;
      }
      const details = await Promise.all(clients.map((c) => getClient(c.id)));
      const all = details.flatMap((c) =>
        c.legal_entities.map((e) => ({
          id: e.id,
          name: `${c.name} / ${e.name}`,
        })),
      );
      setEntities(all);
      setEntity(entityFilter ?? all[0]?.id ?? "");
      setAdding(true);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await patchAgreement(selected.id, {
        owner_email: selected.owner_email || null,
        next_action: selected.next_action || null,
        due_date: selected.due_date || null,
        ...(["missing", "requested", "sent"].includes(selected.state)
          ? { state: selected.state }
          : {}),
      });
      reload();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function download(row: AgreementRow) {
    setBusy(true);
    setError(null);
    try {
      const response = await getDownloadUrl(row.id);
      window.open(response.url, "_blank", "noopener,noreferrer");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  const filtered = rows.filter(
    (r) =>
      (view === "all" ||
        r.kind === view ||
        (view === "action" &&
          !["executed", "terminated", "superseded"].includes(stateOf(r)))) &&
      `${r.client_name} ${r.legal_entity_name} ${r.owner_email} ${r.next_action}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  return (
    <div>
      <PageHeader
        title="NDA & MSA"
        actions={
          canEdit ? (
            <Button onClick={() => void add()} disabled={busy}>
              <Plus className="mr-2 h-4 w-4" />
              Track agreement
            </Button>
          ) : undefined
        }
      />
      <div className="mb-4 flex flex-wrap gap-3">
        <select
          aria-label="Agreement view"
          className="rounded-control border border-divider bg-surface p-2 text-body"
          value={view}
          onChange={(e) => setView(e.target.value)}
        >
          {[
            ["all", "All agreements"],
            ["NDA", "NDA"],
            ["MSA", "MSA"],
            ["action", "Needs action"],
          ].map(([v, name]) => (
            <option key={v} value={v}>
              {name}
            </option>
          ))}
        </select>
        <Input
          className="max-w-sm"
          aria-label="Search agreements"
          placeholder="Search client, entity or owner"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      {error && (
        <ErrorState
          title="Agreement action failed"
          description={error}
          onRetry={() => setRevision((n) => n + 1)}
        />
      )}
      {loading ? (
        <p role="status">Loading agreements...</p>
      ) : !filtered.length ? (
        <EmptyState title="No agreements match this view" />
      ) : (
        <div className="overflow-x-auto">
          <table
            aria-label="Agreement register"
            className="w-full min-w-[760px] text-body"
          >
            <thead>
              <tr className="border-b border-divider text-left text-text-secondary">
                {[
                  "Agreement",
                  "Client / legal entity",
                  "Status",
                  "Effective / expiry",
                  "Owner / next action",
                  "",
                ].map((h, i) => (
                  <th key={i} className="px-3 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.id} className="border-b border-divider">
                  <td className="p-3">
                    <button
                      className="font-medium text-primary underline"
                      onClick={() => setSelected({ ...r })}
                    >
                      {r.kind}
                    </button>
                  </td>
                  <td className="p-3">
                    {r.client_name ?? "Client unavailable"}
                    <div className="text-secondary text-text-secondary">
                      {r.legal_entity_name ?? "Entity unavailable"}
                    </div>
                  </td>
                  <td className="p-3">
                    <StatusBadge
                      label={label(stateOf(r))}
                      tone={
                        stateOf(r) === "executed"
                          ? "ok"
                          : stateOf(r) === "expired"
                            ? "danger"
                            : "warn"
                      }
                    />
                  </td>
                  <td className="whitespace-nowrap p-3 tnum">
                    {r.effective_from ?? "Not recorded"}
                    <div>{r.expiry ?? "Not recorded"}</div>
                  </td>
                  <td className="p-3">
                    {r.owner_email ?? "Unassigned"}
                    <div className="text-secondary text-text-secondary">
                      {r.next_action ?? "No next action"}
                      {r.due_date ? ` · ${r.due_date}` : ""}
                    </div>
                  </td>
                  <td className="p-3">
                    <div className="flex gap-2">
                      {canEdit &&
                        !["terminated", "superseded"].includes(r.state) && (
                          <Button
                            variant="secondary"
                            title={`Upload signed ${r.kind}`}
                            aria-label={`Upload signed ${r.kind}`}
                            onClick={() => setUpload(r)}
                          >
                            <Upload className="h-4 w-4" />
                          </Button>
                        )}
                      {r.evidence_s3_key && (
                        <Button
                          variant="secondary"
                          title={`Download ${r.kind}`}
                          aria-label={`Download ${r.kind}`}
                          disabled={busy}
                          onClick={() => void download(r)}
                        >
                          <Download className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Sheet
        open={!!selected}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
      >
        <SheetContent className="overflow-y-auto">
          <SheetHeader>
            <SheetTitle>{selected?.kind} tracking</SheetTitle>
            <SheetDescription>
              {selected?.client_name} · {selected?.legal_entity_name}
            </SheetDescription>
          </SheetHeader>
          {selected && (
            <div className="mt-5 grid gap-4 text-body">
              {error && <p role="alert">{error}</p>}
              <label>
                Status
                <select
                  className="mt-1 w-full border border-divider bg-surface p-2"
                  value={selected.state}
                  disabled={
                    !canEdit ||
                    [
                      "executed",
                      "expired",
                      "terminated",
                      "superseded",
                    ].includes(selected.state)
                  }
                  onChange={(e) =>
                    setSelected({
                      ...selected,
                      state: e.target.value as AgreementState,
                    })
                  }
                >
                  {!["missing", "requested", "sent"].includes(
                    selected.state,
                  ) && (
                    <option value={selected.state}>
                      {label(stateOf(selected))}
                    </option>
                  )}
                  {[
                    ...(rows.find((r) => r.id === selected.id)?.state ===
                    "missing"
                      ? ["missing"]
                      : []),
                    "requested",
                    "sent",
                  ].map((s) => (
                    <option key={s} value={s}>
                      {label(s)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Owner email
                <Input
                  type="email"
                  value={selected.owner_email ?? ""}
                  disabled={!canEdit}
                  onChange={(e) =>
                    setSelected({ ...selected, owner_email: e.target.value })
                  }
                />
              </label>
              <label>
                Next action
                <Input
                  value={selected.next_action ?? ""}
                  disabled={!canEdit}
                  onChange={(e) =>
                    setSelected({ ...selected, next_action: e.target.value })
                  }
                />
              </label>
              <label>
                Due date
                <Input
                  type="date"
                  value={selected.due_date ?? ""}
                  disabled={!canEdit}
                  onChange={(e) =>
                    setSelected({ ...selected, due_date: e.target.value })
                  }
                />
              </label>
              {canEdit && (
                <Button disabled={busy} onClick={() => void save()}>
                  <Save className="mr-2 h-4 w-4" />
                  Save tracking
                </Button>
              )}
            </div>
          )}
        </SheetContent>
      </Sheet>
      {upload && (
        <UploadAgreementDialog
          agreement={upload}
          onClose={() => setUpload(null)}
          onSaved={reload}
        />
      )}
      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Track agreement</DialogTitle>
            <DialogDescription>Client legal entity</DialogDescription>
          </DialogHeader>
          {error && <p role="alert">{error}</p>}
          <select
            aria-label="Legal entity"
            value={entity}
            onChange={(e) => setEntity(e.target.value)}
            className="w-full border border-divider bg-surface p-2"
          >
            {entities.map((e) => (
              <option value={e.id} key={e.id}>
                {e.name}
              </option>
            ))}
          </select>
          <select
            aria-label="Agreement kind"
            value={kind}
            onChange={(e) => setKind(e.target.value as "NDA" | "MSA")}
            className="border border-divider bg-surface p-2"
          >
            <option>NDA</option>
            <option>MSA</option>
          </select>
          <Button
            disabled={busy || !entity}
            onClick={async () => {
              setBusy(true);
              try {
                await createAgreement({
                  legal_entity_id: entity,
                  type: kind,
                  state: "missing",
                  next_action: `Obtain signed ${kind}`,
                });
                reload();
              } catch (e) {
                setError(String(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            Create tracking record
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
