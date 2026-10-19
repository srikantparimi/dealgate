import { useEffect, useRef, type RefObject } from "react";

/**
 * Toasts are Radix dismissable layers too, and Radix gives Escape only to the newest layer. A toast raised
 * from inside an open dialog (a download, a mark, an upload) is that layer for its few seconds, so Escape would
 * dismiss the toast and leave the dialog the person is working in open (S24-AG1 T14, docs/bugs #109).
 *
 * While a toast that opened after this dialog is on screen and focus is inside the dialog, Escape is handed
 * back to the dialog: its own `onEscapeKeyDown` runs first (so busy and open-list guards still decide), and
 * unless that prevented it the dialog closes through its own close control, so its `onOpenChange` and focus
 * return behave exactly as for an ordinary Escape. The toast stays up for the rest of its time.
 */
export function useEscapeAboveToasts(
  contentRef: RefObject<HTMLElement | null>,
  closeRef: RefObject<HTMLButtonElement | null>,
  onEscapeKeyDown?: (event: KeyboardEvent) => void,
) {
  const openedAt = useRef(Date.now());
  const handler = useRef(onEscapeKeyDown);
  handler.current = onEscapeKeyDown;

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      const content = contentRef.current;
      if (
        !content ||
        !(event.target instanceof Node) ||
        !content.contains(event.target)
      )
        return;
      const toastAbove = Array.from(
        document.querySelectorAll<HTMLElement>(
          '[data-dg-toast][data-state="open"]',
        ),
      ).some((toast) => Number(toast.dataset.dgToastAt) >= openedAt.current);
      if (!toastAbove) return; // the dialog is the newest layer: Radix handles Escape itself
      handler.current?.(event);
      if (event.defaultPrevented) return;
      event.stopImmediatePropagation(); // the toast keeps its remaining time
      closeRef.current?.click();
    }
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [contentRef, closeRef]);
}
