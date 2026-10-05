import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Check, FilePlus2, Files, Minus } from "lucide-react";
import { getMe, listAgreements, type AgreementRow } from "../api/client";

export function ClientAgreementPresence({
  clientId,
}: {
  clientId: string | null | undefined;
}) {
  return clientId ? (
    <Presence key={clientId} clientId={clientId} />
  ) : (
    <p>Client documents unavailable: no client linked.</p>
  );
}

function Presence({ clientId }: { clientId: string }) {
  const [rows, setRows] = useState<AgreementRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [canWrite, setCanWrite] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let live = true;
    setRows(null);
    setError(null);
    listAgreements({ client_id: clientId }).then(
      (result) => {
        if (live) setRows(result.items);
      },
      (e) => {
        if (live)
          setError(e instanceof Error ? e.message : "Documents unavailable");
      },
    );
    getMe().then(
      (actor) => {
        if (live)
          setCanWrite(
            actor.groups.some((g) => ["Legal", "SystemAdmin"].includes(g)),
          );
      },
      () => {
        if (live) setCanWrite(false);
      },
    );
    return () => {
      live = false;
    };
  }, [clientId, reload]);
  return (
    <section
      aria-label="Client NDA and MSA"
      className="my-4 border-y border-divider py-3 text-body"
    >
      <h2 className="font-medium">Client documents</h2>
      {error ? (
        <div role="alert">
          {error}{" "}
          <button onClick={() => setReload((n) => n + 1)} className="underline">
            Retry documents
          </button>
        </div>
      ) : rows === null ? (
        <p role="status">Loading client documents...</p>
      ) : (
        <div className="flex flex-wrap gap-x-8 gap-y-3">
          {(["NDA", "MSA"] as const).map((kind) => {
            const count = rows.filter((r) => r.kind === kind).length;
            const path = `/agreements?client_id=${encodeURIComponent(clientId)}&kind=${kind}`;
            return (
              <div key={kind} className="flex flex-wrap items-center gap-3">
                <span className="inline-flex items-center gap-1">
                  {count ? (
                    <Check size={16} aria-hidden="true" />
                  ) : (
                    <Minus size={16} aria-hidden="true" />
                  )}
                  {kind}: {count ? `${count} on file` : "Not on file"}
                </span>
                {count > 0 && (
                  <Link
                    to={path}
                    aria-label={`View ${kind} documents`}
                    className="inline-flex items-center gap-1 underline"
                  >
                    <Files size={16} />
                    View
                  </Link>
                )}
                {canWrite && (
                  <Link
                    to={`${path}&upload=1`}
                    aria-label={`Upload ${kind}`}
                    className="inline-flex items-center gap-1 underline"
                  >
                    <FilePlus2 size={16} />
                    Upload
                  </Link>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
