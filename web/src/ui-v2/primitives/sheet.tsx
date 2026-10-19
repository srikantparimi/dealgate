import * as DialogPrimitive from "@radix-ui/react-dialog";
import { cva, type VariantProps } from "class-variance-authority";
import { X } from "lucide-react";
import {
  forwardRef,
  useRef,
  type ComponentPropsWithoutRef,
  type ElementRef,
  type HTMLAttributes,
} from "react";
import { cn } from "../../lib/cn";
import { useEscapeAboveToasts } from "./escapeAboveToasts";

/**
 * Right-side drawer built on Radix Dialog. Used for quick task editing,
 * next steps, contacts, filters, notifications and resource rows (spec §4).
 */
export const Sheet = DialogPrimitive.Root;
export const SheetTrigger = DialogPrimitive.Trigger;
export const SheetClose = DialogPrimitive.Close;

export const SheetOverlay = forwardRef<
  ElementRef<typeof DialogPrimitive.Overlay>,
  ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn("fixed inset-0 z-50 bg-executive opacity-50", className)}
    {...props}
  />
));
SheetOverlay.displayName = "SheetOverlay";

const sheetVariants = cva(
  cn(
    "fixed z-50 gap-4 bg-surface p-6 shadow-dialog transition-motion",
    "text-text focus:outline-none",
  ),
  {
    variants: {
      side: {
        right: "inset-y-0 right-0 h-full w-full sm:max-w-md border-l border-divider",
        left: "inset-y-0 left-0 h-full w-full sm:max-w-md border-r border-divider",
        top: "inset-x-0 top-0 border-b border-divider",
        bottom: "inset-x-0 bottom-0 border-t border-divider",
      },
    },
    defaultVariants: { side: "right" },
  },
);

export interface SheetContentProps
  extends ComponentPropsWithoutRef<typeof DialogPrimitive.Content>,
    VariantProps<typeof sheetVariants> {}

export const SheetContent = forwardRef<
  ElementRef<typeof DialogPrimitive.Content>,
  SheetContentProps
>(({ side = "right", className, children, onEscapeKeyDown, ...props }, ref) => {
  const contentRef = useRef<HTMLDivElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);
  useEscapeAboveToasts(contentRef, closeRef, onEscapeKeyDown);
  return (
    <DialogPrimitive.Portal>
      <SheetOverlay />
      <DialogPrimitive.Content
        ref={(node) => {
          contentRef.current = node;
          if (typeof ref === "function") ref(node);
          else if (ref) ref.current = node;
        }}
        className={cn(sheetVariants({ side }), className)}
        onEscapeKeyDown={onEscapeKeyDown}
        {...props}
      >
        {children}
        <DialogPrimitive.Close
          ref={closeRef}
          className={cn(
            "absolute right-4 top-4 rounded-control p-1 text-text-secondary",
            "hover:bg-primary-subtle focus-visible:outline-focus transition-motion",
          )}
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
});
SheetContent.displayName = "SheetContent";

export function SheetHeader({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-1", className)} {...props} />;
}

export const SheetTitle = forwardRef<
  ElementRef<typeof DialogPrimitive.Title>,
  ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn("text-section text-text", className)}
    {...props}
  />
));
SheetTitle.displayName = "SheetTitle";

export const SheetDescription = forwardRef<
  ElementRef<typeof DialogPrimitive.Description>,
  ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn("text-secondary text-text-secondary", className)}
    {...props}
  />
));
SheetDescription.displayName = "SheetDescription";
