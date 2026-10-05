# Watching Current-Filter Extension

Application `5a5c42c849ecb3807d0816beec62c5fd49bf6782`. API80816:
55pass35.62s ([XML](watching-filter-api.xml)); UI51379:6pass9.99s.
Typecheck44203 found two test-only unsupported options, removed;49298 exits0.

Independent [QA](../../lanes/qa-t39-closure.md) preserved literal T39 local closure
and identified wider CO03 client-group/current-filter gaps. API10469 reproduced
missing authorized deal0vs1. UI27754 reproduced missing current-filter count query.
Repair scopes client-group expansion through the existing authorization helper;
Pipeline Watching count reads the same active filters, reuses the rows request
when watching is selected, and rejects stale response updates.

Browser45589: original full T39 passed40.1s on this application, extension failed
because test selected textbox rather than searchbox. No product error or assertion
timeout increase is hidden. Its finally was interrupted by timeout; lead used
the exact trace actor/deal/group to remove owned watch and archive owned group:
both DELETE responses204. Retained test fixture is provenance-scoped.

Corrected extension33527 passed1/20.5s (test16s): client-group+Watching exact deal1;
nonmatching search updates count/rows0; reload retains0; removing search restores
the same exact deal1; API exact identity corroborates. Finally removes watch and
archives group successfully. No feature responses mocked; only local identity
header adapter. No cloud objects/providers. Original screenshot artifacts retained.

Commands from `tests/e2e`:
```sh
env S21_WATCHING_PROOF_PREFIX=t39-filter npx playwright test --config playwright.s21-local.config.ts s21-watching.spec.ts --workers=1 --output=test-results/s21-watch-5a5c42c
npx playwright test --config playwright.s21-local.config.ts s21-watching.spec.ts --grep 'current search filters' --workers=1 --output=test-results/s21-watch-filter-selector
```

First command historical1pass/1harnessfailure; second corrects only that identified
selector and proves the extension. Unit source correction removes unsupported
Testing Library options; no assertion weakened. Closed-status branch has focused
UI proof, not a new real-provider/staging claim. Broader T12 remains pending.
