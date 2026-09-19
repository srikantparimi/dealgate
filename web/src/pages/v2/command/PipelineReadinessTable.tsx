/**
 * Pipeline-client readiness table — spec §5 item 3 (+ §7 column order).
 *
 * Columns: client & owner · commercial stage · NDA · MSA · SOW gate /
 * package versions · next client action. NDA and MSA are separate,
 * always-clickable StatusBadges that open the underlying agreement — the
 * spec explicitly forbids a combined "Contracts" checkbox.
 */

import { Link } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../../../lib/cn";
import { StatusBadge, type StatusTone } from "../../../ui-v2/StatusBadge";

export interface AgreementCell {
  label: string;
  tone: StatusTone;
  href: string;
  icon?: LucideIcon;
}

export interface ReadinessRow {
  id: string;
  clientName: string;
  clientHref: string;
  ownerName: string | null;
  commercialStage: string | null;
  nda: AgreementCell | null;
  msa: AgreementCell | null;
  sowGate: {
    label: string;
    tone: StatusTone;
    href: string;
  } | null;
  packageVersion?: string | null;
  nextAction: {
    text: string | null;
    date: string | null;
  };
}

export interface PipelineReadinessTableProps {
  rows: ReadinessRow[];
  emptyMessage?: ReactNode;
  caption?: ReactNode;
}

function agreementCellNode(cell: AgreementCell | null, kind: string) {
  if (!cell) {
    return (
      <StatusBadge
        tone="warn"
        label={`${kind}: Missing`}
        aria-label={`${kind} missing`}
      />
    );
  }
  return (
    <Link
      to={cell.href}
      aria-label={`${kind} ${cell.label}`}
      className="inline-block focus-visible:outline-focus rounded-[6px]"
    >
      <StatusBadge tone={cell.tone} label={cell.label} icon={cell.icon} />
    </Link>
  );
}

export function PipelineReadinessTable({
  rows,
  emptyMessage,
  caption,
}: PipelineReadinessTableProps) {
  return (
    <section aria-label="Pipeline client readiness">
      <div className="mb-3 flex items-end justify-between gap-3">
        <h2 className="text-section text-text">Pipeline client readiness</h2>
        {caption ? (
          <span className="text-secondary text-text-secondary">{caption}</span>
        ) : null}
      </div>
      <div className="overflow-x-auto rounded-panel border border-divider bg-surface">
        {rows.length === 0 ? (
          <div
            role="status"
            className="p-6 text-body text-text-secondary text-center"
          >
            {emptyMessage ?? "No pipeline clients found."}
          </div>
        ) : (
          <table className="min-w-full text-body">
            <thead className="border-b border-divider bg-canvas/60">
              <tr>
                <Th>Client &amp; owner</Th>
                <Th>Commercial stage</Th>
                <Th>NDA</Th>
                <Th>MSA</Th>
                <Th>SOW gate / package</Th>
                <Th>Next client action</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.id}
                  className="border-b border-divider last:border-0 hover:bg-canvas/40"
                >
                  <td className="px-3 py-3 align-top">
                    <Link
                      to={r.clientHref}
                      className="text-body text-text font-medium hover:text-primary focus-visible:outline-focus"
                    >
                      {r.clientName}
                    </Link>
                    <div className="text-secondary text-text-secondary">
                      {r.ownerName ?? "Unassigned"}
                    </div>
                  </td>
                  <td className="px-3 py-3 align-top">
                    <span className="text-body text-text">
                      {r.commercialStage ?? "Unknown"}
                    </span>
                  </td>
                  <td className="px-3 py-3 align-top">
                    {agreementCellNode(r.nda, "NDA")}
                  </td>
                  <td className="px-3 py-3 align-top">
                    {agreementCellNode(r.msa, "MSA")}
                  </td>
                  <td className="px-3 py-3 align-top">
                    {r.sowGate ? (
                      <Link
                        to={r.sowGate.href}
                        className="inline-block focus-visible:outline-focus rounded-[6px]"
                        aria-label={`SOW gate ${r.sowGate.label}`}
                      >
                        <StatusBadge
                          tone={r.sowGate.tone}
                          label={r.sowGate.label}
                        />
                      </Link>
                    ) : (
                      <span className="text-secondary text-text-secondary">
                        No SOW yet
                      </span>
                    )}
                    {r.packageVersion ? (
                      <div className="mt-1 text-secondary text-text-secondary">
                        {r.packageVersion}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-3 py-3 align-top">
                    <div className="text-body text-text">
                      {r.nextAction.text ?? (
                        <span className="text-text-secondary">
                          No action recorded
                        </span>
                      )}
                    </div>
                    {r.nextAction.date ? (
                      <div className="text-secondary text-text-secondary tnum">
                        Due {r.nextAction.date}
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

function Th({ children }: { children: ReactNode }) {
  return (
    <th
      scope="col"
      className={cn(
        "px-3 py-2 text-left text-secondary uppercase tracking-wide",
        "text-text-secondary font-medium",
      )}
    >
      {children}
    </th>
  );
}
