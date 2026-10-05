# T17 Documents History Roles

Tested against base `f74df880e8b1a718e0544accb8f9e1d32730d77c`.

The SOW Documents tab was reachable by Legal and HR, but its version-history
request used the narrower staffing-write role set and returned 403. The history
reader now extends the existing read role set with Legal and HR; staffing writes
remain unchanged.

Baseline focused run: 4 failed and 4 passed (`/tmp/s21-history-roles-red-f74df88.xml`).
All four Legal/HR business and issued-fixture history reads failed with 403; all
four staffing-write denials passed.

Final run: 23 passed, no skips or failures
(`/tmp/s21-history-roles-green-f74df88.xml`). It includes the eight new cases plus
15 existing account/fixture isolation cases. Ruff passed for both changed Python
files. This is local API evidence, not browser, staging or role-provider proof.
