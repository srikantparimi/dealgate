import { forwardRef, type LabelHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

export type LabelProps = LabelHTMLAttributes<HTMLLabelElement>;

export const Label = forwardRef<HTMLLabelElement, LabelProps>(
  ({ className, ...props }, ref) => (
    <label
      ref={ref}
      className={cn(
        "text-secondary font-medium text-text-secondary",
        className,
      )}
      {...props}
    />
  ),
);
Label.displayName = "Label";
