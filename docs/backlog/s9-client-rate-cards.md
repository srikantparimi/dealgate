# S9 — Client rate cards (client-scoped bill rates, MSA-imported)

## Story
Split the existing single "rate card" concept into three cleanly separated
tables per `docs/sow-first-principles.md`:

- **Client bill rate cards** — per legal entity, versioned + effective-dated.
  Import from the MSA rate schedule (the extractor reads it the same way it
  reads a SOW). Source of revenue rates.
- **HR cost bands** — role × seniority × location. Source of cost.
- **Margin policy** — floors + cost definition + allocation rule. Company-
  wide.

Resolution order for a SOW's revenue rates: client card → SOW-stated rates
override → client segment default → company default. Every fallback is
loud (warning chip on the package + summary).

## Deliverables
1. Migration `20260919_XXXX_client_rate_cards.py`:
   - `client_rate_card` (id, client_id FK legal_entity, effective_from, published_at, published_by, notes, source ENUM(msa|manual|import), source_document_id nullable).
   - `client_rate_card_row` (id, client_rate_card_id FK, role, seniority, location, bill_rate NUMERIC(10,4), currency, unit ENUM(hourly|daily|monthly), effective_period).
   - Rename existing `rate_card_*` → `cost_band_*` in migration + models + services + routers. Keep the old table alive until the migration ships (dual-write only if it saves a story; otherwise a straight rename with a downgrade path).
2. `api/app/models/client_rate_card.py`.
3. `api/app/services/client_rate_cards.py`:
   - `publish_client_rate_card(session, actor_id, client_id, rows, ...)` — immutable.
   - `active_client_rate_card(session, client_id, at=None)`.
   - `resolve_bill_rate(session, client_id, role, seniority, location, sow_stated=None) -> {rate, source, warning}`.
4. `api/app/routers/client_rate_cards.py` (Finance/SystemAdmin writes; any governance role reads):
   - `GET  /clients/{id}/rate-card` — active card + rows.
   - `POST /clients/{id}/rate-card` — new version.
   - `POST /clients/{id}/rate-card/import` — accepts an MSA file, extracts a rate schedule via the existing Bedrock adapter, returns a draft the user confirms.
5. Update `api/app/services/rate_cards.py` (now `cost_bands.py`) to purge bill-rate logic and stay a cost-only service. The GM engine reads bill rates through `resolve_bill_rate` + cost through `lookup_cost` — two functions, two sources of truth.
6. **Web**: Settings → Rate cards page now has 3 tabs — **Client cards / Cost bands / Margin policy**. Client cards tab lists clients + their active card version; each row opens a per-client card editor (import from MSA button + resolved rows).
7. Tests: 12+ new tests covering the split, resolution order, fallback warning, MSA import happy path.

## Constraints
- Backward compat: the existing GM sandbox + Delivery Model Builder keep working — swap the internal call to `resolve_bill_rate` for revenue and keep `lookup_cost` for cost.
- Every write emits `client_rate_card.published` audit.
- Bill rates cannot come from HR bands and vice versa.

## Notes
Referenced by `s9-sow-first-pipeline.md` — that story consumes
`resolve_bill_rate`.
