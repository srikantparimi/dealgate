# S13 — CloudFront custom-error responses masked real API failures

Promoted to [S14a](../directives/s14a-cloudfront.md); see the
[implementation and verification report](../reports/s14a.md).
The implementation uses a viewer-request SPA rewrite, not the historical
origin-error function proposal below.

## Why

Product owner instruction, 20 September 2026 (S12 correction message):

> File one backlog item: scope the CloudFront custom error responses to
> the SPA behavior only (or route /api/* errors through untouched), so
> API failures return JSON errors, never index.html with 200. That
> masking will hide real production errors from users and monitors.

## What went wrong

The S12 build agent hypothesised that CloudFront was dropping multipart
POST bodies on `/api/sows/upload`, because the API-context request from
Playwright received `<!doctype html>` back with `Content-Type:
text/html`. HAR capture from the real browser (see
`docs/reports/s12/upload-requests.log`) proves the opposite: the
browser upload returned `200 application/json` as expected. The HTML
body came from CloudFront's SPA fallback — its custom-error-response
rewrite maps 403/404 to `index.html` with HTTP 200 across the whole
distribution, including the `/api/*` behaviour, so any legitimate API
error is invisible to callers and monitors.

That masking is a production risk: a bad token, an expired session or
a 500 from the API will render as "the app looks broken" instead of
returning a useful status a client (or CloudWatch) can act on.

## What to change

- Scope CloudFront custom error responses to the SPA behaviour only.
  Options (in preference order):
  1. Move the SPA-rewrite rule off the distribution-level
     `CustomErrorResponses` and onto the default-cache-behaviour's
     `FunctionAssociations` (a CloudFront Function that rewrites the
     URI to `/index.html` when the path is not `/api/*` and the
     origin returned 4xx). This keeps `/api/*` responses byte-for-byte
     as the ALB sent them.
  2. Alternatively, add explicit ordered cache behaviours for `/api/*`
     that set `error_caching_min_ttl=0` and clear
     `custom_error_responses` on the origin request policy — Terraform
     `aws_cloudfront_distribution.custom_error_response` is
     distribution-scoped, so option 1 is cleaner.
- Add a smoke test in `.github/workflows/staging-smoke.yml` that hits
  `/api/does-not-exist` on staging and asserts the response is JSON
  with `status: 404` — not HTML.
- Update `docs/runbooks/staging-deploys.md` with the recipe: after the
  CloudFront invalidation completes, run the smoke check.

## Definition of done

- On staging: `curl -sI https://d1mu2un4hj9akj.cloudfront.net/api/nope`
  returns `HTTP/2 404` with `content-type: application/json`, not `200
  text/html`.
- CloudFront invalidation for the SPA path (`/`, `/assets/*`) still
  serves `index.html` on unknown paths.
- The staging smoke check runs after every deploy and gates.
