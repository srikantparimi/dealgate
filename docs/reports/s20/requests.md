# S20 · cross-worker requests (Lead routes)

Workers append a block here whenever they need a change on a file they
don't own (per `contracts.md` §6) — the Lead applies within the hour and
tags the responsible worker + a link to the requesting commit.

Format:
```
## <Wn>-<UTC>-<seq> · <one-line title>
Reason: <why>
File(s): <paths>
Change: <exact behavior/API>
Rollback: <how to undo>
Test: <acceptance>
Requested-in: <sha of requesting commit or `plan-only`>
```

---

## W2-2026-09-30-01 · Add `opportunity.name` column (dealname)

Reason: Directive S20 §2 W2 · L04 — Opportunities table must show the actual
deal name from HubSpot `dealname`. Today `dealname` is fetched
(`api/app/integrations/hubspot.py:107` includes it in `_DEAL_PROPERTIES`)
but never stored; the UI is forced to render `stage_label` in the Deal
column, which is why every row shows its stage as the deal identity.

File(s): `api/app/models/opportunity.py`,
`api/alembic/versions/` (new revision numbered by Lead),
`api/app/services/hubspot_intake.py` (populate + update path).

Change:
- Add `name: Mapped[str | None] = mapped_column(String(255), nullable=True)`
  on `Opportunity`.
- Migration: `op.add_column('opportunity', sa.Column('name', sa.String(255),
  nullable=True))`. Backward-compatible: nullable, no server_default beyond
  NULL; existing rows keep working; downgrade is `op.drop_column`.
- In `hubspot_intake._upsert_opportunity`: read `props.get("dealname")`,
  set on `Opportunity(name=…)` at insert and at update-with-change-detection
  (same pattern as `stage_label`). Emit the field in the `after` audit.

Rollback: Lead reverts the alembic revision (`alembic downgrade -1`);
`hubspot_intake` change removes the `props.get("dealname")` block.

Test: W2 acceptance test asserts opportunity rows expose `name` via the
API and the SPA renders it in the Deal column. W1's backfill test can
grow a name-populated assertion on next pass.

Requested-in: (this commit)


## W2-2026-09-30-02 · Client account-owner surface for pipeline rollups

Reason: Directive §2 W2 · L05 + contracts §2 D2 — client rows must show a
"client account owner" that is the HubSpot company `hubspot_owner_id`
resolved via W1's owner mirror, NOT derived from a deal. Today
`services/hubspot_pipeline.list_clients` sets `owner_name=None` /
`owner_email=None` on every client row (see
`api/app/services/hubspot_pipeline.py:940-941`) with a "slice 2 UI plugs
deeper owner metadata" comment, then falls back to the *primary deal's
owner* as `owner_id`. That's the exact overwrite-with-deal-owner defect
D2 forbids.

File(s): `api/app/models/client.py` + a migration + W1's mirror
(`api/app/services/hubspot_owners*.py` and intake company upsert).

Change:
- Add `hubspot_owner_id: Mapped[str | None] = mapped_column(String(64),
  nullable=True)` on `Client`.
- W1 populates it in the company-upsert path (currently
  `services/hubspot_intake.upsert_client_from_hubspot`) from the company's
  `hubspot_owner_id` property; on unset → NULL.
- W1's owner mirror exposes a lookup `resolve_owner_by_hubspot_id(session,
  hs_owner_id) -> (name, email) | (None, None)` for W2's query service to
  call once per page of clients (batch).
- Migration: `op.add_column('client', sa.Column('hubspot_owner_id',
  sa.String(64), nullable=True))`, backward-compatible.

Rollback: drop the column; W1's mirror lookup returns (None, None) which
W2 already handles as "not set".

Test: W2 acceptance test seeds a company with a HubSpot owner id + a
deal whose owner is different, asserts the client row's `owner_name`
tracks the company property, not the deal.

Requested-in: (this commit)


## W2-2026-09-30-03 · `hubspot_business_unit` column on opportunity + optional company

Reason: Directive §2 W2 + contracts §4 filter contract — Opportunities
must be filterable by Business Unit, and rows must render a BU column
(L04). Per D10 the BU property is discovered via HubSpot properties API
(W1 owns the discovery + type-aware mirroring). W2 needs a column to
persist the discovered value against so the filter + column work.

File(s): `api/app/models/opportunity.py`, a migration, W1's mapper.

Change:
- Add `hubspot_business_unit: Mapped[str | None] = mapped_column(String(64),
  nullable=True)` on `Opportunity` (assumes the discovered field is a
  simple picklist; if W1 reports a different type in
  `sync_status.hubspot_property_business_unit`, this column becomes
  `String(255)` or JSON per W1's report — Lead decides).
- W1 pulls the discovered internal property name from
  `sync_status.hubspot_property_business_unit`, adds it to
  `_DEAL_PROPERTIES` in `integrations/hubspot.py`, and stores the value
  in `hubspot_business_unit` at insert + change-detected update.
- If the property is on the **company** instead of the deal (D10 says
  "deals, then companies"), W1 mirrors it onto `client.hubspot_business_unit`
  instead; W2 filter joins through the client. W1's `blocked` report is
  authoritative if neither surface yields a property.

Rollback: drop the column; W1 stops writing it.

Test: W2 asserts the `business_unit=[…]` query param filters
opportunities to matching rows, and the column renders in the UI table.

Requested-in: (this commit)

