import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

export type InputProps = InputHTMLAttributes<HTMLInputElement>;

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, type = "text", ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        "flex h-10 w-full rounded-control border border-input-border",
        "bg-surface px-3 text-body text-text",
        "placeholder:text-text-secondary",
        "disabled:cursor-not-allowed disabled:opacity-60",
        "focus-visible:outline-focus",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
