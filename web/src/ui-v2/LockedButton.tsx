// S24-AG1 F1/F12 · a write control the caller may not use stays visible and
// says why (the prototype's "locked with a reason, not hidden"). It is not
// `disabled` (that would drop it from the tab order and hide the reason): it is
// aria-disabled, keeps focus, explains itself on hover and focus, and a click
// shows the reason as a toast. The server still answers 403 regardless.
import { forwardRef, useId, type ComponentPropsWithoutRef, type ReactNode } from "react";

import { cn } from "../lib/cn";
import { Button } from "./primitives/button";
import { useToast } from "./primitives/toaster";
import { Tooltip, TooltipContent, TooltipTrigger } from "./primitives/tooltip";

export type LockReason = "writer" | "admin";

export const LOCK_TITLE: Record<LockReason, string> = {
  writer: "Only Legal and SystemAdmin can change agreements",
  admin: "Only SystemAdmin can do this",
};

export const LOCK_TOAST: Record<LockReason, string> = {
  writer: "Only Legal and SystemAdmin can change agreements. You can view and download.",
  admin: "Only SystemAdmin can do this.",
};

type ButtonProps = ComponentPropsWithoutRef<typeof Button>;

export interface LockedButtonProps extends ButtonProps {
  /** null/undefined = usable; otherwise the reason it is locked. */
  lock?: LockReason | null;
  /** Override the toast text shown when a locked button is pressed. */
  lockMessage?: string;
  children: ReactNode;
}

export const LockedButton = forwardRef<HTMLButtonElement, LockedButtonProps>(function LockedButton(
  { lock, lockMessage, children, className, onClick, ...rest },
  ref,
) {
  const { toast } = useToast();
  const reasonId = useId();
  if (!lock) {
    return (
      <Button ref={ref} className={className} onClick={onClick} {...rest}>
        {children}
      </Button>
    );
  }
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          ref={ref}
          {...rest}
          type="button"
          aria-disabled="true"
          aria-describedby={reasonId}
          data-locked={lock}
          className={cn("cursor-not-allowed opacity-70", className)}
          onClick={(event) => {
            event.preventDefault();
            toast({ title: lockMessage ?? LOCK_TOAST[lock] });
          }}
        >
          {children}
          <span id={reasonId} className="sr-only">
            {` (locked: ${LOCK_TITLE[lock]})`}
          </span>
        </Button>
      </TooltipTrigger>
      <TooltipContent>{LOCK_TITLE[lock]}</TooltipContent>
    </Tooltip>
  );
});
