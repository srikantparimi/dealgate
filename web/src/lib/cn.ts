import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// The theme's own font sizes (tailwind.config.ts `fontSize`). Without them
// tailwind-merge reads `text-metric` as a text colour and drops it when a
// colour class such as `text-text-secondary` follows (S23-PL2).
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [
        {
          text: [
            "bannerHeadline", "pageHeading", "metric", "section", "body", "table", "secondary", "label", "page", "page-mobile",
          ],
        },
      ],
    },
  },
});

/**
 * Compose Tailwind class names, resolving conflicts (later wins).
 *
 * Standard shadcn helper — use this in every V2 primitive so a caller can
 * pass an override className without having to fight the built-in defaults.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
