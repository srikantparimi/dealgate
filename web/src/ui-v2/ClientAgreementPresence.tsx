// S24-AG1 F3/B10 · the client's NDA and MSA strip on the deal page, the client page and the SOW
// workspace. Same endpoint, states and wording as the Agreements page (GET /clients/{id}/agreements and
// the shared state tags), the amber warning for a net-new client past stage 1, and an Upload that opens
// the upload dialog right here (CLAUDE.md rule 13: no redirect-only editor). Non-writers see the Upload
// locked with its reason; the server refuses them regardless.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { AGREEMENT_KINDS, getClientAgreements, type AgreementKind, type ClientAgreements } from "../api/agreements";
import { UploadDialog } from "../pages/v2/agreements/UploadDialog";
import { AgreementStateTag } from "./AgreementStateTag";
import { LockedButton } from "./LockedButton";

export function ClientAgreementPresence({ clientId }: { clientId: string | null | undefined }) {
  return clientId ? <Presence key={clientId} clientId={clientId} /> : <p>Client documents unavailable: no client linked.</p>;
}

function Presence({ clientId }: { clientId: string }) {
  const [data, setData] = useState<ClientAgreements | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [upload, setUpload] = useState<AgreementKind | null>(null);

  useEffect(() => {
    const ctl = new AbortController();
    setError(null);
    getClientAgreements(clientId, ctl.signal).then(
      (next) => {
        if (!ctl.signal.aborted) setData(next);
      },
      (e: unknown) => {
        if (!ctl.signal.aborted) setError(e instanceof Error && e.message ? e.message : "Documents unavailable");
      },
    );
    return () => ctl.abort();
  }, [clientId, reload]);

  const missing = data ? AGREEMENT_KINDS.filter((kind) => cardOf(data, kind).state === "missing") : [];

  return (
    <section aria-label="Client NDA and MSA" className="my-4 flex flex-col gap-2 border-y border-divider py-3 text-body">
      <h2 className="font-medium">Client documents</h2>
      {error ? (
        <div role="alert">
          {error}{" "}
          <button type="button" onClick={() => setReload((n) => n + 1)} className="underline">
            Retry documents
          </button>
        </div>
      ) : data === null ? (
        <p role="status">Loading client documents...</p>
      ) : (
        <>
          {data.needs_attention && missing.length ? (
            <p className="rounded-control border-l-4 border-warning bg-warning-surface px-3 py-2 text-secondary text-warning">
              {`Net new, past stage 1, ${missing.join(" and ")} missing.`}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-x-8 gap-y-3">
            {AGREEMENT_KINDS.map((kind) => {
              const card = cardOf(data, kind);
              const held = card.state === "client" || card.state === "standard" || card.state === "covered";
              const path = `/agreements?client_id=${encodeURIComponent(clientId)}&kind=${kind}`;
              return (
                <div key={kind} className="flex flex-wrap items-center gap-3">
                  <span className="font-medium">{kind}</span>
                  <AgreementStateTag state={card.state} />
                  {held ? (
                    <Link to={path} aria-label={`View ${kind} documents`} className="underline">
                      View
                    </Link>
                  ) : null}
                  <LockedButton
                    variant="secondary"
                    size="sm"
                    lock={data.can_write ? null : "writer"}
                    onClick={() => setUpload(kind)}
                  >
                    <span aria-hidden="true">{"↑ "}</span>
                    {`Upload ${kind}`}
                  </LockedButton>
                </div>
              );
            })}
          </div>
          {data.can_write ? (
            <UploadDialog
              open={upload !== null}
              target={{ mode: "client", clientId, clientName: data.name, kind: upload ?? "NDA", lockTarget: true }}
              canWrite={data.can_write}
              onOpenChange={(open) => {
                if (!open) setUpload(null);
              }}
              onUploaded={() => {
                setUpload(null);
                setReload((n) => n + 1);
              }}
            />
          ) : null}
        </>
      )}
    </section>
  );
}

function cardOf(data: ClientAgreements, kind: AgreementKind) {
  return kind === "NDA" ? data.nda : data.msa;
}
