/**
 * /engagements/:id/:tab — one engagement (S22 P2-1 … P2-3), as the prototype:
 * header, status line, tabs Allocations · Forecast · Setup & costs.
 *
 * Everything shown is the engine's output served by the API; the page never
 * computes a number. Edits PATCH the ledger and the whole page reloads from
 * the server, so a change on one tab is reflected on the others.
 *
 * S24-AG1 F11: an engagement created together with a new client (by hand, on
 * New engagement) shows "Add the NDA and MSA now (optional)" until dismissed. It
 * opens the shared upload dialog for that client; Legal and SystemAdmin upload,
 * every other role sees the button locked with the reason (the API refuses them too).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { AGREEMENT_KINDS, type AgreementKind } from "../../../api/agreements";
import {
  ENGAGEMENT_TYPE_LABEL,
  dismissAgreementsOffer,
  dismissImportNote,
  getEngagement,
  getEngagementForecast,
  getForecastSettings,
  listAllocations,
  listCosts,
  rememberAgreementsOffer,
  takeAgreementsOffer,
  takeImportNote,
  type AgreementsOffer,
  type Allocation,
  type Engagement,
  type EngagementCost,
  type Forecast,
  type ForecastCalendar,
} from "../../../api/engagements";
import { Button } from "../../../ui-v2/primitives/button";
import { ErrorState } from "../../../ui-v2/ErrorState";
import { LockedButton } from "../../../ui-v2/LockedButton";
import { UploadDialog } from "../agreements/UploadDialog";
import { PageHeader } from "../../../ui-v2/PageHeader";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import { Tabs, TabsList, TabsTrigger } from "../../../ui-v2/primitives/tabs";
import { duration, hours, money, pct } from "./format";
import { StatusPill, WRITE_ROLES, errorText, hasAny, useGroups } from "./shared";
import { AllocationsTab } from "./AllocationsTab";
import { ForecastTab } from "./ForecastTab";
import { SetupTab } from "./SetupTab";

export type EngagementTab = "allocations" | "forecast" | "setup";

/** Agreements writers (S24-AG1 B11): Legal and SystemAdmin. */
const AGREEMENT_WRITE_ROLES = ["Legal", "SystemAdmin"];

/** Whole hours without a trailing .0, otherwise two places — display only. */
function hoursText(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}
const TABS: { id: EngagementTab; label: string }[] = [
  { id: "allocations", label: "Allocations" },
  { id: "forecast", label: "Forecast" },
  { id: "setup", label: "Setup & costs" },
];

export interface EngagementData {
  engagement: Engagement;
  allocations: Allocation[];
  costs: EngagementCost[];
  forecast: Forecast;
  /** null when the caller may not read the calendar (rate card is individual cost). */
  calendar: ForecastCalendar | null;
}

export function EngagementPage() {
  const { id = "", tab: rawTab } = useParams<{ id: string; tab?: string }>();
  const tab: EngagementTab = rawTab === "forecast" || rawTab === "setup" ? rawTab : "allocations";
  const navigate = useNavigate();
  const groups = useGroups();
  const canWrite = hasAny(groups, WRITE_ROLES);
  const [data, setData] = useState<EngagementData | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  // P4-4: an engagement created from the sheet shows its import warnings + hours check once.
  const [importNote, setImportNote] = useState(() => takeImportNote(id));
  // S24-AG1 F11: a client created by hand with this engagement.
  const [agreementsOffer, setAgreementsOffer] = useState(() => takeAgreementsOffer(id));

  const reload = useCallback(async () => {
    setError(null);
    try {
      const [engagement, allocations, costs, forecast, calendar] = await Promise.all([
        getEngagement(id),
        listAllocations(id),
        listCosts(id),
        getEngagementForecast(id),
        getForecastSettings().catch(() => null),
      ]);
      setData({ engagement, allocations, costs, forecast, calendar });
    } catch (cause) {
      setError(cause);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    setLoading(true);
    void reload();
  }, [reload]);

  if (error) {
    return <ErrorState title="We couldn't load this engagement." description={errorText(error, "Retry to try again.")} onRetry={() => void reload()} />;
  }
  if (loading || !data) {
    return (
      <p role="status" className="text-body text-text-secondary">
        Loading engagement…
      </p>
    );
  }

  const { engagement, forecast } = data;
  const floor = forecast.project_floor_pct;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={
          <span data-testid="engagement-heading">
            {engagement.client_name} · {engagement.name}
          </span>
        }
        subtitle={
          <span data-testid="engagement-subtitle">
            {engagement.business_unit} · {ENGAGEMENT_TYPE_LABEL[engagement.type]} · {engagement.start} → {engagement.end} · {duration(forecast.duration_months)} months · sales{" "}
            {engagement.sales_owner ?? "—"} · delivery {engagement.delivery_owner ?? "—"} · HubSpot: {engagement.hubspot_deal_id ?? "—"}
            {engagement.closed ? (
              <>
                {" · "}
                <span data-testid="closed-badge" className="inline-flex align-middle">
                  <StatusBadge tone="neutral" label="CLOSED" />
                </span>
              </>
            ) : null}
          </span>
        }
        actions={
          <Button variant="secondary" onClick={() => navigate("/portfolio")}>
            <ArrowLeft className="mr-1 h-4 w-4" aria-hidden /> Portfolio
          </Button>
        }
      />

      {importNote ? (
        <div className="rounded-card border border-dashed border-primary bg-primary-subtle px-4 py-3 text-body" data-testid="import-note">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="font-medium">Imported from the sheet.</p>
              {importNote.warnings.length > 0 ? <p className="mt-1 text-secondary">{importNote.warnings.join(" · ")}</p> : null}
              {importNote.hours_check.length > 0 ? (
                <ul className="mt-1 text-secondary">
                  {importNote.hours_check.map((row) => (
                    <li key={row.role}>
                      {row.sheet_hours === null
                        ? `${row.role}: ${row.note}`
                        : row.note === "matches the sheet"
                          ? `${row.role}: ${hours(row.engine_hours)} h — matches the sheet`
                          : `Sheet said ${hoursText(row.sheet_hours)} h for ${row.role}; ${row.note}`}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                dismissImportNote(id);
                setImportNote(null);
              }}
            >
              Dismiss
            </Button>
          </div>
        </div>
      ) : null}

      {agreementsOffer ? (
        <AgreementsOfferNote
          offer={agreementsOffer}
          canWrite={hasAny(groups, AGREEMENT_WRITE_ROLES)}
          onUploaded={(next) => {
            rememberAgreementsOffer(id, next);
            setAgreementsOffer(next);
          }}
          onDismiss={() => {
            dismissAgreementsOffer(id);
            setAgreementsOffer(null);
          }}
        />
      ) : null}

      <div className="flex flex-wrap items-center gap-3 rounded-card border border-divider bg-surface px-4 py-3" data-testid="status-line" role="status">
        <StatusPill status={forecast.status} />
        <b className="font-display text-section">GM {pct(forecast.totals.gm_pct)}</b>
        <span className="text-secondary text-text-secondary">project floor {pct(floor)}</span>
        <span className="text-secondary text-text-secondary">
          · revenue {money(forecast.totals.total_revenue)} · cost {money(forecast.totals.total_cost)} · hours {hours(forecast.totals.hours)}
        </span>
        {Object.entries(forecast.location_check).map(([location, check]) => (
          <StatusBadge
            key={location}
            tone={check.ok ? "success" : "warning"}
            label={`${location} resources ${pct(check.gm_pct)} vs ${pct(check.floor)}${check.ok ? "" : " · review rates"}`}
          />
        ))}
        {forecast.missing.length > 0 ? <StatusBadge tone="warning" label={`Missing: ${forecast.missing.join(", ")}`} /> : null}
      </div>

      <Tabs value={tab} onValueChange={(value) => navigate(`/engagements/${id}/${value}`)}>
        <TabsList aria-label="Engagement sections">
          {TABS.map((t) => (
            <TabsTrigger key={t.id} value={t.id}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {tab === "allocations" ? (
        <AllocationsTab data={data} canWrite={canWrite} onChanged={reload} />
      ) : tab === "forecast" ? (
        <ForecastTab data={data} />
      ) : (
        <SetupTab data={data} canWrite={canWrite} onChanged={reload} />
      )}
    </div>
  );
}

/** "NDA", "MSA" or "NDA and MSA". */
function kindsText(kinds: readonly AgreementKind[]): string {
  return kinds.join(" and ");
}

/**
 * S24-AG1 F11 — the optional offer for a client created with this engagement. Opens the shared
 * upload dialog preset to the client (client fixed, client copy, the first kind not yet added).
 */
function AgreementsOfferNote({
  offer,
  canWrite,
  onUploaded,
  onDismiss,
}: {
  offer: AgreementsOffer;
  canWrite: boolean;
  onUploaded: (next: AgreementsOffer) => void;
  onDismiss: () => void;
}) {
  const [open, setOpen] = useState(false);
  const opener = useRef<HTMLButtonElement | null>(null);
  const dismiss = useRef<HTMLButtonElement | null>(null);
  const remaining = AGREEMENT_KINDS.filter((kind) => !offer.uploaded.includes(kind));
  const uploaded = AGREEMENT_KINDS.filter((kind) => offer.uploaded.includes(kind));

  function close() {
    setOpen(false);
    // Focus returns to the control that opened the dialog (or to Dismiss once nothing is left to add).
    window.setTimeout(() => (opener.current ?? dismiss.current)?.focus(), 0);
  }

  return (
    <div className="rounded-card border border-dashed border-primary bg-primary-subtle px-4 py-3 text-body" data-testid="agreements-offer">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium">
            New client: <span data-testid="agreements-offer-client">{offer.client_name}</span>
          </p>
          {uploaded.length > 0 ? (
            <p className="mt-1 text-secondary" role="status">
              {kindsText(uploaded)} uploaded.
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {remaining.length > 0 ? (
            <LockedButton ref={opener} size="sm" lock={canWrite ? null : "writer"} onClick={() => setOpen(true)}>
              {`Add the ${kindsText(remaining)} now (optional)`}
            </LockedButton>
          ) : null}
          <Button ref={dismiss} size="sm" variant="secondary" onClick={onDismiss}>
            Dismiss
          </Button>
        </div>
      </div>
      {canWrite && remaining.length > 0 ? (
        <UploadDialog
          open={open}
          target={{ mode: "client", clientId: offer.client_id, clientName: offer.client_name, kind: remaining[0], lockTarget: true }}
          canWrite={canWrite}
          onOpenChange={(next) => (next ? setOpen(true) : close())}
          onUploaded={(result) => {
            const kinds = new Set<AgreementKind>([...offer.uploaded, result.kind]);
            onUploaded({ ...offer, uploaded: AGREEMENT_KINDS.filter((kind) => kinds.has(kind)) });
            close();
          }}
        />
      ) : null}
    </div>
  );
}
