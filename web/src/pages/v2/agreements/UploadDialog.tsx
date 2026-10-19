// S24-AG1 F2 · the upload dialog (props fixed for the page shell, the client strip and F11), and the
// right-drawer shell every FE-B dialog opens in. The prototype opens everything in one right drawer with
// a kicker over the title; the kit's Sheet (Radix) gives the focus trap, Escape and an inert page
// behind it. Every dialog here is opened programmatically, so the drawer itself puts focus back on the
// control that opened it.
import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
  type Ref,
} from "react";

import type { AgreementKind } from "../../../api/agreements";
import type { UUID } from "../../../api/client";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "../../../ui-v2/primitives/sheet";
import { UploadForm } from "./UploadForm";

export interface UploadTarget {
  /** "client": a client copy for one client; "standard": the next standard version. */
  mode: "client" | "standard";
  clientId?: UUID | null;
  clientName?: string | null;
  kind?: AgreementKind;
  /** The client and the "What is this?" choice are fixed (opened from a client panel or row). */
  lockTarget?: boolean;
  /** Opened from the attach wizard's step 1: shows "Back to attach" and returns there afterwards. */
  fromWizard?: boolean;
}

export interface UploadResult {
  mode: "client" | "standard";
  kind: AgreementKind;
  clientId?: UUID | null;
}

export interface UploadDialogProps {
  open: boolean;
  target: UploadTarget | null;
  /** Legal or SystemAdmin. A non-writer never sees the form (the opener is locked). */
  canWrite: boolean;
  onOpenChange: (open: boolean) => void;
  onUploaded: (result: UploadResult) => void;
  onBackToWizard?: () => void;
}

// --- shared drawer pieces -----------------------------------------------------------------------

/**
 * Remembers the element that had focus when `open` turned true and returns a Radix
 * `onCloseAutoFocus` handler that puts focus back there (or on `fallback()` when that element is
 * gone, e.g. a button that a change replaced).
 */
export function useReturnFocus(open: boolean, fallback?: () => HTMLElement | null) {
  const opener = useRef<HTMLElement | null>(null);
  const fallbackRef = useRef(fallback);
  fallbackRef.current = fallback;
  useLayoutEffect(() => {
    if (!open) return;
    const active = document.activeElement;
    opener.current = active instanceof HTMLElement && active !== document.body ? active : null;
  }, [open]);
  return useCallback((event: Event) => {
    event.preventDefault();
    const target = opener.current;
    opener.current = null;
    if (target?.isConnected) {
      target.focus();
      return;
    }
    fallbackRef.current?.()?.focus();
  }, []);
}

/**
 * A number that changes each time `open` turns true. Key a dialog body on it so every opening
 * starts clean, while a closing dialog keeps its state until the drawer has animated out.
 */
export function useOpenSession(open: boolean): number {
  const [state, setState] = useState({ open, session: open ? 1 : 0 });
  if (open !== state.open) {
    const next = { open, session: open ? state.session + 1 : state.session };
    setState(next);
    return next.session;
  }
  return state.session;
}

function isExpandedCombobox(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    target.getAttribute("role") === "combobox" &&
    target.getAttribute("aria-expanded") === "true"
  );
}

export interface AgreementsDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kicker: string;
  title: string;
  /** While true (an upload in flight) Escape, an outside click and the close button do nothing. */
  busy?: boolean;
  /** Focus target when the opener no longer exists on close. */
  fallbackFocus?: () => HTMLElement | null;
  titleRef?: Ref<HTMLHeadingElement>;
  children: ReactNode;
}

/** The right drawer every Agreements dialog opens in (prototype: one drawer, kicker over the title). */
export function AgreementsDrawer({
  open,
  onOpenChange,
  kicker,
  title,
  busy = false,
  fallbackFocus,
  titleRef,
  children,
}: AgreementsDrawerProps) {
  const returnFocus = useReturnFocus(open, fallbackFocus);
  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next && busy) return;
        onOpenChange(next);
      }}
    >
      <SheetContent
        side="right"
        aria-describedby={undefined}
        className="flex w-full flex-col gap-5 overflow-y-auto sm:max-w-[600px]"
        onCloseAutoFocus={returnFocus}
        onEscapeKeyDown={(event) => {
          // An open client list closes first; an upload in flight keeps the drawer open.
          if (busy || isExpandedCombobox(event.target)) event.preventDefault();
        }}
        onInteractOutside={(event) => {
          if (busy) event.preventDefault();
        }}
      >
        <SheetHeader className="pr-10">
          <p className="font-mono text-label uppercase text-primary-text">{kicker}</p>
          <SheetTitle ref={titleRef} tabIndex={-1}>
            {/* The size sits on the inner span: the kit's cn() would merge it away against text-text. */}
            <span className="block break-words text-pageHeading text-text [overflow-wrap:anywhere]">{title}</span>
          </SheetTitle>
        </SheetHeader>
        {children}
      </SheetContent>
    </Sheet>
  );
}

// --- the dialog ----------------------------------------------------------------------------------

/** "Upload document", a standard panel's upload, a row's "↑ Upload client copy", the client strip and F11. */
export function UploadDialog(props: UploadDialogProps) {
  const session = useOpenSession(props.open);
  return <UploadDialogSession key={session} {...props} />;
}

function UploadDialogSession({ open, target, canWrite, onOpenChange, onUploaded, onBackToWizard }: UploadDialogProps) {
  // Each opening is its own session: the target it opened with holds until it closes (an opener may
  // clear `target` as soon as it starts closing).
  const [start] = useState<UploadTarget>(() => target ?? { mode: "client" });
  const [busy, setBusy] = useState(false);
  const [selection, setSelection] = useState<{ mode: "client" | "standard"; kind: AgreementKind }>({
    mode: start.mode,
    kind: start.kind ?? "NDA",
  });
  const onSelectionChange = useCallback(
    (mode: "client" | "standard", kind: AgreementKind) => setSelection({ mode, kind }),
    [],
  );
  const toWizard = Boolean(start.fromWizard && onBackToWizard);
  const standard = selection.mode === "standard";

  return (
    <AgreementsDrawer
      open={open}
      onOpenChange={onOpenChange}
      kicker={standard ? "Standard copy" : "Upload"}
      title={standard ? `Upload standard ${selection.kind}` : "Upload a document"}
      busy={busy}
    >
      <UploadForm
        target={start}
        canWrite={canWrite}
        cancelLabel={toWizard ? "Back to attach" : "Cancel"}
        onCancel={() => (toWizard ? onBackToWizard!() : onOpenChange(false))}
        onUploaded={(result) => {
          onUploaded(result);
          if (toWizard) onBackToWizard!();
          else onOpenChange(false);
        }}
        onBusyChange={setBusy}
        onSelectionChange={onSelectionChange}
      />
    </AgreementsDrawer>
  );
}
