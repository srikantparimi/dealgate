import { mock } from "node:test";
import { expect, request, test, type APIRequestContext } from "@playwright/test";
import { apiFetch } from "../fixtures/api";

test.afterEach(() => mock.restoreAll());

function respond(status: number, contentType: string | undefined, body: string) {
  let disposed = false;
  mock.method(request, "newContext", async () => ({
    fetch: async () => ({
      status: () => status,
      ok: () => status >= 200 && status < 300,
      headers: () => contentType === undefined ? {} : { "content-type": contentType },
      text: async () => body,
    }),
    dispose: async () => { disposed = true; },
  }) as unknown as APIRequestContext);
  return () => disposed;
}

test("accepts JSON media types with parameters", async () => {
  const disposed = respond(200, "Application/JSON; charset=utf-8", '{"ok":true}');
  expect((await apiFetch("Sales", "GET", "/sows")).json).toEqual({ ok: true });
  expect(disposed()).toBe(true);
});

for (const status of [200, 401, 404, 500]) {
  test(`rejects HTML at status ${status} even when non-2xx is allowed`, async () => {
    const disposed = respond(status, "text/html", "<!doctype html><html>SPA</html>");
    await expect(apiFetch("Sales", "GET", "/sows", undefined, { allowNon2xx: true }))
      .rejects.toThrow(`apiFetch GET /sows -> ${status}: expected application/json, got text/html`);
    expect(disposed()).toBe(true);
  });
}

for (const contentType of [undefined, "text/plain", "application/jsonp"]) {
  test(`rejects JSON bodies labeled ${contentType ?? "no content-type"}`, async () => {
    respond(200, contentType, '{"ok":true}');
    await expect(apiFetch("Sales", "GET", "/sows"))
      .rejects.toThrow("expected application/json");
  });
}

test("preserves explicitly allowed JSON errors", async () => {
  respond(401, "application/json", '{"detail":"Unauthorized"}');
  expect(await apiFetch("Sales", "GET", "/sows", undefined, { allowNon2xx: true }))
    .toMatchObject({ status: 401, ok: false, json: { detail: "Unauthorized" } });
});

test("still rejects unexpected JSON error statuses", async () => {
  respond(404, "application/json", '{"detail":"Not Found"}');
  await expect(apiFetch("Sales", "GET", "/sows"))
    .rejects.toThrow('apiFetch GET /sows -> 404: {"detail":"Not Found"}');
});

for (const body of ["", "<html>mislabeled</html>"]) {
  test(`rejects invalid JSON with body ${JSON.stringify(body)}`, async () => {
    respond(200, "application/json", body);
    await expect(apiFetch("Sales", "GET", "/sows"))
      .rejects.toThrow("invalid JSON response");
  });
}

for (const status of [204, 205]) {
  test(`accepts empty ${status} without a content-type`, async () => {
    respond(status, undefined, "");
    expect(await apiFetch("SystemAdmin", "DELETE", "/capabilities/id"))
      .toMatchObject({ status, ok: true, json: null, text: "" });
  });

  for (const body of ["", "<html>SPA</html>"]) {
    test(`rejects HTML content-type on ${status} with body ${JSON.stringify(body)}`, async () => {
      respond(status, "text/html", body);
      await expect(apiFetch("SystemAdmin", "DELETE", "/capabilities/id"))
        .rejects.toThrow("expected application/json");
    });
  }
}
