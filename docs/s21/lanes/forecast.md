# Forecast Financial Projection Lane

## Scope and Isolation

Branch `s21/forecast`, worktree `dealgate-s21-forecast-lane`, baseline `4af15f7`.
Owns only `api/app/gm/forecast.py`, additions to
`api/tests/test_s21_forecast_projection.py`, and this report. Independent QA
tests are unchanged. Own `api/.venv`; no database, cloud, browser, worker, or
deployment operations. Lead integrates. The scoped three-hour authorization
does not change release or infrastructure approvals.

## Financial Changes

- Economic identity is account + source + scope + service month, independently
  of a caller-generated row ID. Duplicate entries fail closed.
- Conversion fractions, FX, probability, and unavoidable-cost calculations use
  exact rational intermediates before returning Decimal money. Ordinary partial
  conversion can cancel a repeating ratio without losing exact final money.
- `ForecastLine.revenue_uses_ratio` is additive and defaults false. The integration
  service must copy this provenance from commercial calendar schedule rows.
  Only proven ratio tails use the established 28-digit calculation precision;
  no currency cent-rounding policy was introduced. Cost does not inherit revenue
  provenance. Ratio values that cannot preserve fractional precision fail closed.
- Aggregate money is summed exactly before precision validation. An unsupported
  exact total raises a visible precision error instead of silently dropping cents.
- Blank FX revisions, probability provenance, and assumption entries exclude
  unresolved planning money with existing explicit reasons.

## Local Evidence

Unchanged independent QA: 31 tests. Existing projection tests: 11 tests unchanged.
Four added adversarial tests cover calendar ratio weighting, exact cost isolation,
large aggregate cent-loss prevention, and partial conversion with FX and
unavoidable costs. Combined: 46 passed, no skips or xfails.

Commands from `api/`:

```sh
.venv/bin/pytest tests/test_s21_forecast_projection.py tests/test_s21_forecast_independent.py
.venv/bin/ruff check app/gm/forecast.py tests/test_s21_forecast_projection.py
.venv/bin/mypy --follow-imports=skip app/gm/forecast.py
```

Ruff and scoped helper typing pass. An initial test invocation ran while isolated
dependency installation was still incomplete and failed collection for missing
`pytest_asyncio`; the subsequent run followed successful installation, not an
assertion change or test retry mechanism.

This is pure financial helper evidence only, not persisted Forecast, permission,
worker, application, staging, or full contract acceptance. Those remain owned by
the integration lead. No merge to main or deployment occurred.
