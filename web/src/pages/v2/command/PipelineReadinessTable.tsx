/**
 * Pipeline-client readiness table — DealGate v2.1 prototype (lines 375–381,
 * 536).
 *
 * Columns: Client · owner · Stage · NDA · MSA · SOW gate · Next client
 * action. Table wrapper is a `.card`; the table itself uses 13px cells,
 * 36px header row, 44px body row (via `--row` density variable).
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
  title?: string;
  moreLabel?: string;
  moreHref?: string;
}

function agreementCellNode(cell: AgreementCell | null, kind: string) {
  if (!cell) {
    return (
      <StatusBadge
        tone="warning"
        label="Missing"
        aria-label={`${kind} missing`}
      />
    );
  }
  return (
    <Link
      to={cell.href}
      aria-label={`${kind} ${cell.label}`}
      className="inline-block focus-visible:outline-focus rounded-[4px]"
    >
      <StatusBadge tone={cell.tone} label={cell.label} icon={cell.icon} />
    </Link>
  );
}

export function PipelineReadinessTable({
  rows,
  emptyMessage,
  caption,
  title = "Pipeline client readiness",
  moreLabel,
  moreHref,
}: PipelineReadinessTableProps) {
  return (
    <section
      aria-label={title}
      className="rounded-card border border-border bg-surface"
    >
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-5 pt-4">
        <h2 className="text-section font-semibold text-text">{title}</h2>
        {caption ? (
          <span className="text-[12px] text-text-muted">{caption}</span>
        ) : null}
        {moreLabel && moreHref ? (
          <Link
            to={moreHref}
            className="ml-auto text-[13px] text-primaryText hover:underline focus-visible:outline-focus"
          >
            {moreLabel}
          </Link>
        ) : null}
      </header>
      <div className="overflow-x-auto p-2">
        {rows.length === 0 ? (
          <div
            role="status"
            className="p-6 text-center text-body text-text-secondary"
          >
            {emptyMessage ?? "No pipeline clients found."}
          </div>
        ) : (
          <table className="w-full border-collapse text-[13px] leading-[1.4]">
            <thead>
              <tr>
                <Th>Client &middot; owner</Th>
                <Th>Stage</Th>
                <Th>NDA</Th>
                <Th>MSA</Th>
                <Th>SOW gate</Th>
                <Th>Next client action</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.id}
                  className="border-b border-border last:border-b-0 transition-motion hover:bg-surface-sunken"
                >
                  <Td>
                    <Link
                      to={r.clientHref}
                      className="font-medium text-text hover:text-primaryText hover:underline focus-visible:outline-focus"
                    >
                      {r.clientName}
                    </Link>
                    <div className="text-[12px] text-text-secondary">
                      {r.ownerName ?? "Unassigned"}
                    </div>
                  </Td>
                  <Td>{r.commercialStage ?? "Unknown"}</Td>
                  <Td>{agreementCellNode(r.nda, "NDA")}</Td>
                  <Td>{agreementCellNode(r.msa, "MSA")}</Td>
                  <Td>
                    {r.sowGate ? (
                      <Link
                        to={r.sowGate.href}
                        className="inline-block focus-visible:outline-focus rounded-[4px]"
                        aria-label={`SOW gate ${r.sowGate.label}`}
                      >
                        <StatusBadge tone={r.sowGate.tone} label={r.sowGate.label} />
                      </Link>
                    ) : (
                      <span className="text-text-secondary">No SOW yet</span>
                    )}
                    {r.packageVersion ? (
                      <div className="mt-1 text-[12px] text-text-muted">
                        {r.packageVersion}
                      </div>
                    ) : null}
                  </Td>
                  <Td>
                    <div className="text-text">
                      {r.nextAction.text ?? (
                        <span className="text-text-secondary">
                          No action recorded
                        </span>
                      )}
                    </div>
                    {r.nextAction.date ? (
                      <div className="text-[12px] text-text-muted tnum">
                        Due {r.nextAction.date}
                      </div>
                    ) : null}
                  </Td>
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
        "h-[36px] border-b border-border px-3 text-left",
        "text-[11px] uppercase tracking-[0.05em] font-semibold",
        "text-text-secondary whitespace-nowrap",
      )}
    >
      {children}
    </th>
  );
}

function Td({ children }: { children: ReactNode }) {
  return (
    <td
      className={cn(
        "px-3 align-middle border-b border-border",
        "h-[var(--dg-row-height)]",
      )}
    >
      {children}
    </td>
  );
}
