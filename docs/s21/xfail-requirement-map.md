# Inherited Xfail Requirement Map

## Scope And Artifact

This is a static, per-case attribution of the 150 inherited xfails in
`docs/s21/evidence/baseline/full-0059.xml`, not a new test run or acceptance
result. Reviewed from application baseline `646419b` on
`s21/qa-extraction-review`; the prior review report is unchanged. No application
imports, test collection/execution, database, browser or cloud calls were made.
Only native XML/source reads and documentation checks were used.

- JUnit timestamp: `2026-10-02T08:21:07.062113-07:00`; elapsed `602.785` seconds.
- Stored suite: 2,342 tests, zero failures/errors, 151 skipped entries:
  **150 `pytest.xfail` + one `pytest.skip`**, hence 2,191 passing entries.
- Artifact SHA256: `0db12d155bb494cb6c278c8888961fedd9154e36ee88fa3dec5cd2826520e636`.
- This JUnit metadata does not identify a code SHA. The review baseline is not
  being substituted for the source revision of that historical run.
- **30 groups, 138 marked functions, 150 expanded node IDs**: parameterization
  adds four missing-input, six permission-matrix and two material-change cases.
- **S = 146 skeleton cases** (134 function bodies raising `AssertionError`,
  plus 12 expansions). Their marker wording sometimes names an old dependency
  instead of saying skeleton; that does not make the body substantive.
- **H = four absent-helper cases**: the first four renewal tests import
  `compute_trigger_date`, absent from `app.services.renewals`; the implemented
  helper is `compute_alert_date`. These are not failing calculations of that
  implemented helper. The other four renewal cases are skeletons.
- The separate live skip is
  `api/tests/test_bedrock_model_check.py::test_default_extract_model_id_is_live_and_invokeable`,
  recorded reason `"opt-in live check; set LIVE_BEDROCK_CHECK=1 with AWS creds to run"`.
  It affects FC-09 / S21-18 (S21F:T16/T24), but is **not** one of the 150 xfails.

## Reading The Crosswalk

Every table row preserves the JUnit `classname`/`name` identity, including
parameter suffixes, as a repository-relative pytest node ID. No collection was
used: `tests.test_s20_x` becomes `api/tests/test_s20_x.py`. Recorded reasons
are copied from `skipped[@type="pytest.xfail"]/@message` as JSON strings;
ASCII `\uXXXX` escapes preserve any original non-ASCII characters exactly.
The JUnit entries have no exception body: S/H is a separate source-inspected
classification, not an invented traceback or replacement marker reason.

All rows also relate to **CO-02 / S21F:T38** for regression reconciliation;
the requirement column lists additional affected functional v3 IDs. Scenario
IDs in the last column are exclusively **S21F:T01-T45**, not the old S20
numbers appearing verbatim inside reasons. Links identify affected scope, not
equivalent tests, passing requirements or permission to retire a skeleton.
The source contract is `docs/directives/s21-forecast-implementation.md`;
`docs/s21/qa-regression-gaps.md` supplies the earlier 30-group investigation.
In particular, currency/floor cases also map to S21-15's explicit missing-cost
and component-floor rules, and date-filter cases map to S21-11's timezone and
boundary contract, even where the earlier summary only listed a scenario.

## Superseding Evidence Is Not Retirement

The earlier gap inventory is historical; its missing implementation observations
must not be copied forward as though intervening source fixes did not happen:

| Historical area | Later source/evidence | What remains true of this inventory |
| --- | --- | --- |
| Release used sixty days instead of calendar months | `8857936` changes signed release to `compute_alert_date`; `docs/s21/lanes/renewal-calendar.md` records literal release-date regressions and an attributed 54-pass/13-xfail run | That specific release defect is superseded. All eight inherited renewal entries still appear here; four import the obsolete name. Weekly acknowledgement and verified-extension behavior are not proved by calculator equivalence. |
| Scan resume/metadata/archive boundaries | `1c5b245` adds atomic backfill pages; `2761da9` adds independent boundary cases; `8bd6da6` fixes scan cycles, metadata races and stale restoration | These are new implementations/assertions, not execution of the five inherited scan skeletons or the inherited worker-crash skeleton. |
| Pipeline population and Business Unit observations | `9bc8ed7` reconciles independent pipeline findings; `494ae2e` reads current observed BU facts across views | A shared behavior may now have meaningful replacement coverage; each legacy filter/rollup assertion still needs an explicit equivalence/retirement decision. |
| Re-extraction correction preservation and review | `48f47f4`, `57f7269`, `e75af5c` and `0cbb530` add protected overrides, mutation locks, conflict review and currency guards | The five inherited recovery skeletons remain. The separate `qa-extraction-review.md` records current static review gaps; no live seven-profile corpus is established by these names. |
| Financial actual source revisions and scope | `83ee512` and `f944daa` add retained financial imports and scope/replay corrections, with independent cases in `test_s21_financial_actuals_independent.py` | New FinancialActual revision assertions are not automatically the old ActualPeriod never-update contract. The five inherited baseline/forecast/actuals cases remain recorded xfails. |

These are source/artifact attributions, not freshly executed pass claims. No
test was removed, unmarked, weakened or reclassified in this docs task. The
lead owns the current requirement ledger and complete-regression acceptance;
this map does not overwrite either. Full CO-02 acceptance remains **missing**
from this bounded artifact-only task.

## Per-Case Inventory

## baseline_forecast_actuals (5)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 1 | `api/tests/test_s20_baseline_forecast_actuals.py::test_baseline_is_immutable` | S | `"depends on W7 baseline snapshot on release"` | FC-06, CO-05 | T21, T41 |
| 2 | `api/tests/test_s20_baseline_forecast_actuals.py::test_forecast_history_preserved` | S | `"depends on W7 forecast versioning"` | FC-06, FC-11 | T21, T25 |
| 3 | `api/tests/test_s20_baseline_forecast_actuals.py::test_actuals_new_row_never_updates_old` | S | `"depends on W7 actuals import path"` | FC-06, CO-05 | T21, T41 |
| 4 | `api/tests/test_s20_baseline_forecast_actuals.py::test_duplicate_import_rejected_by_source_event_id` | S | `"depends on W1 + W7 dedupe key (D7)"` | FC-06, FC-12, CO-05 | T21, T28, T41 |
| 5 | `api/tests/test_s20_baseline_forecast_actuals.py::test_deterioration_triggers_recovery_flag` | S | `"depends on W7 recovery-flag emitter"` | FC-06, CO-05 | T21, T41 |

## ceo_conditional (5)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 6 | `api/tests/test_s20_ceo_conditional.py::test_compliant_package_reads_not_required` | S | `"depends on W3 CEO surface + gm assessment"` | S21-06, S21-15 | T06, T13 |
| 7 | `api/tests/test_s20_ceo_conditional.py::test_below_floor_package_requires_exception` | S | `"depends on W3 CEO service + gm below-floor detection"` | S21-06, S21-15 | T06, T13 |
| 8 | `api/tests/test_s20_ceo_conditional.py::test_conditions_are_enforced_at_release` | S | `"depends on W3 CEO exception conditions engine"` | S21-06, DG-06, CO-05 | T06, T17, T41 |
| 9 | `api/tests/test_s20_ceo_conditional.py::test_expired_exception_blocks_release` | S | `"depends on W3 CEO exception expiry"` | S21-06, DG-06, CO-05 | T06, T17, T41 |
| 10 | `api/tests/test_s20_ceo_conditional.py::test_material_change_invalidates_exception` | S | `"depends on W3 material-change invalidation (T21)"` | S21-03, S21-06, S21-16 | T03, T06, T14 |

## client_rollups (5)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 11 | `api/tests/test_s20_client_rollups.py::test_mixed_open_closed_counts` | S | `"skeleton; extend existing list_clients()"` | S21-09, DG-02 | T09, T17 |
| 12 | `api/tests/test_s20_client_rollups.py::test_zero_deal_client_renders_row` | S | `"skeleton"` | S21-09, DG-02 | T09, T17 |
| 13 | `api/tests/test_s20_client_rollups.py::test_multiple_deal_owners_visible` | S | `"skeleton"` | S21-10, DG-02 | T10, T17 |
| 14 | `api/tests/test_s20_client_rollups.py::test_closed_lost_client_reads_open_0_with_label` | S | `"skeleton; L07 regression for 74 Sky"` | S21-09, DG-02 | T09, T17 |
| 15 | `api/tests/test_s20_client_rollups.py::test_multi_association_deal_counted_once_in_global` | S | `"skeleton"` | S21-09, DG-02 | T09, T17 |

## extraction_recovery (5)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 16 | `api/tests/test_s20_extraction_recovery.py::test_extraction_failure_preserves_file` | S | `"skeleton"` | DG-04, FC-09 | T16, T28 |
| 17 | `api/tests/test_s20_extraction_recovery.py::test_ambiguous_fields_are_needs_confirmation` | S | `"skeleton"` | S21-04, S21-18, FC-09 | T04, T16, T24 |
| 18 | `api/tests/test_s20_extraction_recovery.py::test_duplicate_upload_offers_link` | S | `"skeleton"` | DG-04, FC-09 | T17, T28 |
| 19 | `api/tests/test_s20_extraction_recovery.py::test_saved_draft_restores_corrections` | S | `"skeleton"` | S21-03, FC-09 | T03, T24 |
| 20 | `api/tests/test_s20_extraction_recovery.py::test_ai_result_is_a_draft_needing_confirmation` | S | `"skeleton; A7 lifecycle boundary"` | S21-18, FC-09 | T16, T24 |

## filter_combinations (4)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 21 | `api/tests/test_s20_filter_combinations.py::test_or_within_owner_field` | S | `"depends on W2 filter bar and W1 BU mirror"` | S21-09, S21-11 | T09 |
| 22 | `api/tests/test_s20_filter_combinations.py::test_and_across_fields` | S | `"depends on W2 filter bar"` | S21-09, S21-11 | T09 |
| 23 | `api/tests/test_s20_filter_combinations.py::test_owner_and_bu_and_date_intersection` | S | `"depends on W1 BU mirror (D10) + W2 filter bar"` | S21-09, S21-11, S21-12, CO-08 | T09, T44 |
| 24 | `api/tests/test_s20_filter_combinations.py::test_missing_value_filter` | S | `"depends on W2 missing-value filter"` | S21-09, S21-11 | T09 |

## filter_dates (6)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 25 | `api/tests/test_s20_filter_dates.py::test_last_90_preset_includes_recent_only` | S | `"skeleton"` | S21-09, S21-11 | T09 |
| 26 | `api/tests/test_s20_filter_dates.py::test_next_30_preset_covers_close_dates` | S | `"skeleton"` | S21-09, S21-11 | T09 |
| 27 | `api/tests/test_s20_filter_dates.py::test_date_only_field_not_shifted_by_tz` | S | `"skeleton"` | S21-09, S21-11 | T09 |
| 28 | `api/tests/test_s20_filter_dates.py::test_missing_date_filter` | S | `"skeleton"` | S21-09, S21-11 | T09 |
| 29 | `api/tests/test_s20_filter_dates.py::test_boundary_inclusive_lower_exclusive_upper` | S | `"skeleton"` | S21-09, S21-11 | T09 |
| 30 | `api/tests/test_s20_filter_dates.py::test_response_echoes_timezone` | S | `"skeleton"` | S21-09, S21-11 | T09 |

## freshness_injection (5)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 31 | `api/tests/test_s20_freshness_injection.py::test_15_events_drain_within_two_minutes` | S | `"depends on W1 continuous-consumer + watermarks (D4)"` | OP-01, OP-04, CO-06 | T33, T36, T42 |
| 32 | `api/tests/test_s20_freshness_injection.py::test_event_after_tick_boundary_picks_up_within_15_seconds` | S | `"depends on W1 continuous consumer (A2)"` | OP-01, CO-06, FC-12 | T27, T33, T42 |
| 33 | `api/tests/test_s20_freshness_injection.py::test_backlog_over_5_min_flips_freshness_to_stale` | S | `"depends on W1 stale-state banner via watermark"` | OP-01, CO-06, FC-12 | T27, T33, T42 |
| 34 | `api/tests/test_s20_freshness_injection.py::test_dlq_message_flips_state_to_failed` | S | `"depends on W1 DLQ surface"` | OP-01, CO-06, FC-12 | T27, T33, T42 |
| 35 | `api/tests/test_s20_freshness_injection.py::test_worker_tick_without_events_does_not_advance_processed` | S | `"depends on W1 watermark discipline (contract \u00a75)"` | OP-01, CO-06, FC-12 | T27, T33, T42 |

## gm_incomplete_inputs (7)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 36 | `api/tests/test_s20_gm_incomplete_inputs.py::test_missing_input_yields_not_assessed[rate_missing-rate]` | S | `"skeleton; wire to gm.assess()"` | S21-15, S21-17 | T13, T15 |
| 37 | `api/tests/test_s20_gm_incomplete_inputs.py::test_missing_input_yields_not_assessed[cost_missing-cost]` | S | `"skeleton; wire to gm.assess()"` | S21-15, S21-17 | T13, T15 |
| 38 | `api/tests/test_s20_gm_incomplete_inputs.py::test_missing_input_yields_not_assessed[currency_missing-currency]` | S | `"skeleton; wire to gm.assess()"` | S21-04, S21-15, S21-17 | T04, T13, T15 |
| 39 | `api/tests/test_s20_gm_incomplete_inputs.py::test_missing_input_yields_not_assessed[allocation_missing-allocation]` | S | `"skeleton; wire to gm.assess()"` | S21-15, S21-17 | T13, T15 |
| 40 | `api/tests/test_s20_gm_incomplete_inputs.py::test_missing_input_yields_not_assessed[revenue_basis_missing-revenue_basis]` | S | `"skeleton; wire to gm.assess()"` | S21-15, S21-17 | T13, T15 |
| 41 | `api/tests/test_s20_gm_incomplete_inputs.py::test_finance_approval_rejects_not_assessed_package` | S | `"skeleton; wire to /approvals/{package_id}/finance"` | S21-05, S21-15, S21-17 | T05, T13, T15 |
| 42 | `api/tests/test_s20_gm_incomplete_inputs.py::test_command_center_reports_unavailable_not_zero` | S | `"skeleton; asserts Command center attention render"` | FC-12 | T27 |

## gm_thresholds (5)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 43 | `api/tests/test_s20_gm_thresholds.py::test_us_35_percent_exact_passes` | S | `"skeleton; wire to app.gm.check_thresholds()"` | S21-15, S21-17 | T13, T15 |
| 44 | `api/tests/test_s20_gm_thresholds.py::test_india_50_percent_exact_passes` | S | `"skeleton; wire to app.gm.check_thresholds()"` | S21-15, S21-17 | T13, T15 |
| 45 | `api/tests/test_s20_gm_thresholds.py::test_india_49_point_999_percent_fails` | S | `"skeleton; wire to app.gm.check_thresholds()"` | S21-15, S21-17 | T13, T15 |
| 46 | `api/tests/test_s20_gm_thresholds.py::test_blended_margin_cannot_hide_failed_india_component` | S | `"skeleton; wire to app.gm.check_thresholds()"` | S21-15, S21-17 | T13, T15 |
| 47 | `api/tests/test_s20_gm_thresholds.py::test_no_float_in_gm_pipeline` | S | `"skeleton; asserts float never enters the calc"` | S21-15, S21-17 | T13, T15 |

## integrations_truthfulness (5)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 48 | `api/tests/test_s20_integrations_truthfulness.py::test_hubspot_read_only_shown_when_write_scope_missing` | S | `"depends on W4 integrations page derivation"` | OP-01, FC-12 | T27, T33, T42 |
| 49 | `api/tests/test_s20_integrations_truthfulness.py::test_cognito_verified_by_current_request` | S | `"depends on W4"` | FC-12 | T32 |
| 50 | `api/tests/test_s20_integrations_truthfulness.py::test_document_storage_verified_from_config` | S | `"depends on W4"` | DG-04, FC-12 | T17, T28 |
| 51 | `api/tests/test_s20_integrations_truthfulness.py::test_document_signature_is_separate_row` | S | `"depends on W4"` | DG-06, FC-12 | T17 |
| 52 | `api/tests/test_s20_integrations_truthfulness.py::test_health_page_shows_watermarks_not_empty_queue` | S | `"depends on W4 health surface (L20)"` | OP-01, CO-06, FC-12 | T27, T33, T42 |

## many_sows_per_deal (6)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 53 | `api/tests/test_s20_many_sows_per_deal.py::test_two_packages_persist_independently` | S | `"depends on W3 request to relax sow.opportunity_id uniqueness (D1)"` | DG-04, DG-06 | T17 |
| 54 | `api/tests/test_s20_many_sows_per_deal.py::test_version_history_isolated_per_package` | S | `"depends on W3 multi-SOW support"` | DG-04, DG-06 | T17 |
| 55 | `api/tests/test_s20_many_sows_per_deal.py::test_rollup_headline_picks_most_blocked_open_package` | S | `"depends on W3 rollup headline computation"` | S21-09, DG-02, DG-04 | T09, T17 |
| 56 | `api/tests/test_s20_many_sows_per_deal.py::test_archived_package_excluded_from_headline_counted_separately` | S | `"depends on W3 rollup + archive semantics (D1)"` | S21-09, DG-02, DG-04 | T09, T17 |
| 57 | `api/tests/test_s20_many_sows_per_deal.py::test_released_package_never_hides_pending_sibling` | S | `"depends on W3 rollup rules (D1)"` | S21-09, DG-02, DG-04 | T09, T17 |
| 58 | `api/tests/test_s20_many_sows_per_deal.py::test_decisions_do_not_cross_package_boundaries` | S | `"depends on W3 approvals engine"` | S21-03, S21-05, DG-06, FC-12 | T03, T05, T32 |

## material_change_invalidates (6)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 59 | `api/tests/test_s20_material_change_invalidates.py::test_material_change_bumps_version_and_invalidates[price_change-amount-150000]` | S | `"depends on W3 material-change revision + invalidation (T21)"` | S21-03, S21-16, DG-06 | T03, T14, T17 |
| 60 | `api/tests/test_s20_material_change_invalidates.py::test_material_change_bumps_version_and_invalidates[scope_change-scope_text-New: 12-month engagement, +2 developers]` | S | `"depends on W3 material-change revision + invalidation (T21)"` | S21-03, S21-16, DG-06 | T03, T14, T17 |
| 61 | `api/tests/test_s20_material_change_invalidates.py::test_material_change_bumps_version_and_invalidates[staffing_cost_change-role_rate-185.00]` | S | `"depends on W3 material-change revision + invalidation (T21)"` | S21-03, S21-16, DG-06 | T03, T14, T17 |
| 62 | `api/tests/test_s20_material_change_invalidates.py::test_signature_refused_while_invalidated_approvals_outstanding` | S | `"depends on W3 signature gate"` | S21-03, S21-16, DG-06 | T03, T14, T17 |
| 63 | `api/tests/test_s20_material_change_invalidates.py::test_release_refused_until_re_approval_complete` | S | `"depends on W7 release gate"` | S21-03, S21-16, DG-06 | T03, T14, T17 |
| 64 | `api/tests/test_s20_material_change_invalidates.py::test_history_preserves_old_approvals` | S | `"depends on W3 audit trail"` | S21-03, S21-16 | T03, T14 |

## nda_msa_rules (5)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 65 | `api/tests/test_s20_nda_msa_rules.py::test_upload_sets_on_file_true_verified_false` | S | `"depends on W3 NDA/MSA fact split (D3)"` | DG-05 | T17 |
| 66 | `api/tests/test_s20_nda_msa_rules.py::test_legal_decision_flips_verified_true` | S | `"depends on W3 Legal approval \u2192 verification path"` | DG-05 | T17 |
| 67 | `api/tests/test_s20_nda_msa_rules.py::test_signature_holds_do_not_list_nda_msa_by_default` | S | `"depends on W7 signature hold-reasons list (D3)"` | DG-05 | T17 |
| 68 | `api/tests/test_s20_nda_msa_rules.py::test_client_detail_shows_two_independent_facts` | S | `"depends on W2 client detail page render"` | DG-05 | T17 |
| 69 | `api/tests/test_s20_nda_msa_rules.py::test_neither_on_file_nor_verified_blocks_submission` | S | `"depends on W3 approval submission gate"` | DG-05 | T17 |

## owner_resolution (6)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 70 | `api/tests/test_s20_owner_resolution.py::test_active_owner_resolves_to_name` | S | `"depends on W1 owner mirror table with archived support"` | S21-10, S21-12 | T10 |
| 71 | `api/tests/test_s20_owner_resolution.py::test_archived_owner_still_resolves` | S | `"depends on W1 owner mirror with archived support (D2)"` | S21-10, S21-12 | T10 |
| 72 | `api/tests/test_s20_owner_resolution.py::test_unresolved_owner_reads_owner_details_unavailable` | S | `"depends on W1 owner mirror table"` | S21-10, S21-12 | T10 |
| 73 | `api/tests/test_s20_owner_resolution.py::test_null_source_owner_reads_unassigned` | S | `"depends on W1 mirror"` | S21-10, S21-12 | T10 |
| 74 | `api/tests/test_s20_owner_resolution.py::test_company_account_owner_not_derived_from_deals` | S | `"depends on W1 mirror and Client.account_owner_id column"` | S21-10, DG-02 | T10, T17 |
| 75 | `api/tests/test_s20_owner_resolution.py::test_hubspot_owner_without_local_login_still_valid` | S | `"depends on W1 mirror"` | S21-10, S21-12 | T10 |

## ownership_and_rollup (3)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 76 | `api/tests/test_s20_ownership_and_rollup.py::test_source_owner_and_local_assignee_are_separate_columns` | S | `"depends on W1 opportunity schema (source_owner_id + assignee_id)"` | S21-04, S21-10 | T04, T10 |
| 77 | `api/tests/test_s20_ownership_and_rollup.py::test_headline_picks_worst_open_by_d1_order` | S | `"depends on W3 rollup engine"` | S21-09, DG-02, DG-04 | T09, T17 |
| 78 | `api/tests/test_s20_ownership_and_rollup.py::test_archived_count_is_separate` | S | `"depends on W3 archive counting"` | S21-09, DG-02, DG-04 | T09, T17 |

## permissions_uniform (10)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 79 | `api/tests/test_s20_permissions_uniform.py::test_wrong_role_gets_403[POST-/api/approvals/{id}/finance-Finance-Delivery]` | S | `"skeleton; wire to a test client with role-partitioned tokens"` | FC-12 | T32 |
| 80 | `api/tests/test_s20_permissions_uniform.py::test_wrong_role_gets_403[POST-/api/approvals/{id}/legal-Legal-Finance]` | S | `"skeleton; wire to a test client with role-partitioned tokens"` | FC-12 | T32 |
| 81 | `api/tests/test_s20_permissions_uniform.py::test_wrong_role_gets_403[POST-/api/ceo-exceptions-CEO-Delivery]` | S | `"skeleton; wire to a test client with role-partitioned tokens"` | FC-12 | T32 |
| 82 | `api/tests/test_s20_permissions_uniform.py::test_wrong_role_gets_403[POST-/api/release/{id}-Delivery-Sales]` | S | `"skeleton; wire to a test client with role-partitioned tokens"` | FC-12 | T32 |
| 83 | `api/tests/test_s20_permissions_uniform.py::test_wrong_role_gets_403[POST-/api/signature/send/{id}-SalesLeader-Sales]` | S | `"skeleton; wire to a test client with role-partitioned tokens"` | FC-12 | T32 |
| 84 | `api/tests/test_s20_permissions_uniform.py::test_wrong_role_gets_403[GET-/api/packages/{id}/staff-cost-detail-Finance-Sales]` | S | `"skeleton; wire to a test client with role-partitioned tokens"` | FC-12 | T32 |
| 85 | `api/tests/test_s20_permissions_uniform.py::test_wrong_role_gets_403[GET-/api/audit/export.csv-Finance-Sales]` | S | `"skeleton; wire to a test client with role-partitioned tokens"` | FC-12 | T32 |
| 86 | `api/tests/test_s20_permissions_uniform.py::test_forged_cognito_groups_are_rejected` | S | `"skeleton; wire to Cognito token validator"` | FC-12 | T32 |
| 87 | `api/tests/test_s20_permissions_uniform.py::test_search_permissions_match_list_permissions` | S | `"skeleton; wire to search endpoint"` | S21-09, FC-12 | T09, T32 |
| 88 | `api/tests/test_s20_permissions_uniform.py::test_export_obeys_same_permissions_as_list` | S | `"skeleton; wire to export endpoints"` | FC-11, FC-12 | T25, T32 |

## release_authorization (5)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 89 | `api/tests/test_s20_release_authorization.py::test_crm_closed_won_alone_refuses_release` | S | `"depends on W7 release gate"` | DG-06, CO-05 | T17, T28, T41 |
| 90 | `api/tests/test_s20_release_authorization.py::test_internal_signoff_alone_still_refuses` | S | `"depends on W7 release gate"` | DG-06, CO-05 | T17, T28, T41 |
| 91 | `api/tests/test_s20_release_authorization.py::test_all_three_gates_pass_creates_project_once` | S | `"depends on W7 release + project provisioning"` | DG-06, CO-05 | T17, T28, T41 |
| 92 | `api/tests/test_s20_release_authorization.py::test_executed_document_diverging_terms_refused` | S | `"depends on W7 executed-terms diff check (T22)"` | DG-06, CO-05 | T17, T28, T41 |
| 93 | `api/tests/test_s20_release_authorization.py::test_release_retry_is_idempotent` | S | `"depends on W7 idempotency guard"` | DG-06, CO-05 | T17, T28, T41 |

## renewals_calendar_months (8)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 94 | `api/tests/test_s20_renewals_calendar_months.py::test_normal_march_15` | H | `"depends on W4 renewals calendar-month engine (D8)"` | S21-16 | T14 |
| 95 | `api/tests/test_s20_renewals_calendar_months.py::test_march_1_uses_january_1_not_60_days_back` | H | `"depends on W4 D8 engine"` | S21-16 | T14 |
| 96 | `api/tests/test_s20_renewals_calendar_months.py::test_april_30_clamps_to_feb_28` | H | `"depends on W4 D8 engine + month-end clamp"` | S21-16 | T14 |
| 97 | `api/tests/test_s20_renewals_calendar_months.py::test_april_30_leap_year_gives_feb_29` | H | `"depends on W4 D8 engine + leap year"` | S21-16 | T14 |
| 98 | `api/tests/test_s20_renewals_calendar_months.py::test_tz_boundary_no_day_shift` | S | `"depends on W4 TZ handling"` | S21-16 | T14 |
| 99 | `api/tests/test_s20_renewals_calendar_months.py::test_short_assessment_alerts_at_start` | S | `"depends on W4 short-assessment rule"` | S21-16 | T14 |
| 100 | `api/tests/test_s20_renewals_calendar_months.py::test_weekly_repeat_until_acknowledged` | S | `"depends on W4 weekly-repeat scheduler"` | S21-16 | T14 |
| 101 | `api/tests/test_s20_renewals_calendar_months.py::test_unverified_extension_does_not_push_trigger` | S | `"depends on W4 extension verification"` | S21-16 | T14 |

## report_dependency_failure (3)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 102 | `api/tests/test_s20_report_dependency_failure.py::test_agreements_failure_does_not_zero_pipeline` | S | `"depends on W4 command-center summary surface"` | FC-12 | T27 |
| 103 | `api/tests/test_s20_report_dependency_failure.py::test_no_zero_substitution_for_failed_metric` | S | `"depends on W4"` | FC-12 | T27 |
| 104 | `api/tests/test_s20_report_dependency_failure.py::test_failure_surface_links_to_health` | S | `"depends on W4 health surface"` | FC-12 | T27 |

## report_scale (4)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 105 | `api/tests/test_s20_report_scale.py::test_report_covers_120_rows_incl_closed_and_unknown_stage` | S | `"depends on W4 portfolio at scale"` | S21-09, FC-11 | T31 |
| 106 | `api/tests/test_s20_report_scale.py::test_approval_turnaround_median_and_p90` | S | `"depends on W4 approval-turnaround endpoint (L18)"` | FC-11 | T25, T31 |
| 107 | `api/tests/test_s20_report_scale.py::test_missing_aggregate_reads_state_missing_not_zero` | S | `"depends on W4 honest-status handling"` | FC-11, FC-12 | T25, T27, T31 |
| 108 | `api/tests/test_s20_report_scale.py::test_export_covers_all_rows` | S | `"depends on W4 export at scale"` | FC-11 | T25, T31 |

## report_totals (5)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 109 | `api/tests/test_s20_report_totals.py::test_bu_filter_totals_reconcile` | S | `"depends on W4 report endpoints"` | S21-11, FC-11, CO-08 | T09, T25, T44 |
| 110 | `api/tests/test_s20_report_totals.py::test_drill_down_lands_on_matching_pipeline_filter` | S | `"depends on W4"` | S21-09, S21-11, DG-03, FC-11 | T09, T17, T25 |
| 111 | `api/tests/test_s20_report_totals.py::test_mixed_currency_declares_reporting_currency_and_fx` | S | `"depends on W4 currency envelope"` | FC-02, FC-11 | T18, T25 |
| 112 | `api/tests/test_s20_report_totals.py::test_unknown_bucket_visible_in_every_report` | S | `"depends on W4 unknown-bucket surface"` | FC-11, FC-12 | T25 |
| 113 | `api/tests/test_s20_report_totals.py::test_export_row_count_matches_list` | S | `"depends on W4 export endpoint"` | S21-09, FC-11 | T09, T25 |

## scan_resume (5)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 114 | `api/tests/test_s20_scan_resume.py::test_partial_scan_archives_nothing` | S | `"depends on W1 scan generation semantics (A3)"` | CO-07, FC-12 | T27, T28, T29, T43 |
| 115 | `api/tests/test_s20_scan_resume.py::test_mid_scan_record_is_not_archived` | S | `"depends on W1 mid-scan-record protection"` | CO-07, FC-12 | T27, T28, T29, T43 |
| 116 | `api/tests/test_s20_scan_resume.py::test_overlapping_generations_do_not_archive_each_others_records` | S | `"depends on W1 generation lock"` | CO-07, FC-12 | T27, T28, T29, T43 |
| 117 | `api/tests/test_s20_scan_resume.py::test_filtered_scan_does_not_archive_out_of_scope` | S | `"depends on W1 filtered-scan metadata"` | CO-07, FC-12 | T27, T28, T29, T43 |
| 118 | `api/tests/test_s20_scan_resume.py::test_rollback_restores_archived_at` | S | `"depends on W1 rollback support"` | CO-07 | T29, T43 |

## security_boundaries (8)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 119 | `api/tests/test_s20_security_boundaries.py::test_api_responses_are_not_cacheable` | S | `"skeleton; wire to CloudFront + FastAPI headers"` | FC-12, CO-01 | T32, T38 |
| 120 | `api/tests/test_s20_security_boundaries.py::test_authorization_forwarded_end_to_end` | S | `"skeleton"` | FC-12, CO-01 | T32, T38 |
| 121 | `api/tests/test_s20_security_boundaries.py::test_webhook_signature_hmac_correct` | S | `"skeleton"` | CO-07, FC-12 | T27, T32, T43 |
| 122 | `api/tests/test_s20_security_boundaries.py::test_webhook_replay_rejected` | S | `"skeleton"` | CO-07, FC-12 | T27, T32, T43 |
| 123 | `api/tests/test_s20_security_boundaries.py::test_cognito_wrong_issuer_rejected` | S | `"skeleton"` | FC-12 | T32 |
| 124 | `api/tests/test_s20_security_boundaries.py::test_cognito_expired_rejected` | S | `"skeleton"` | FC-12 | T32 |
| 125 | `api/tests/test_s20_security_boundaries.py::test_cognito_wrong_token_use_rejected` | S | `"skeleton"` | FC-12 | T32 |
| 126 | `api/tests/test_s20_security_boundaries.py::test_cognito_wrong_audience_rejected` | S | `"skeleton"` | FC-12 | T32 |

## signature_nda_msa_rule (3)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 127 | `api/tests/test_s20_signature_nda_msa_rule.py::test_signature_holds_omits_nda_msa_when_no_code_rule` | S | `"depends on W3 + W7 alignment (L13 contradiction, D3)"` | DG-05, DG-06 | T17 |
| 128 | `api/tests/test_s20_signature_nda_msa_rule.py::test_if_rule_exists_it_is_documented_and_uniformly_applied` | S | `"depends on decisions.md documenting the rule if it exists"` | DG-05, DG-06 | T17 |
| 129 | `api/tests/test_s20_signature_nda_msa_rule.py::test_four_surfaces_agree` | S | `"depends on W2 client detail + W3 workspace surface"` | DG-05, DG-06 | T17 |

## signature_verification (5)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 130 | `api/tests/test_s20_signature_verification.py::test_unsigned_upload_does_not_execute` | S | `"depends on W7 signature service"` | DG-06, CO-05 | T17, T28, T41 |
| 131 | `api/tests/test_s20_signature_verification.py::test_executed_document_diverging_terms_rejected` | S | `"depends on W7 executed-vs-approved diff"` | DG-06, CO-05 | T17, T28, T41 |
| 132 | `api/tests/test_s20_signature_verification.py::test_declined_signature_requires_rework` | S | `"depends on W7 decline path"` | DG-06, CO-05 | T17, T28, T41 |
| 133 | `api/tests/test_s20_signature_verification.py::test_expired_signature_retry_no_duplicate_send` | S | `"depends on W7 expire + retry path"` | DG-06, CO-05 | T17, T28, T41 |
| 134 | `api/tests/test_s20_signature_verification.py::test_nda_msa_rule_consistent_across_surfaces` | S | `"depends on W3 + W7 NDA/MSA rule alignment (D3, T41)"` | DG-05, DG-06 | T17 |

## source_dedup (4)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 135 | `api/tests/test_s20_source_dedup.py::test_same_event_delivered_twice_yields_one_effect` | S | `"depends on W1 (source, source_event_id) unique constraint (D7)"` | CO-07, FC-12 | T27, T28, T43 |
| 136 | `api/tests/test_s20_source_dedup.py::test_retry_after_commit_before_ack_is_idempotent` | S | `"depends on W1 crash-safety (A4)"` | CO-07, FC-12 | T27, T28, T43 |
| 137 | `api/tests/test_s20_source_dedup.py::test_two_different_events_on_same_row_both_apply` | S | `"depends on W1 dedupe scope (per-event, not per-row)"` | CO-07, FC-12 | T27, T28, T43 |
| 138 | `api/tests/test_s20_source_dedup.py::test_partial_commit_is_never_visible` | S | `"depends on W1 atomic mirror+audit+outbox commit"` | CO-07, FC-12 | T27, T28, T43 |

## stage_reconciliation (3)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 139 | `api/tests/test_s20_stage_reconciliation.py::test_stage_buckets_reconcile_to_total_open` | S | `"depends on W1 aggregation by (pipeline_id, stage_id) \u2014 D9"` | S21-09, S21-12, DG-02 | T09, T10 |
| 140 | `api/tests/test_s20_stage_reconciliation.py::test_client_count_never_leaks_into_deal_count` | S | `"depends on W1 aggregation by (pipeline_id, stage_id) \u2014 D9"` | S21-09, DG-02 | T09, T17 |
| 141 | `api/tests/test_s20_stage_reconciliation.py::test_unknown_stage_bucket_is_explicit` | S | `"depends on W1 aggregation by (pipeline_id, stage_id) \u2014 D9"` | S21-09, S21-12, DG-02 | T09, T10 |

## stale_package_refused (3)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 142 | `api/tests/test_s20_stale_package_refused.py::test_stale_tab_decision_returns_409` | S | `"depends on W3 approvals with version guard"` | S21-03, S21-05, FC-12 | T03, T05, T32 |
| 143 | `api/tests/test_s20_stale_package_refused.py::test_decision_against_pre_revision_version_refused` | S | `"depends on W3 material-change revision path (T21)"` | S21-03, S21-05, FC-12 | T03, T05, T32 |
| 144 | `api/tests/test_s20_stale_package_refused.py::test_rejection_payload_includes_current_version` | S | `"depends on W3 approvals engine"` | S21-03, S21-05, FC-12 | T03, T05, T32 |

## sync_edge_cases (1)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 145 | `api/tests/test_s20_sync_edge_cases.py::test_worker_crash_resumes_from_cursor` | S | `"Session 4 (continuous consumer): mid-batch crash + cursor resume needs the running service"` | CO-07, FC-12 | T28, T43 |

## upload_interrupt_recovery (5)

| # | Exact repository-relative node ID | Kind | Recorded reason (JSON string) | Affected v3 requirement IDs | S21F scenarios |
| ---: | --- | :---: | --- | --- | --- |
| 146 | `api/tests/test_s20_upload_interrupt_recovery.py::test_upload_resumes_at_last_completed_part` | S | `"skeleton"` | DG-04 | T17, T28 |
| 147 | `api/tests/test_s20_upload_interrupt_recovery.py::test_extraction_job_is_idempotent` | S | `"skeleton"` | DG-04, FC-09, FC-12 | T17, T24, T28 |
| 148 | `api/tests/test_s20_upload_interrupt_recovery.py::test_duplicate_upload_offers_link_not_create` | S | `"skeleton"` | DG-04, FC-09 | T17, T28 |
| 149 | `api/tests/test_s20_upload_interrupt_recovery.py::test_approved_version_immutable_across_restart` | S | `"skeleton"` | S21-03, S21-18, DG-06 | T03, T16, T28 |
| 150 | `api/tests/test_s20_upload_interrupt_recovery.py::test_deal_binding_survives_every_step` | S | `"skeleton"` | DG-03, DG-04 | T17, T28 |
