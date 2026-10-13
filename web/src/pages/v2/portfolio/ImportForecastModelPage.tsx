/**
 * /import/forecast-model — Import the forecast model (S22 P5-7), as the
 * prototype's renderImport(): upload the FY forecast model master → the server
 * dry-runs it (BU cards, per-tab table, the report markdown) → "Load …" posts
 * the same file with dry_run=false and lands on /portfolio.
 *
 * Every count on the page is the importer's (POST /engagements/import-forecast-model);
 * the browser only renders the report it is handed.
 */

import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Upload } from "lucide-react";
import { ENGAGEMENT_TYPE_LABEL, errorsFrom, importForecastModel, type EngagementType, type ForecastModelImportResult } from "../../../api/engagements";
import { Button } from "../../../ui-v2/primitives/button";
import { Markdown } from "../../../ui-v2/Markdown";
import { PageHeader } from "../../../ui-v2/PageHeader";
import { cn } from "../../../lib/cn";
import { Panel, errorText, headCell, headCellNum, numCell, table, tableWrap, textCell } from "./shared";

const field = "min-h-control-compact rounded-control border border-input-border bg-warning-surface px-2 py-1 text-body text-text disabled:bg-surface-sunken disabled:text-text-muted";

function typeLabel(type: string): string {
  return (ENGAGEMENT_TYPE_LABEL as Record<string, string>)[type as EngagementType] ?? type;
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

export function ImportForecastModelPage() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ForecastModelImportResult | null>(null);
  const [errors, setErrors] = useState<string[] | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [phase, setPhase] = useState<"idle" | "dry-run" | "loading">("idle");
  const fileInput = useRef<HTMLInputElement | null>(null);

  async function dryRun(picked: File | undefined) {
    if (!picked) return;
    setFile(picked);
    setResult(null);
    setErrors(null);
    setMessage(`Reading ${picked.name}…`);
    setPhase("dry-run");
    try {
      setResult(await importForecastModel(picked, true));
      setMessage(null);
    } catch (cause) {
      const problems = errorsFrom(cause);
      if (problems) {
        setErrors(problems);
        setMessage(null);
      } else {
        setMessage(errorText(cause, "Could not read that file."));
      }
    } finally {
      setPhase("idle");
    }
  }

  async function load() {
    if (!file || !result) return;
    setErrors(null);
    setMessage("Loading the model…");
    setPhase("loading");
    try {
      await importForecastModel(file, false);
      navigate("/portfolio");
    } catch (cause) {
      const problems = errorsFrom(cause);
      if (problems) setErrors(problems);
      else setMessage(errorText(cause, "The model was not loaded."));
      if (problems) setMessage(null);
      setPhase("idle");
    }
  }

  // The button's label counts what the dry run listed: people across the client tabs, into that many clients.
  const blockers = result?.blockers ?? [];
  const peopleCount = result ? result.tabs.reduce((sum, tab) => sum + tab.people, 0) : 0;
  const clientCount = result ? result.tabs.length : 0;
  const busy = phase !== "idle";

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Import the forecast model"
        subtitle="The FY forecast model master (one tab per client, one row per person, month blocks). Dry run first — nothing is created until you confirm."
      />

      <Panel className="max-w-4xl" title="1 · Upload the workbook">
        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={fileInput}
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            aria-label="Forecast model (.xlsx)"
            className={cn(field, "max-w-md")}
            disabled={busy}
            onChange={(event) => void dryRun(event.target.files?.[0])}
          />
          {message ? (
            <span role="status" className="text-secondary text-text-secondary">
              {message}
            </span>
          ) : null}
        </div>
        {errors ? (
          <p role="alert" className="mt-2 text-secondary text-danger" data-testid="import-errors">
            {errors.join(" · ")}
          </p>
        ) : null}
        <p className="mt-3 text-secondary text-text-secondary">
          What the importer does: <b>dashboard</b> → business unit, sales owner, delivery owner, billing type per client · <b>client tab</b> → one engagement per SOW/PO (<i>Team/SOW</i> column) ·{" "}
          <b>row</b> → one allocation per person, plus one per extension-date pair · <b>Actual</b> months → billed revenue and hours (vacation and unplanned leave deducted) · <b>WorkingDays</b> →
          holidays per location. A flat Max Billing every month (Costco-style 173 h) becomes a monthly rate; <i>-OVERTIME</i> / <i>-ON CALL</i> rows carry actuals only; CLOSED tabs import as closed.
        </p>
      </Panel>

      {result ? (
        <Panel className="max-w-6xl" title="2 · Dry run — what would be created" id="dry-run">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="dry-run-cards">
            {result.by_business_unit.map((unit) => (
              <div key={unit.business_unit} className="rounded-card border border-divider bg-surface p-4" data-testid="dry-run-card" data-bu={unit.business_unit}>
                <div className="text-label uppercase tracking-wide text-text-secondary">{unit.business_unit}</div>
                <div className="mt-1 font-display text-metric tnum">{unit.clients}</div>
                <div className="mt-1 text-secondary text-text-secondary">
                  {plural(unit.engagements, "engagement")} · {unit.people} people · {unit.closed} closed
                </div>
              </div>
            ))}
          </div>

          <div className={cn(tableWrap, "mt-3")}>
            <table className={table} aria-label="Dry run by client tab" data-testid="dry-run-tabs">
              <thead>
                <tr>
                  <th className={headCell}>Tab</th>
                  <th className={headCell}>Client (dashboard)</th>
                  <th className={headCell}>BU</th>
                  <th className={headCell}>Type</th>
                  <th className={headCellNum}>Engagements</th>
                  <th className={headCellNum}>People</th>
                  <th className={headCellNum}>Allocations (ext.)</th>
                  <th className={headCellNum}>Months (with actuals)</th>
                  <th className={headCell}>Needs attention</th>
                </tr>
              </thead>
              <tbody>
                {result.tabs.map((tab) => (
                  <tr key={tab.tab} data-testid="dry-run-tab" data-bu={tab.business_unit ?? ""}>
                    <td className={cn(textCell, "font-semibold")}>{tab.tab}</td>
                    <td className={textCell}>{tab.client}</td>
                    <td className={cn(textCell, !tab.business_unit && "text-danger")}>{tab.business_unit ?? "—"}</td>
                    <td className={textCell}>{typeLabel(tab.engagement_type)}</td>
                    <td className={numCell}>{tab.engagements}</td>
                    <td className={numCell}>{tab.people}</td>
                    <td className={numCell}>
                      {tab.allocations} ({tab.extensions})
                    </td>
                    <td className={numCell}>
                      {tab.months} ({tab.actual_months})
                    </td>
                    <td className={cn("px-3 py-2 text-secondary", tab.issues.length ? "text-warning" : "text-text-secondary")}>{tab.issues.length ? tab.issues.join(" · ") : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <section className="mt-4 rounded-card border border-divider bg-surface-sunken/40 p-4" aria-label="Dry-run report" data-testid="dry-run-report">
            <Markdown source={result.report_markdown} />
          </section>

          <p className="mt-3 text-secondary text-text-secondary">
            Not loaded from this workbook: <b>costs</b> (the Costing Sheet is empty — every imported person is <i>cost unknown</i> and the engagement shows INCOMPLETE until the rate card or a cost per
            hour is set) · clients that exist only as a number on the dashboard (no tab) · currency for Retro Rabbit (assumed USD).
          </p>

          {blockers.length > 0 ? (
            <section className="mt-4 rounded-card border border-danger bg-danger-surface/30 p-4" aria-label="Fix these in the workbook before loading" data-testid="blockers-panel">
              <h2 className="text-heading-sm text-danger">Fix these in the workbook before loading</h2>
              <p className="mt-1 text-secondary text-text-secondary">
                Each one is a blank cell. Loading anyway would file the rows under a default — the totals on screen would still add up, and only the margin underneath would be wrong — so the import stops here
                instead.
              </p>
              <ul className="mt-3 space-y-3 pl-5 list-disc">
                {blockers.map((blocker) => (
                  <li key={`${blocker.kind}:${blocker.tab}`} data-testid="blocker" data-kind={blocker.kind} data-tab={blocker.tab}>
                    <span className="font-semibold">{blocker.tab}</span> — {blocker.detail}.
                    <div className="mt-0.5 text-secondary text-text-secondary" data-testid="blocker-fix">
                      {blocker.fix}
                    </div>
                  </li>
                ))}
              </ul>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <Button disabled title="Fill the cells above and upload again" data-testid="load-button">
                  <Upload className="mr-1 h-4 w-4" aria-hidden />
                  {`Load ${peopleCount} people into ${plural(clientCount, "client")}`}
                </Button>
                <span className="text-secondary text-text-secondary" data-testid="blockers-count">
                  {`${blockers.length} ${blockers.length === 1 ? "thing" : "things"} to fix · re-upload when the workbook carries them`}
                </span>
              </div>
            </section>
          ) : (
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <Button onClick={() => void load()} disabled={busy} data-testid="load-button">
                <Upload className="mr-1 h-4 w-4" aria-hidden />
                {phase === "loading" ? "Loading…" : `Load ${peopleCount} people into ${plural(clientCount, "client")}`}
              </Button>
              <span className="text-secondary text-text-secondary">Creates the clients, engagements, allocations and actuals above, then opens the portfolio. Re-importing the same file updates rows, never duplicates them.</span>
            </div>
          )}
        </Panel>
      ) : null}
    </div>
  );
}
