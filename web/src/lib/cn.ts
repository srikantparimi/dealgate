import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Compose Tailwind class names, resolving conflicts (later wins).
 *
 * Standard shadcn helper — use this in every V2 primitive so a caller can
 * pass an override className without having to fight the built-in defaults.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
