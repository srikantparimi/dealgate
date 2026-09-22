# Directive S14a: CloudFront must never turn an API error into a 200 HTML page

From: Kanna Parimi, product owner. Commit as `docs/directives/s14a-cloudfront.md`. Promoted from `docs/backlog/cloudfront-4xx-masquerade.md` — this cost an evening of blind debugging in S13a and will hide real production errors from users and monitors.

## The defect

The staging distribution's `CustomErrorResponses` rewrite ANY 4xx/5xx from the ALB origin to `200 + /index.html` from S3, distribution-wide, and the rewritten response gets cached by URI. Every API failure looks like a successful HTML page.

## The fix (Terraform, not console)

1. Scope the SPA fallback to the S3/SPA behavior only: the `/api/*` behavior returns the origin's real status and body, untouched. If CloudFront's distribution-wide `custom_error_response` cannot be scoped (it is distribution-wide by design), the standard fix is: attach the error rewrite only for the SPA routes via a CloudFront Function / error-page pattern on the default behavior's origin, or move `/api/*` to its own distribution or straight ALB DNS for the API. Choose the smallest change that gives: API errors pass through verbatim.
2. `Cache-Control: no-store` on all API error responses (FastAPI middleware: any response ≥ 400 gets it), and set the `/api/*` behavior's error caching TTL to 0 so no error is ever cached.
3. Same PR: move `ALLOW_DEV_SEED_ENDPOINT` into `infra-tf/modules/api/main.tf` as a staging-only variable (absent/false in prod), eliminating the task-def drift created in S13a.

## Proof

- `curl -i https://<staging>/api/nonexistent` and an unauthenticated `/api/sows` through CloudFront → real 404/401 with a JSON body, correct status, `x-cache` never a cached error with stale `age`.
- Repeat the same two curls twice → second response not served from an error cache.
- SPA deep link (e.g. `/sows/xyz` refresh) still serves index.html — the SPA fallback must keep working for page routes.
- `terraform plan` clean after apply (no drift), the dev-seed flag visible in the module, prod plan shows it absent.
- One Playwright helper change: the e2e `apiFetch` helper now asserts `content-type: application/json` on every API call and fails loudly on HTML, permanently.

Report: `docs/reports/s14a.md`, curl transcripts + terraform plan excerpt. Small slice — do not let it grow.
