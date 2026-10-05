# PostgreSQL Confirmation Race Evidence

Lead execution72786, exit0, source8476f3be6c1f9b14b1ff6e760f820a53796ffe5f,
2026-10-02 approximately18:20UTC. Independent script022fce3 integrated8476f3b.
This is a condensed transcription of tool output, not a regenerated test log.

Command from integration root:
`env S21_CONFIRMATION_ADMIN_URL=postgresql+psycopg://s21@127.0.0.1:55421/postgres PYTHONPATH=api:. api/.venv/bin/python -B scripts/s21_confirmation_races_pg.py`

Private database `s21_confirmation_lock_5c19e373a9c448ed8a87329e7f7c15c5`,
migrated to20261002_0061_automation_jobs. Cleanup confirmed after OID/owner/marker
checks, without FORCE or terminating other connections. Retained journey untouched.

| Case | Contender / blocker PID | Observed before writer release | Persisted result |
| --- | --- | --- | --- |
| scope-replay |5571/5569| transactionid wait; public.opportunity RowShareLock |422 extraction_conflict:price;1 unconfirmed version;1 replay audit;0 confirmation/review audits |
| legacy-replay |5572/5571| same exact parent relation/wait |422 missing=[extraction_conflict:price];1 unconfirmed version;1 replay audit;0 confirmation/review audits |
| owner-transfer |5571/5569| same exact parent relation/wait |real ASGI review403 not authorised; transferred owner persisted;source unchanged;0 success audits |
| new-version-selection |5569/5572| same exact parent relation/wait |422 Complete scope: currency: extracted value missing;2 unconfirmed versions;no confirmation/review audits |

Each case had three distinct database backends and refreshed audit/persistence
checks. All audit chains verified. Synthetic provider boundary is explicit;
this is real transaction/API logic, not live OCR/model quality or staging proof.
Selection case inserts version2 through ORM while holding parent lock, not the
upload API. Separate d4d56cc ordinal test proves2 then3 after removal locally;
this report does not extend that to concurrent real upload.
