# S1 E1 — App shell behind SSO

## User story
As any staff member, I log in with my corporate SSO and land on an app shell
that shows my identity and the navigation for my role, so that I can find my
queue without training.

## Acceptance tests (Given/When/Then)
- Given I am not authenticated, when I visit any DealGate page, then I am
  redirected to the IdP and returned to the page I asked for.
- Given I am in the `Sales` group, when I log in, then the left nav shows
  My deals, My tasks, Clients — and no admin links.
- Given I am in the `SystemAdmin` group, when I log in, then the admin section
  is visible; I still cannot approve a package.

## Data touched
- Tables: `user` (id, email, name, groups[], last_login).
- Immutable versions written: none.
- Audit events emitted: `user.login`, `user.logout`.

## Roles allowed
- All roles hit `GET /me`.
- Admin nav gated on `SystemAdmin` group at the API, not just the UI.

## Out of scope
- Local password login.
- Role management UI (separate story).

## Notes
- Blueprint §3 (roles). Build-guide §12 (SSO only, no local passwords).
- Cognito federated to Entra ID or Google Workspace (see questions.md).
