/**
 * Settings → Cost bands (S9 wave 1).
 *
 * Rename-only alias for the previous "Rate cards" section, which is now
 * exclusively the HR cost-band view per docs/sow-first-principles.md.
 * The three-way split — Client cards / Cost bands / Margin policy —
 * ships in the top-level Settings nav; the sub-page keeps its existing
 * Current/Scheduled/Archived tabs, unchanged.
 *
 * Kept as a thin re-export so downstream imports and existing tests
 * don't churn while the wider rename is in flight.
 */

export { RateCardsSection as CostBandsSection } from "./RateCardsSection";
