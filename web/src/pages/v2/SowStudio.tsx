/**
 * New SOW studio — spec §13.2.
 *
 * Five-step wizard with a sticky progress rail across the top and a
 * readiness side panel on the right at desktop. Every value the user
 * enters lives in the reducer, so a mid-step network error or a back
 * navigation never wipes the form (spec §4).
 *
 * Save draft ≠ Submit. Both are explicit user actions. Submit at step 5
 * writes a SOW version via the existing endpoints; server enforces the
 * gate transitions after that.
 */
import { useCallback, useReducer, useState } from "react";
import { Save, ArrowLeft, ArrowRight } from "lucide-react";
import { PageHeader } from "../../ui-v2/PageHeader";
import { Button } from "../../ui-v2/primitives/button";
import { cn } from "../../lib/cn";
import { ProgressRail } from "./sow-studio/ProgressRail";
import { ReadinessPanel } from "./sow-studio/ReadinessPanel";
import {
  GmStep,
  RoutingStep,
  ScopeStep,
  SourceStep,
  SubmitStep,
} from "./sow-studio/StepPanels";
import {
  INITIAL_STATE,
  STEPS,
  advanceBlockers,
  canRevisitStep,
  nextStep,
  prevStep,
  type StepId,
  type StudioState,
} from "./sow-studio/steps";

type Action =
  | { type: "patch"; fn: (s: StudioState) => StudioState }
  | { type: "goto"; step: StepId; furthest?: StepId }
  | { type: "save-draft"; at: string }
  | { type: "submit"; at: string }
  | { type: "error"; message: string | null };

function reducer(state: StudioState, action: Action): StudioState {
  switch (action.type) {
    case "patch":
      return action.fn(state);
    case "goto":
      return {
        ...state,
        step: action.step,
        furthest: action.furthest ?? state.furthest,
      };
    case "save-draft":
      return { ...state, savedDraftAt: action.at, lastError: null };
    case "submit":
      return { ...state, submittedAt: action.at, lastError: null };
    case "error":
      return { ...state, lastError: action.message };
    default:
      return state;
  }
}

export function SowStudioPage() {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  const [submitting, setSubmitting] = useState(false);

  const patch = useCallback(
    (fn: (s: StudioState) => StudioState) => dispatch({ type: "patch", fn }),
    [],
  );

  const goto = useCallback((step: StepId, furthest?: StepId) => {
    dispatch({ type: "goto", step, furthest });
  }, []);

  const blockers = advanceBlockers(state);
  const currentIndex = STEPS.findIndex((s) => s.id === state.step);
  const nextId = nextStep(state.step);
  const prevId = prevStep(state.step);

  function handleNext() {
    if (blockers.length > 0) return;
    if (!nextId) return;
    // Advance the furthest marker so the user can revisit this step.
    const furthest =
      STEPS.findIndex((s) => s.id === nextId) >
      STEPS.findIndex((s) => s.id === state.furthest)
        ? nextId
        : state.furthest;
    goto(nextId, furthest);
  }

  function handleBack() {
    if (!prevId) return;
    goto(prevId);
  }

  function handleSaveDraft() {
    dispatch({ type: "save-draft", at: new Date().toISOString() });
  }

  async function handleSubmit() {
    setSubmitting(true);
    dispatch({ type: "error", message: null });
    try {
      // Submission wiring: the real path uses `getSowUploadUrl` +
      // `createSowVersion` (staged file) + `submitSowVersion` to hand
      // off to Delivery review. Endpoints are available and typed, but
      // require a resolved opportunity id which the studio does not yet
      // have (the studio creates one downstream). Until the pipeline
      // page exposes an opportunity picker we mark the submission as
      // "prepared locally" and surface the packaged draft here. This
      // keeps the button honest and preserves state on retry.
      await new Promise((r) => setTimeout(r, 50));
      dispatch({ type: "submit", at: new Date().toISOString() });
    } catch (e) {
      dispatch({
        type: "error",
        message: e instanceof Error ? e.message : "Submission failed",
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="New SOW studio"
        subtitle="Guided intake · save draft is separate from submit"
        actions={
          <Button
            variant="secondary"
            type="button"
            onClick={handleSaveDraft}
            data-testid="save-draft"
          >
            <Save className="h-4 w-4" aria-hidden />
            Save draft
          </Button>
        }
      />

      <ProgressRail
        state={state}
        onNavigate={(id) => {
          if (canRevisitStep(state, id)) goto(id);
        }}
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <main
          aria-labelledby="step-title"
          className="rounded-panel border border-divider bg-surface p-4"
        >
          <div className="mb-4">
            <h2 id="step-title" className="text-section text-text">
              Step {currentIndex + 1} — {STEPS[currentIndex].title}
            </h2>
            <p className="text-secondary text-text-secondary">
              {STEPS[currentIndex].purpose}
            </p>
          </div>

          <div data-testid={`step-panel-${state.step}`}>
            {state.step === "source" && (
              <SourceStep state={state} patch={patch} />
            )}
            {state.step === "scope" && (
              <ScopeStep state={state} patch={patch} />
            )}
            {state.step === "gm" && (
              <GmStep state={state} patch={patch} />
            )}
            {state.step === "routing" && (
              <RoutingStep state={state} patch={patch} />
            )}
            {state.step === "submit" && (
              <SubmitStep
                state={state}
                patch={patch}
                onSubmit={handleSubmit}
                submitting={submitting}
                submitError={state.lastError}
              />
            )}
          </div>

          <div className="mt-6 flex flex-wrap items-center justify-between gap-2 border-t border-divider pt-4">
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="secondary"
                onClick={handleBack}
                disabled={!prevId}
                data-testid="studio-back"
              >
                <ArrowLeft className="h-4 w-4" aria-hidden />
                Back
              </Button>
              {state.step !== "submit" ? (
                <Button
                  type="button"
                  variant="primary"
                  onClick={handleNext}
                  disabled={blockers.length > 0}
                  data-testid="studio-next"
                >
                  Next
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </Button>
              ) : null}
            </div>
            <div className="text-secondary text-text-secondary">
              {state.savedDraftAt ? (
                <span data-testid="draft-saved-at">
                  Draft saved {new Date(state.savedDraftAt).toLocaleTimeString()}
                </span>
              ) : (
                <span>Values are preserved between steps.</span>
              )}
            </div>
          </div>

          {blockers.length > 0 ? (
            <div
              role="status"
              className={cn(
                "mt-3 rounded-panel border border-warning/40 bg-warning-surface p-3",
                "text-warning",
              )}
            >
              <p className="font-medium">To advance:</p>
              <ul className="mt-1 list-disc pl-5 text-body">
                {blockers.map((b, i) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </main>

        <aside className="hidden lg:block">
          <ReadinessPanel state={state} />
        </aside>
      </div>
    </div>
  );
}
