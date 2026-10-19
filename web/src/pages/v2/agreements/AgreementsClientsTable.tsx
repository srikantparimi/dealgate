// S24-AG1 F1/F12 · the Clients list: Client, Relationship, Furthest open stage,
// NDA, MSA and Action. A table from `sm` up; below it every row is a stacked
// card with inline labels (the Pipeline's ClientsTable pattern), so 375 px has
// no horizontal scroll. Every value is a React text node. A client that needs
// attention gets "↑ Upload client copy" (Legal and SystemAdmin; locked with the
// reason for everyone else); every other client gets "Open →".
import { Badge } from "../../../ui-v2/primitives/badge";
import { AgreementStateTag, AgreementTag, FLAG_TEXT, RelationshipTag } from "../../../ui-v2/AgreementStateTag";
import { LockedButton } from "../../../ui-v2/LockedButton";
import { cn } from "../../../lib/cn";
import { InlineLabel, cellClass, linkButtonClass } from "../pipeline/DealsTable";
import { plural } from "../pipeline/format";
import { CompanyMark, Glyph } from "../pipeline/tags";
import { basisText, stageLabel, stageTone, type AgreementsClientRow } from "./agreementsState";
import type { AgreementRoles } from "./useAgreementsWorkspace";

const HEADERS = ["Client", "Relationship", "Furthest open stage", "NDA", "MSA", "Action"];
/** Preferred widths from `sm` up: the client column takes the rest, so a state tag stays on one line. */
const WIDTHS = ["", "sm:w-[170px]", "sm:w-[170px]", "sm:w-[160px]", "sm:w-[160px]", "sm:w-[180px]"];

/** The business-unit colours the Pipeline uses (tags.tsx BU_TEXT). */
const BU_TEXT: Record<string, string> = {
  ST21: "text-success",
  "IT Avalon": "text-primaryText",
  "Retro Rabbit": "text-warning",
};

export interface AgreementsClientsTableProps {
  rows: AgreementsClientRow[];
  roles: AgreementRoles | null;
  onOpenClient: (clientId: string) => void;
  onUploadClientCopy: (row: AgreementsClientRow) => void;
}

export function AgreementsClientsTable({ rows, roles, onOpenClient, onUploadClientCopy }: AgreementsClientsTableProps) {
  const lock = roles && !roles.canWrite ? "writer" : null;
  return (
    <div className="sm:overflow-x-auto">
      <table aria-label="Clients" className="block w-full text-table sm:table sm:min-w-[960px] sm:border-collapse">
        <thead className="hidden bg-surface-sunken sm:table-header-group">
          <tr>
            {HEADERS.map((h, i) => (
              <th
                key={h}
                scope="col"
                className={cn(
                  i === 0 ? "pl-4 pr-2" : i === HEADERS.length - 1 ? "pl-2 pr-4" : "px-2",
                  "py-2 text-left text-secondary font-medium text-text-secondary",
                  WIDTHS[i],
                )}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="block sm:table-row-group">
          {rows.map((row) => (
            <tr
              key={row.client_id}
              data-row-key={row.client_id}
              className={cn(
                "grid grid-cols-2 gap-x-4 gap-y-3 border-t border-border p-4 first:border-t-0",
                "sm:table-row sm:border-t-0 sm:p-0 sm:hover:bg-surface-sunken",
              )}
            >
              <td className={cn(cellClass, "col-span-2 sm:pl-4")}>
                <span className="flex items-start gap-3">
                  <CompanyMark name={row.name} />
                  <span className="flex min-w-0 flex-col items-start gap-1">
                    <button
                      type="button"
                      data-row-focus
                      aria-haspopup="dialog"
                      onClick={() => onOpenClient(row.client_id)}
                      className="rounded-control text-left text-body font-semibold text-text hover:underline focus-visible:outline-focus [overflow-wrap:anywhere]"
                    >
                      {row.name}
                    </button>
                    <span className="text-secondary text-text-secondary">
                      <BusinessUnits row={row} />
                      {` · ${row.deal_count} ${plural(row.deal_count, "deal", "deals")}`}
                    </span>
                    {row.flags.length ? (
                      <span className="flex flex-wrap gap-1">
                        {row.flags.map((flag) => {
                          const f = FLAG_TEXT[flag];
                          return f ? (
                            <AgreementTag key={flag} tone={f.tone}>
                              {f.text}
                            </AgreementTag>
                          ) : null;
                        })}
                      </span>
                    ) : null}
                  </span>
                </span>
              </td>
              <td className={cellClass}>
                <InlineLabel>Relationship</InlineLabel>
                <span className="flex flex-col items-start gap-1">
                  <RelationshipTag relationship={row.relationship} />
                  <span className="text-secondary text-text-secondary">{basisText(row)}</span>
                </span>
              </td>
              <td className={cellClass}>
                <InlineLabel>Furthest open stage</InlineLabel>
                <StageCell row={row} />
              </td>
              <td className={cellClass}>
                <InlineLabel>NDA</InlineLabel>
                <AgreementStateTag state={row.nda.state} />
              </td>
              <td className={cellClass}>
                <InlineLabel>MSA</InlineLabel>
                <AgreementStateTag state={row.msa.state} />
              </td>
              <td className={cn(cellClass, "col-span-2 sm:pr-4")}>
                {row.needs_attention ? (
                  <LockedButton
                    size="sm"
                    aria-haspopup="dialog"
                    aria-label={`Upload client copy for ${row.name}`}
                    lock={lock}
                    disabled={roles === null}
                    onClick={() => onUploadClientCopy(row)}
                  >
                    <span aria-hidden>↑</span>
                    Upload client copy
                  </LockedButton>
                ) : (
                  <button
                    type="button"
                    aria-haspopup="dialog"
                    aria-label={`Open ${row.name}`}
                    onClick={() => onOpenClient(row.client_id)}
                    className={cn(linkButtonClass, "whitespace-nowrap text-table font-semibold")}
                  >
                    Open
                    <Glyph>→</Glyph>
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** "ST21 · US", several joined by commas; with none, the server's reason or "No business unit". */
export function BusinessUnits({ row }: { row: Pick<AgreementsClientRow, "business_units" | "business_unit_note"> }) {
  if (!row.business_units.length) {
    return <span>{row.business_unit_note?.trim() || "No business unit"}</span>;
  }
  return (
    <>
      {row.business_units.map((unit, i) => (
        <span key={`${unit.name}-${unit.region}`}>
          {i ? ", " : ""}
          <span className={cn("font-semibold", BU_TEXT[unit.name] ?? "text-text")}>{unit.name}</span>
          {` · ${unit.region}`}
        </span>
      ))}
    </>
  );
}

function StageCell({ row }: { row: AgreementsClientRow }) {
  const label = stageLabel(row);
  if (!label) return <span className="text-secondary text-text-secondary">No active deal</span>;
  return (
    <Badge tone={stageTone(row)} className="h-auto min-h-[22px] whitespace-normal py-[3px] leading-tight">
      {label}
    </Badge>
  );
}
