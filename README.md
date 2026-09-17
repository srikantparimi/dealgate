# DealGate

Internal Deal & Delivery Governance platform beside HubSpot. Makes it impossible
to sign a SOW that Delivery, HR, Finance and Legal have not approved against a
calculated gross margin.

- Design: `docs/build-guide.md`
- Policy: `docs/blueprint.md`
- Agent rules: `CLAUDE.md`
- Open decisions: `docs/questions.md`

## Layout

```
dealgate/
  docs/            blueprint, build guide, ADRs, story backlog
  infra/           AWS CDK (TypeScript) — dev/staging/prod
  api/             FastAPI: routers, services, models, migrations
    app/gm/          pure GM calculation library, no I/O
    app/workflow/    state machine + transitions
    app/integrations/ hubspot, ses, teams, bedrock
  worker/          SQS consumers, schedulers, AI jobs
  web/             React + TypeScript
  tests/e2e/       end-to-end scenarios from blueprint § 11
  fixtures/        redacted SOWs, sample GM sheets, rate cards
```

## Local dev (Sprint 0)

Prereqs: Python 3.12, Node 20, Docker.

```
cd api && python -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
uvicorn app.main:app --reload           # http://localhost:8000/healthz

cd web && npm install && npm run dev    # http://localhost:5173
```

### Web env vars

Copy `web/.env.example` to `web/.env.local`. The four `VITE_COGNITO_*` vars
switch the browser to the real Cognito hosted-UI flow:

- `VITE_COGNITO_DOMAIN` — hosted-UI domain (e.g. `https://officeapp-dev.auth.us-east-2.amazoncognito.com`).
- `VITE_COGNITO_CLIENT_ID` — SPA app client ID (no secret, PKCE flow).
- `VITE_COGNITO_REDIRECT_URI` — `/auth/callback` URL; defaults at runtime to `${origin}/auth/callback`.
- `VITE_COGNITO_LOGOUT_URI` — post-logout URL; defaults at runtime to `${origin}`.

Leave them empty to fall back to the `X-Test-User` dev flow — set
`VITE_TEST_USER=<role>@smartek21.com` to pick a role locally. The API
gates that fallback to dev builds only (`import.meta.env.DEV`).

For staging/prod the same names live in GitHub repo secrets — see
`.github/workflows/README.md`.

## Sprint plan

See `docs/build-guide.md` § 13. Sprint 0 delivers the UI kit and the pipeline;
each later sprint delivers real pages, backend-first, tests-first.
