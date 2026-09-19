/**
 * NDA & MSA register (`/agreements`) — spec §12.
 *
 * Views: All agreements / NDA / MSA / Needs action.
 * Columns: agreement name/type · client / legal entity · linked
 * opportunity · version · lifecycle status · internal approval ·
 * execution state · effective + end dates · owner · next action.
 *
 * Legal execution and internal approval stay in DIFFERENT columns —
 * combining them lets an internally-approved-but-unsigned draft look
 * ready, which R06/R07 explicitly forbid.
 *
 * Row click opens a right Sheet detail (there is no dedicated
 * `/agreements/:id` route in this wave — Agent QQ owns that later).
 * The sheet shows the row's fields so a click never dead-ends.
 */

import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  listAgreements,
  type AgreementRow,
  type AgreementState,
} from "../../api/client";
import { EmptyState } from "../../ui-v2/EmptyState";
import { ErrorState } from "../../ui-v2/ErrorState";
import { PageHeader } from "../../ui-v2/PageHeader";
import { StatusBadge } from "../../ui-v2/StatusBadge";
import { Button } from "../../ui-v2/primitives/button";
import { Input } from "../../ui-v2/primitives/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "../../ui-v2/primitives/sheet";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../ui-v2/primitives/tabs";
import { agreementDisplay } from "./pipeline/agreementStatus";
import { UploadAgreementDialog } from "./agreements/UploadAgreementDialog";

type ViewKey = "all" | "nda" | "msa" | "needs_action";

const NEEDS_ACTION: AgreementState[] = [
  "missing",
  "requested",
  "drafting",
  "under_review",
  "sent",
  "partially_signed",
  "expired",
];

const INTERNAL_APPROVED: AgreementState[] = [
  "under_review",
  "sent",
  "partially_signed",
  "executed",
];

function internalApproval(state: AgreementState): {
  label: string;
  tone: "ok" | "warn" | "neutral";
} {
  if (state === "executed" || INTERNAL_APPROVED.includes(state)) {
    return { label: "Approved", tone: "ok" };
  }
  if (state === "drafting" || state === "requested") {
    return { label: "In review", tone: "warn" };
  }
  return { label: "Not started", tone: "neutral" };
}

function executionState(state: AgreementState): {
  label: string;
  tone: "ok" | "warn" | "danger" | "neutral";
} {
  if (state === "executed") return { label: "Executed", tone: "ok" };
  if (state === "partially_signed")
    return { label: "Partially signed", tone: "warn" };
  if (state === "sent") return { label: "Awaiting signature", tone: "warn" };
  if (state === "expired") return { label: "Expired", tone: "danger" };
  if (state === "terminated") return { label: "Terminated", tone: "danger" };
  if (state === "superseded") return { label: "Superseded", tone: "neutral" };
  return { label: "Not signed", tone: "neutral" };
}

function inView(row: AgreementRow, view: ViewKey): boolean {
  if (view === "all") return true;
  if (view === "nda") return row.kind === "NDA";
  if (view === "msa") return row.kind === "MSA";
  if (view === "needs_action") return NEEDS_ACTION.includes(row.state);
  return true;
}

function matchesSearch(row: AgreementRow, q: string): boolean {
  if (!q) return true;
  const needle = q.toLowerCase();
  return (
    row.kind.toLowerCase().includes(needle) ||
    (row.owner_email?.toLowerCase().includes(needle) ?? false) ||
    (row.next_action?.toLowerCase().includes(needle) ?? false) ||
    row.legal_entity_id.toLowerCase().includes(needle)
  );
}

export function AgreementsRegisterPage() {
  const [rows, setRows] = useState<AgreementRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [view, setView] = useState<ViewKey>("all");
  const [query, setQuery] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [detail, setDetail] = useState<AgreementRow | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await listAgreements();
        if (cancelled) return;
        setRows(res.items);
      } catch (err) {
        if (cancelled) return;
        setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(
    () => rows.filter((r) => inView(r, view) && matchesSearch(r, query)),
    [rows, view, query],
  );

  const counts = useMemo(
    () => ({
      all: rows.length,
      nda: rows.filter((r) => r.kind === "NDA").length,
      msa: rows.filter((r) => r.kind === "MSA").length,
      needs_action: rows.filter((r) => NEEDS_ACTION.includes(r.state)).length,
    }),
    [rows],
  );

  return (
    <div>
      <PageHeader
        title="NDA &amp; MSA register"
        subtitle="Entity-level agreement lifecycle. Legal execution and internal approval are shown separately — an approved draft is not a signed contract."
        actions={
          <Button
            variant="primary"
            onClick={() => setUploadOpen(true)}
            aria-label="Upload agreement"
          >
            Upload agreement
          </Button>
        }
      />

      {notice ? (
        <div
          role="status"
          className="mb-4 rounded-panel border border-primary/30 bg-primary-subtle px-4 py-3 text-body text-text"
        >
          {notice}
        </div>
      ) : null}

      <div className="flex flex-col gap-3 pb-4 sm:flex-row sm:items-center sm:justify-between">
        <Tabs
          value={view}
          onValueChange={(v) => setView(v as ViewKey)}
          className="min-w-0"
        >
          <TabsList aria-label="Agreement views">
            <TabsTrigger value="all">All agreements ({counts.all})</TabsTrigger>
            <TabsTrigger value="nda">NDA ({counts.nda})</TabsTrigger>
            <TabsTrigger value="msa">MSA ({counts.msa})</TabsTrigger>
            <TabsTrigger value="needs_action">
              Needs action ({counts.needs_action})
            </TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="sm:w-64">
          <Input
            type="search"
            aria-label="Search agreements"
            placeholder="Search owner, action or entity"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>

      <Tabs value={view} onValueChange={(v) => setView(v as ViewKey)}>
        <TabsContent value={view} forceMount>
          {loading ? (
            <div
              role="status"
              className="rounded-panel border border-divider p-6 text-body text-text-secondary"
            >
              Loading agreements…
            </div>
          ) : error ? (
            <ErrorState
              title="We couldn't load the register"
              description={
                error instanceof ApiError ? error.message : String(error)
              }
            />
          ) : filtered.length === 0 ? (
            <EmptyState
              title="No agreements match this view."
              description="Try All agreements, or upload a new NDA/MSA from the header."
            />
          ) : (
            <div className="overflow-x-auto rounded-panel border border-divider">
              <table
                className="w-full text-body"
                aria-label="Agreement register"
                data-testid="agreements-table"
              >
                <thead className="bg-primary-subtle/40">
                  <tr className="text-left text-secondary text-text-secondary">
                    <th className="px-3 py-2 font-medium">Agreement · type</th>
                    <th className="px-3 py-2 font-medium">Client / entity</th>
                    <th className="px-3 py-2 font-medium">Linked opportunity</th>
                    <th className="px-3 py-2 font-medium">Lifecycle</th>
                    <th
                      className="px-3 py-2 font-medium"
                      data-testid="col-internal-approval"
                    >
                      Internal approval
                    </th>
                    <th
                      className="px-3 py-2 font-medium"
                      data-testid="col-legal-execution"
                    >
                      Legal execution
                    </th>
                    <th className="px-3 py-2 font-medium">Effective · end</th>
                    <th className="px-3 py-2 font-medium">Owner · next</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((row) => {
                    const lifecycle = agreementDisplay(row.state);
                    const internal = internalApproval(row.state);
                    const execution = executionState(row.state);
                    return (
                      <tr
                        key={row.id}
                        data-testid={`agreement-row-${row.id}`}
                        className="cursor-pointer border-t border-divider hover:bg-primary-subtle/30"
                        onClick={() => setDetail(row)}
                      >
                        <td className="px-3 py-3 align-top">
                          <div className="text-text">{row.kind}</div>
                          <div className="text-secondary text-text-secondary">
                            v1 · {row.id.slice(0, 8)}
                          </div>
                        </td>
                        <td className="px-3 py-3 align-top text-text-secondary">
                          Entity {row.legal_entity_id.slice(0, 8)}
                        </td>
                        <td className="px-3 py-3 align-top text-text-secondary">
                          —
                        </td>
                        <td className="px-3 py-3 align-top">
                          <StatusBadge
                            tone={lifecycle.tone}
                            label={lifecycle.label}
                          />
                        </td>
                        <td className="px-3 py-3 align-top">
                          <StatusBadge
                            tone={internal.tone}
                            label={internal.label}
                          />
                        </td>
                        <td className="px-3 py-3 align-top">
                          <StatusBadge
                            tone={execution.tone}
                            label={execution.label}
                          />
                        </td>
                        <td className="px-3 py-3 align-top text-text-secondary tnum">
                          <div>{row.effective_from ?? "—"}</div>
                          <div>{row.expiry ?? "—"}</div>
                        </td>
                        <td className="px-3 py-3 align-top">
                          <div className="text-text">
                            {row.owner_email ?? "Unassigned"}
                          </div>
                          <div className="text-secondary text-text-secondary">
                            {row.next_action ?? "No next action"}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>
      </Tabs>

      <UploadAgreementDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onSubmit={(draft) => {
          setNotice(
            `Draft ${draft.kind} captured locally. Legal review is scheduled once the upload endpoint is wired — nothing has been sent yet.`,
          );
        }}
      />

      <Sheet
        open={detail !== null}
        onOpenChange={(o) => (o ? undefined : setDetail(null))}
      >
        <SheetContent aria-label="Agreement detail" className="overflow-y-auto">
          {detail ? (
            <>
              <SheetHeader>
                <SheetTitle>
                  {detail.kind} · {agreementDisplay(detail.state).label}
                </SheetTitle>
                <SheetDescription>
                  Full agreement detail is Agent QQ's territory. This drawer
                  shows the register fields so a click never dead-ends.
                </SheetDescription>
              </SheetHeader>
              <dl className="mt-4 grid grid-cols-1 gap-3 text-body">
                <div>
                  <dt className="text-secondary text-text-secondary">Entity</dt>
                  <dd className="text-text">{detail.legal_entity_id}</dd>
                </div>
                <div>
                  <dt className="text-secondary text-text-secondary">
                    Lifecycle
                  </dt>
                  <dd>
                    <StatusBadge
                      tone={agreementDisplay(detail.state).tone}
                      label={agreementDisplay(detail.state).label}
                    />
                  </dd>
                </div>
                <div>
                  <dt className="text-secondary text-text-secondary">
                    Internal approval
                  </dt>
                  <dd>
                    <StatusBadge
                      tone={internalApproval(detail.state).tone}
                      label={internalApproval(detail.state).label}
                    />
                  </dd>
                </div>
                <div>
                  <dt className="text-secondary text-text-secondary">
                    Legal execution
                  </dt>
                  <dd>
                    <StatusBadge
                      tone={executionState(detail.state).tone}
                      label={executionState(detail.state).label}
                    />
                  </dd>
                </div>
                <div>
                  <dt className="text-secondary text-text-secondary">
                    Effective from
                  </dt>
                  <dd className="tnum text-text">
                    {detail.effective_from ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-secondary text-text-secondary">Expiry</dt>
                  <dd className="tnum text-text">{detail.expiry ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-secondary text-text-secondary">Owner</dt>
                  <dd className="text-text">
                    {detail.owner_email ?? "Unassigned"}
                  </dd>
                </div>
                <div>
                  <dt className="text-secondary text-text-secondary">
                    Next action
                  </dt>
                  <dd className="text-text">
                    {detail.next_action ?? "No next action"}
                  </dd>
                </div>
              </dl>
            </>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
