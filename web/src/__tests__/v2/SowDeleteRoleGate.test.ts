/**
 * Rule 11 regression from the owner's click-through: the Delete SOW
 * control only renders for roles that can actually use it, mirroring
 * the server's governance-scoped delete roles.
 */
import { describe, expect, it } from "vitest";
import { SOW_DELETE_ROLES, canDeleteSow } from "../../pages/v2/SowWorkspace";

describe("canDeleteSow", () => {
  it("mirrors the server tuple exactly", () => {
    expect([...SOW_DELETE_ROLES]).toEqual([
      "SystemAdmin",
      "CEO",
      "SalesLeader",
      "Finance",
      "Legal",
    ]);
  });

  it("allows each governance role", () => {
    for (const role of SOW_DELETE_ROLES) {
      expect(canDeleteSow([role])).toBe(true);
    }
  });

  it("denies Delivery, HR, Sales and anonymous viewers", () => {
    expect(canDeleteSow(["Delivery"])).toBe(false);
    expect(canDeleteSow(["HR", "Sales"])).toBe(false);
    expect(canDeleteSow([])).toBe(false);
    expect(canDeleteSow(undefined)).toBe(false);
  });
});
