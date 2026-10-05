# People Managed Supply UI

Isolated `s21/people-supply-ui`, baseline `70d7d2a`. Scope is the implemented
HR/SystemAdmin managed workforce import/history/availability API only. Lead
owns route/navigation wiring, schema/API and demand/sourcing implementation.
No demand, reservation, hire or sourcing controls are rendered by this screen.

The typed client uses POST/GET `/people/imports` and GET `/people/availability`.
The screen checks current role before requesting named supply; server guards
remain authoritative. It displays source observation timestamps, exact Decimal
allocations, dated gross capacity/commitments, named skills/location/timezone,
source evidence and immutable import history. No salary/rate/cost fields are
requested or rendered as workforce attributes.

The JSON upload/editor retains unknown fields for whole-file server validation,
including forbidden financial fields: they are never silently stripped into an
apparently successful partial import. Validation locations/messages are shown.
Request UUID and the latest loaded batch for the same source are server request
metadata, not trusted file metadata. Network/conflict errors retain the draft,
reason and request identity; an explicit source-version reload refreshes the
optimistic base without clearing edits/errors. History paging does not silently
advance that base. Successful import reloads both persisted supply and history.

Known source/version/observation metadata prefill from availability. Backend
gap: availability omits stable `person_key`, so it cannot reconstruct a complete
roster suitable for reimport. The UI therefore requires an actual supplied JSON
roster rather than inventing identity keys or silently replacing the roster with
an empty list. No financial or demand totals are calculated in the browser.

Seven component tests were authored before verification: named supply/freshness,
strict validation with extra salary field preserved, optimistic409 retention,
successful persistence refresh, role restriction, loading/error honesty and
actual FileReader upload. Production was authored during the lead's author-only
capacity window; no preimplementation runtime-red evidence is claimed.

Verification in the serialized slot: **7 tests passed**, no skips/retries,
9.86 seconds. TypeScript and diff checks passed. Actual FileReader loading and FastAPI-shaped validation errors
are included. Dependencies were copied into this worktree (no symlink/shared
writes), and formatting used the existing cached local Prettier executable;
no network install or provider call. Unit mocks are test-boundary fixtures only.
Whole People/FC-07 completion and staging proof remain open. The lead is adding
stable person_key to availability separately; no reconstructed roster claim is
made by this bounded increment.
