# fixtures/

Only redacted / synthetic data. Never commit real client data.

- `sows/` — five redacted SOWs (S0 collects them). Names replaced with
  `Client A`, `Client B`, etc. Money kept, page numbers kept.
- `gm_sheets/` — three redacted historical GM sheets to test the calc
  library against Finance's Excel.
- `rate_cards/` — planning cost bands by role, seniority, location. Sample
  card for tests; the real card lives in Secrets Manager, not in the repo.

If a fixture starts looking like real client data, delete it and file the
question in `docs/questions.md`.
