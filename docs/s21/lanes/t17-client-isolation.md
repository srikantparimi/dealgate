# T17 Client Fixture Isolation

Branch: `s21/t17-client-isolation`; baseline: `610cc9f`.
Worktree: `/Users/srikanthparimi/OfficeApp/dealgate-s21-actual-coverage`.
Ownership: clients router, new focused client fixture-access tests, this report.

The connected route audit passed owner routes but found that a normal reader
could list the issued fixture client. The fix uses authoritative `account_scope`
and `user_allowed`, not names or inferred CRM provenance. It resolves and commits
the canonical actor before scope reads. Authorized client IDs are filtered before
pagination and totals. Fixture counts, owners, sources and detail opportunities
include only the exact issued opportunity, not an unissued sibling. Existing
regular-business Sales ownership and leader read policies remain in effect.

Client recent activity now includes agreement root IDs, so replacement audit
events can appear without exposing another client's agreement history. The
existing timeline router already uses scoped visible deal IDs; it was not edited.

## Verification

Tests authored before implementation. Original focused execution reproduced
**8 failed / 1 passed in 11.88s**. Initial fix: **9 passed in 4.93s**.
After adding a nonempty fixture timeline and agreement audit assertion:
**10 passed in 6.78s**.

Command (own `api` directory):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest tests/test_s21_client_fixture_access.py -o addopts='' -q -p no:cacheprovider
```

Coverage includes normal/test/unissued readers, expired/wrong-tenant/forged-owner
grants, pagination totals, owner filters, unissued siblings, ordinary Sales
ownership, real private timeline activity and agreement audit attribution.
This is local ASGI/SQLite regression evidence, not staging or full T17 closure.
Lead owns the connected route rerun and the separate agreement endpoint repair.
No browser, provider, shared database, migration or deployment operation was run.
