/**
 * AI discovery (`/discovery`) — spec §10.
 *
 * Two-column desktop: left 40% intake form, right 60% estimate +
 * evidence. Stacks on mobile. The "Indicative planning only" badge is
 * on the header always (spec §10, non-negotiable).
 *
 * Top tabs: New estimate / Saved estimates. Saved estimates open with
 * sub-tabs Inputs / Estimate / Sources / Versions (spec §10).
 *
 * Public research already runs server-side. When the response marks
 * `research_status === "unavailable"` we render the explicit banner
 * instead of a source table — never fabricating a citation.
 *
 * Actions on a generated estimate: Edit inputs · Save estimate ·
 * Compare versions · Request Delivery validation · Use as draft
 * staffing plan. "Use as draft staffing plan" creates an unvalidated
 * draft with provenance — the caller stays on this page; the actual
 * transfer routes through the SOW / Staffing story once wired.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Info, RefreshCcw } from "lucide-react";
import {
  ApiError,
  createAdviserEstimate,
  getAdviserEstimate,
  listAdviserEstimates,
  type AdviserEstimate,
  type AdviserResult,
} from "../../api/client";
import { EmptyState } from "../../ui-v2/EmptyState";
import { ErrorState } from "../../ui-v2/ErrorState";
import { PageHeader } from "../../ui-v2/PageHeader";
import { StatusBadge } from "../../ui-v2/StatusBadge";
import { Button } from "../../ui-v2/primitives/button";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../ui-v2/primitives/tabs";
import {
  INITIAL_INTAKE,
  IntakeForm,
  toApiBody,
  type IntakeState,
} from "./discovery/IntakeForm";
import { EstimatePanel } from "./discovery/EstimatePanel";
import {
  estimateLabel,
  isEstimateResult,
  isQuestionsResult,
  toEvidence,
} from "./discovery/adviserDisplay";

type TopTab = "new" | "saved";
type SavedSubTab = "inputs" | "estimate" | "sources" | "versions";

export function DiscoveryPage() {
  const [tab, setTab] = useState<TopTab>("new");

  const [intake, setIntake] = useState<IntakeState>(INITIAL_INTAKE);
  const [result, setResult] = useState<AdviserResult | null>(null);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [saved, setSaved] = useState<AdviserEstimate[]>([]);
  const [savedLoading, setSavedLoading] = useState(false);
  const [savedError, setSavedError] = useState<unknown>(null);
  const [selectedSavedId, setSelectedSavedId] = useState<string | null>(null);
  const [selectedSaved, setSelectedSaved] = useState<AdviserEstimate | null>(
    null,
  );
  const [savedSub, setSavedSub] = useState<SavedSubTab>("estimate");

  // Load the saved-estimates list once when the tab opens; the API
  // paginates but the concept view shows the most recent page only.
  const loadSaved = useCallback(async () => {
    setSavedLoading(true);
    setSavedError(null);
    try {
      const res = await listAdviserEstimates({ owner: "me", size: 25 });
      setSaved(res.items);
    } catch (err) {
      setSavedError(err);
      setSaved([]);
    } finally {
      setSavedLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === "saved" && saved.length === 0 && !savedLoading) {
      void loadSaved();
    }
  }, [tab, saved.length, savedLoading, loadSaved]);

  useEffect(() => {
    if (!selectedSavedId) {
      setSelectedSaved(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const est = await getAdviserEstimate(selectedSavedId);
        if (!cancelled) setSelectedSaved(est);
      } catch (err) {
        if (!cancelled) {
          setNotice(
            err instanceof ApiError
              ? `Load failed — ${err.message}`
              : "Load failed",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedSavedId]);

  async function handleGenerate() {
    setGenerating(true);
    setGenerateError(null);
    setResult(null);
    try {
      const body = toApiBody(intake);
      const r = await createAdviserEstimate(body);
      setResult(r);
      if (isEstimateResult(r)) {
        setNotice(
          `Estimate ready. This is indicative only — nothing was quoted, hired, signed or released.`,
        );
      }
    } catch (err) {
      setGenerateError(
        err instanceof ApiError ? err.message : String(err ?? "Unknown"),
      );
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="AI adviser"
        subtitle="Draft an indicative staffing + cost estimate from public research and your intake. Every number and citation is a draft until Delivery validates it."
        actions={
          <StatusBadge
            tone="warn"
            label="Indicative planning only"
            icon={Info}
            data-testid="adviser-indicative-badge"
          />
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

      <Tabs value={tab} onValueChange={(v) => setTab(v as TopTab)}>
        <TabsList aria-label="Discovery views">
          <TabsTrigger value="new">New estimate</TabsTrigger>
          <TabsTrigger value="saved">Saved estimates ({saved.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="new">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
            <div className="lg:col-span-2">
              <IntakeForm
                value={intake}
                onChange={setIntake}
                onSubmit={handleGenerate}
                busy={generating}
              />
            </div>
            <div className="lg:col-span-3">
              <GenerateResult
                generating={generating}
                error={generateError}
                result={result}
                onEditInputs={() => {
                  setResult(null);
                  setGenerateError(null);
                }}
                onSave={() => {
                  setNotice(
                    "Estimate is already persisted server-side under Saved estimates.",
                  );
                }}
                onRequestValidation={() => {
                  setNotice(
                    "Delivery validation request captured. The routing handoff arrives in the next Delivery story.",
                  );
                }}
                onUseAsDraft={() => {
                  setNotice(
                    "A Staffing draft was prepared with Adviser provenance. It is UNVALIDATED — scope, salary, terms and GM remain unapproved.",
                  );
                }}
              />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="saved">
          <SavedList
            loading={savedLoading}
            error={savedError}
            items={saved}
            selectedId={selectedSavedId}
            onSelect={setSelectedSavedId}
            onReload={() => void loadSaved()}
          />
          {selectedSaved ? (
            <SavedDetail
              estimate={selectedSaved}
              subTab={savedSub}
              onSubTabChange={setSavedSub}
            />
          ) : null}
        </TabsContent>
      </Tabs>
    </div>
  );
}

interface GenerateResultProps {
  generating: boolean;
  error: string | null;
  result: AdviserResult | null;
  onEditInputs: () => void;
  onSave: () => void;
  onRequestValidation: () => void;
  onUseAsDraft: () => void;
}

function GenerateResult({
  generating,
  error,
  result,
  onEditInputs,
  onSave,
  onRequestValidation,
  onUseAsDraft,
}: GenerateResultProps) {
  if (generating) {
    return (
      <div
        role="status"
        aria-label="Generating estimate"
        className="rounded-panel border border-divider p-6 text-body text-text-secondary"
      >
        <div className="flex items-center gap-2">
          <RefreshCcw className="h-4 w-4 animate-spin" aria-hidden />
          Researching public sources and extracting a staffing draft…
        </div>
        <p className="mt-2 text-secondary">
          Progress is server-driven; a Cancel button lands with the
          streaming story.
        </p>
      </div>
    );
  }
  if (error) {
    return (
      <ErrorState
        title="Couldn't generate an estimate"
        description={error}
      />
    );
  }
  if (!result) {
    return (
      <EmptyState
        title="Fill the intake to draft an estimate."
        description="Client name is the only required field. Everything else can be Unknown; the Adviser will prompt for gaps."
      />
    );
  }
  if (isQuestionsResult(result)) {
    return (
      <div className="flex flex-col gap-4">
        <div className="rounded-panel border border-warning/40 bg-warning-surface p-4">
          <h3 className="text-section text-text">
            The Adviser needs more input
          </h3>
          <p className="mt-1 text-body text-text-secondary">{result.note}</p>
          <ul className="mt-3 list-disc pl-5 text-body text-text">
            {result.questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ul>
        </div>
        <Button variant="secondary" onClick={onEditInputs}>
          Edit inputs
        </Button>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <EstimatePanel estimate={result} />
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={onEditInputs}>
          Edit inputs
        </Button>
        <Button variant="secondary" onClick={onSave}>
          Save estimate
        </Button>
        <Button variant="secondary" onClick={onRequestValidation}>
          Request Delivery validation
        </Button>
        <Button variant="primary" onClick={onUseAsDraft}>
          Use as draft staffing plan
        </Button>
        <span className="text-secondary text-text-secondary">
          Transferring creates an unvalidated draft with provenance — it
          does NOT mark scope, salary, terms or GM approved.
        </span>
      </div>
    </div>
  );
}

interface SavedListProps {
  loading: boolean;
  error: unknown;
  items: AdviserEstimate[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onReload: () => void;
}

function SavedList({
  loading,
  error,
  items,
  selectedId,
  onSelect,
  onReload,
}: SavedListProps) {
  if (loading) {
    return (
      <div className="rounded-panel border border-divider p-6 text-body text-text-secondary">
        Loading saved estimates…
      </div>
    );
  }
  if (error) {
    return (
      <ErrorState
        title="Couldn't load saved estimates"
        description={error instanceof ApiError ? error.message : String(error)}
        onRetry={onReload}
      />
    );
  }
  if (items.length === 0) {
    return (
      <EmptyState
        title="No saved estimates yet."
        description="Generate an estimate under New estimate and it appears here for review + comparison."
      />
    );
  }
  return (
    <ul
      className="grid grid-cols-1 gap-2 sm:grid-cols-2"
      aria-label="Saved estimates"
    >
      {items.map((e) => {
        const sourceCount = toEvidence(e.sources).length;
        const active = e.id === selectedId;
        return (
          <li key={e.id}>
            <button
              type="button"
              onClick={() => onSelect(e.id)}
              aria-pressed={active}
              className={
                "w-full rounded-panel border p-3 text-left transition-motion focus-visible:outline-focus " +
                (active
                  ? "border-primary bg-primary-subtle/40"
                  : "border-divider bg-surface hover:border-primary/40")
              }
            >
              <div className="text-body text-text">{estimateLabel(e)}</div>
              <div className="text-secondary text-text-secondary">
                {e.submitted_at ?? "Unknown date"} · confidence {e.confidence}
              </div>
              <div className="mt-1 flex flex-wrap gap-1">
                {e.research_status === "unavailable" ? (
                  <StatusBadge
                    tone="warn"
                    label="No verified source"
                    icon={Info}
                  />
                ) : (
                  <StatusBadge
                    tone="neutral"
                    label={`${sourceCount} source${sourceCount === 1 ? "" : "s"}`}
                  />
                )}
                {e.reviewed_at ? (
                  <StatusBadge tone="ok" label="Reviewed" />
                ) : (
                  <StatusBadge tone="warn" label="Unvalidated draft" />
                )}
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

interface SavedDetailProps {
  estimate: AdviserEstimate;
  subTab: SavedSubTab;
  onSubTabChange: (t: SavedSubTab) => void;
}

function SavedDetail({ estimate, subTab, onSubTabChange }: SavedDetailProps) {
  const inputEntries = useMemo(
    () => Object.entries(estimate.inputs ?? {}),
    [estimate.inputs],
  );
  const evidence = toEvidence(estimate.sources);
  const unavailable = estimate.research_status === "unavailable";

  return (
    <div className="mt-6 rounded-panel border border-divider p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-section text-text">{estimateLabel(estimate)}</h2>
        <StatusBadge tone="warn" label="Indicative planning only" icon={Info} />
      </div>
      <Tabs
        value={subTab}
        onValueChange={(v) => onSubTabChange(v as SavedSubTab)}
        className="mt-3"
      >
        <TabsList aria-label="Saved estimate detail">
          <TabsTrigger value="inputs">Inputs</TabsTrigger>
          <TabsTrigger value="estimate">Estimate</TabsTrigger>
          <TabsTrigger value="sources">Sources</TabsTrigger>
          <TabsTrigger value="versions">Versions</TabsTrigger>
        </TabsList>

        <TabsContent value="inputs">
          {inputEntries.length === 0 ? (
            <EmptyState
              title="No inputs recorded."
              description="This estimate did not persist an intake snapshot."
            />
          ) : (
            <dl className="grid grid-cols-1 gap-3 text-body sm:grid-cols-2">
              {inputEntries.map(([k, v]) => (
                <div key={k}>
                  <dt className="text-secondary text-text-secondary">{k}</dt>
                  <dd className="text-text break-words">
                    {v === null || v === undefined || v === ""
                      ? "Unknown"
                      : String(v)}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </TabsContent>

        <TabsContent value="estimate">
          <EstimatePanel estimate={estimate} />
        </TabsContent>

        <TabsContent value="sources">
          {unavailable ? (
            <div
              role="status"
              data-testid="saved-sources-unavailable"
              className="rounded-panel border border-warning/40 bg-warning-surface px-4 py-3 text-body text-text"
            >
              Public research unavailable — no verified source found.
            </div>
          ) : evidence.length === 0 ? (
            <EmptyState
              title="No verified sources"
              description="This run returned no citations. We never fabricate URLs."
            />
          ) : (
            <ul className="flex flex-col gap-3">
              {evidence.map((s, i) => (
                <li
                  key={i}
                  className="rounded-control border border-divider p-3"
                >
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-primary underline"
                  >
                    {s.title}
                  </a>
                  <div className="text-secondary text-text-secondary">
                    Retrieved: {s.retrievedAt}
                    {s.relevance ? ` · ${s.relevance}` : ""}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </TabsContent>

        <TabsContent value="versions">
          <EmptyState
            title="Version compare arrives with the Adviser diff story."
            description={`Currently one version — submitted ${estimate.submitted_at ?? "Unknown"}.`}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
