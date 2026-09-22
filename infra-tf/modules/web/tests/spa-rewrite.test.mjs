import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";

const handler = runInNewContext(`${readFileSync(new URL("../spa-rewrite.js", import.meta.url), "utf8")}\nhandler;`);
for (const [method, uri, expected] of [
  ["GET", "/", "/index.html"],
  ["GET", "/sows/xyz", "/index.html"],
  ["HEAD", "/sows/xyz/", "/index.html"],
  ["GET", "/v1.0/settings", "/index.html"],
  ["GET", "/api", "/api"],
  ["GET", "/api/nonexistent", "/api/nonexistent"],
  ["GET", "/api/sows", "/api/sows"],
  ["GET", "/assets/missing", "/assets/missing"],
  ["GET", "/assets/app.js", "/assets/app.js"],
  ["GET", "/favicon.ico", "/favicon.ico"],
  ["OPTIONS", "/sows/xyz", "/sows/xyz"],
]) {
  test(`${method} ${uri} -> ${expected}`, () => {
    const request = { method, uri, querystring: { tab: { value: "gm" } }, headers: {} };
    assert.equal(handler({ request }), request);
    assert.equal(request.uri, expected);
    assert.equal(request.querystring.tab.value, "gm");
  });
}
