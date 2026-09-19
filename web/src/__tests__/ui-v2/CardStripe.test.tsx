/**
 * CardStripe — v2.1 spec `elevation.stripe`.
 */
import { describe, expect, it } from "vitest";
import { cardStripeClass } from "../../ui-v2/CardStripe";

describe("cardStripeClass", () => {
  it("returns the danger stripe for blocked cards", () => {
    expect(cardStripeClass("blocked")).toContain("border-l-danger");
  });

  it("returns the warning stripe for at-risk cards", () => {
    expect(cardStripeClass("at-risk")).toContain("border-l-warning");
  });

  it("returns the primary stripe for in-progress cards", () => {
    expect(cardStripeClass("in-progress")).toContain("border-l-primary");
  });

  it("returns an empty string when no variant is supplied", () => {
    expect(cardStripeClass(null)).toBe("");
    expect(cardStripeClass(undefined)).toBe("");
  });
});
