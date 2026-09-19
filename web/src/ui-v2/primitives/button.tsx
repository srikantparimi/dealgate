import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

/**
 * Button primitive.
 *
 * Variants map to spec §2:
 * - primary: filled violet — one per page/decision region
 * - secondary: outlined
 * - tertiary: text
 * - destructive: filled danger — always paired with an explicit verb
 * - ghost: transparent, for icon-only header/nav actions
 * - hero: the executive banner lime accent — reserved for one action
 */
export const buttonVariants = cva(
  cn(
    "inline-flex items-center justify-center gap-2 rounded-control",
    "font-medium text-body whitespace-nowrap",
    "transition-motion",
    "disabled:pointer-events-none disabled:opacity-60",
    "focus-visible:outline-focus",
  ),
  {
    variants: {
      variant: {
        primary: "bg-primary text-primary-fg hover:opacity-95",
        secondary:
          "bg-surface text-text border border-input-border hover:bg-primary-subtle",
        tertiary: "bg-transparent text-primary hover:bg-primary-subtle",
        destructive: "bg-danger text-white hover:opacity-95",
        ghost: "bg-transparent text-text hover:bg-primary-subtle",
        hero: "bg-hero text-hero-fg hover:opacity-95",
      },
      size: {
        sm: "h-8 px-3 text-secondary",
        md: "h-10 min-w-[44px] px-4",
        lg: "h-12 px-5 text-section",
        icon: "h-10 w-10 p-0",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, type, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        type={asChild ? undefined : (type ?? "button")}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";
