# Current Worktree Inventory

## Snapshot Boundary

Git metadata captured 2026-10-03 01:13:46 UTC through 2026-10-03 01:14:13 UTC; active lead/governance HEAD and status rechecked 2026-10-03 01:15:16 UTC. This is a point-in-time, serial, non-atomic inventory, already aging after that timestamp. The current entrypoint in `docs/s21/claude-handoff.md` overrides this snapshot for later HEAD/runtime/task updates. Historical `branch-inventory.md` and its old 67-tree/T11 summary are not current counts.

Observed **71 registered worktrees: 66 clean, 5 dirty; 13 tracked modifications and 10 untracked entries**. No staged changes, detached worktrees, locked or prunable entries were reported. Ignored files are excluded by Git status; this is not a filesystem, process, dependency, secret or runtime audit. Clean means only no tracked/untracked status entries, not integrated, tested, finished or safe to remove.

All 71 absolute paths, checked-out branches, full HEADs and statuses are below. These are checked-out branch heads, not a census of every preserved local or remote ref. All historical owners, original fork bases and semantic integration states are **unknown** unless explicitly recorded in the next section. Commit ancestry alone does not establish cherry-pick equivalence. The lead identifies other workers as idle/historical; this document did not inspect processes.

## Active And Preserved Work

- **Lead:** `/Users/srikanthparimi/OfficeApp/dealgate-s21-forecast`, `feat/s21-forecast`, observed `fa0c787b19beacaf68f6f7ab63d86af5f1edb2fd`. Active T18 connected-proof/integration and handoff work. Exact dirty paths are below; their contents and runtime were not inspected. Lead HEAD may move immediately.
- **Governance:** `/Users/srikanthparimi/OfficeApp/dealgate-s21-actual-coverage`, reused branch `s21/t18-account-label`, observed `99b98752cff684f31216cc6bdf20e607adce6eec` (guarded five-view fixture). Lead reports this fixture **unmerged/unexecuted**, with a guard correction being authored. Git status was still **clean** at the 2026-10-03 01:15:16 UTC recheck; the pending correction is reported work, not an observed dirty file or completed fix. Original branch fork base unknown.
- **QA:** `/Users/srikanthparimi/OfficeApp/dealgate-s21-ocr-evidence`, now `s21/t18-inventory`, created from exact `fa0c787b19beacaf68f6f7ab63d86af5f1edb2fd` after the previous branch was verified clean. This task owns only this new inventory. Its table HEAD is the pre-document-commit HEAD; committing this file necessarily advances that one entry. Final delivery provides the resulting commit.
- **Preserved OCR:** the unmodified `s21/ocr-evidence` ref remains at `57dcd0dea99d2f44ef1035d584c9ad1b6298ca0e`. It contains partial checkpoint `3044163a038cc4044ab4c2b336ac670862c345e7` (`test: checkpoint unimplemented OCR evidence boundary contract`). Ancestry confirms that checkpoint is on the preserved OCR ref and is not an ancestor of the sampled integration HEAD. Lead explicitly identifies OCR as **unmerged/partial**; no implementation completion is claimed. No OCR edits were moved into this inventory branch.
- **Integrated empty-account labels:** lead reports worker `f443f259f4af28f3ce39bed110b7dc365a872716` integrated as `ae753de78ba8bae93949bb4b0175d38c8bebd5da`. Git ancestry confirms the integration commit is included in sampled `fa0c787b19beacaf68f6f7ab63d86af5f1edb2fd`. Semantic equivalence/tests were not reassessed here.
- **Preserved older actuals branch:** `s21/actual-coverage` remains at `3731c8c8873e0a6e4dcf08ff86bd56065be4ef57` (same-identity financial lock regression). Lead reports its prior work integrated; this branch ref is not the currently checked-out T18 fixture branch. No new integration proof is inferred from its old tree name.

## All Registered Worktrees

| # | Absolute worktree path | Checked-out branch | Full HEAD at snapshot | Git state | Assigned activity / ownership |
| --- | --- | --- | --- | --- | --- |
| 1 | `/Users/srikanthparimi/OfficeApp/dealgate` | `main` | `321b365393171837ccfe364def2b13ae5a72c06d` | dirty | Historical; owner unknown |
| 2 | `/Users/srikanthparimi/OfficeApp/dealgate-s20-W1` | `s20/W1` | `d56265fed9bf5737b30ed0585bdc17430cc9070f` | dirty | Historical; owner unknown |
| 3 | `/Users/srikanthparimi/OfficeApp/dealgate-s20-W2` | `s20/W2` | `8d94ef406ea8d7a3b1617ac601d45022974e6660` | dirty | Historical; owner unknown |
| 4 | `/Users/srikanthparimi/OfficeApp/dealgate-s20-W3` | `s20/W3` | `9dd3f358515cf1998cb1eb6db55a5aedb044bc24` | clean | Historical; owner unknown |
| 5 | `/Users/srikanthparimi/OfficeApp/dealgate-s20-W4` | `feat/s20-w4` | `1f05090df3476511955cb313364fe3f59b83ded6` | dirty | Historical; owner unknown |
| 6 | `/Users/srikanthparimi/OfficeApp/dealgate-s20-W5` | `s20/W5` | `423eeb045633f222a236daec9f8fd02bebe2b1fd` | clean | Historical; owner unknown |
| 7 | `/Users/srikanthparimi/OfficeApp/dealgate-s20-W6` | `s20/W6` | `4f0363fad2f0000eb1a278c9995d112c16ac750f` | clean | Historical; owner unknown |
| 8 | `/Users/srikanthparimi/OfficeApp/dealgate-s20-W7` | `feat/s20-w7` | `8b42c81a4f398eb445485d00c4ea7e5929104bf1` | clean | Historical; owner unknown |
| 9 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-actual-coverage` | `s21/t18-account-label` | `99b98752cff684f31216cc6bdf20e607adce6eec` | clean | Governance active |
| 10 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-approval-card` | `s21/approval-card-population` | `1e74402f4872f036d51c221cc6f81d7e9f6c5cc5` | clean | Historical; owner unknown |
| 11 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-commercial` | `s21/commercial` | `fad62b34015f4432f846b1cbc83aa5da75197e2b` | clean | Historical; owner unknown |
| 12 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-commercial-ui` | `s21/commercial-ui` | `08bceb292e1ec439ea71f6b51287a5a7aaec5214` | clean | Historical; owner unknown |
| 13 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-conflict-drafts` | `s21/conflict-draft-invalidation` | `550b8c1f81589b04c262b99e951aa4f136eb6dbe` | clean | Historical; owner unknown |
| 14 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-connected-journey` | `s21/connected-actuals-automation` | `9565ad8638a17f25f20b7bb9f1825440f6970cd7` | clean | Historical; owner unknown |
| 15 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-coverage-editor` | `s21/coverage-editor` | `48c5cf4b2e357fba51e28024221a9fdafe0e0503` | clean | Historical; owner unknown |
| 16 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-crm-bu-readers` | `s21/crm-bu-readers` | `7d6745ae621181a60536731416f0be671643f8c4` | clean | Historical; owner unknown |
| 17 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-crm-facet-wiring` | `s21/crm-facet-wiring` | `7b7d0193d9d900dd180c24ac6838b0015052f9e9` | clean | Historical; owner unknown |
| 18 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-crm-filters` | `s21/crm-filters` | `339e22188e108eed2b414d07315c7d7b0b87c916` | clean | Historical; owner unknown |
| 19 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-crm-metadata` | `s21/crm-metadata` | `6447305de1fe33c193efcb502ceb89308c9c0a90` | clean | Historical; owner unknown |
| 20 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-crm-source-review` | `s21/crm-source-review` | `e555140fa2f927f94043c35964d91aade0e65cab` | clean | Historical; owner unknown |
| 21 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-demand-coverage` | `s21/demand-coverage` | `e69d813fc517a50d2f7553ac53399c9108f84968` | clean | Historical; owner unknown |
| 22 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-demand-projection-fix` | `s21/demand-projection-fix` | `22a163a04699febdc87d150b876f077b1d437e57` | clean | Historical; owner unknown |
| 23 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-demand-source` | `s21/demand-source-projection` | `a5bacf944e3ec965f6cd5daaf925ed5677200df9` | clean | Historical; owner unknown |
| 24 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-demand-ui` | `s21/demand-ui` | `2127701066688346900df56e731a1fb098d05e82` | clean | Historical; owner unknown |
| 25 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-extraction-corpus-audit` | `s21/extraction-corpus-audit` | `dfaf23c5b4c0672c5c77dc04aac6619d9483295a` | clean | Historical; owner unknown |
| 26 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-extraction-diagnosis` | `s21/extraction-diagnosis` | `19ed715d08223e063002d5a1a1217bc5acd32364` | clean | Historical; owner unknown |
| 27 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-extraction-overrides` | `s21/extraction-overrides` | `788a3cdadf2a5b3001a2836048ddaa3dab6b523c` | clean | Historical; owner unknown |
| 28 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-filter-fixture` | `s21/pipeline-filter-fixture` | `8112e3f5e46311326fbbd28e32e8df80c9406d4b` | clean | Historical; owner unknown |
| 29 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-forecast` | `feat/s21-forecast` | `fa0c787b19beacaf68f6f7ab63d86af5f1edb2fd` | dirty | Lead active |
| 30 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-forecast-lane` | `s21/forecast` | `f2a88ed9e1f41aa6f6058971098700bf2256ae57` | clean | Historical; owner unknown |
| 31 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-forecast-overview` | `s21/forecast-overview` | `67c9814dc966efe6fa9e9eb8e2225faab0bf21cd` | clean | Historical; owner unknown |
| 32 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-forecast-ui` | `s21/forecast-ui` | `ead499e307681d0496330ec78471c616a34714e5` | clean | Historical; owner unknown |
| 33 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-governance` | `s21/governance` | `3db1b93eba7ee9b115ac0a59744c91367edc9c5f` | clean | Historical; owner unknown |
| 34 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-next-opportunities` | `s21/next-opportunities` | `3bd7c08236c544694b52d3f640904c9b81b2ab88` | clean | Historical; owner unknown |
| 35 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-ocr-evidence` | `s21/t18-inventory` | `fa0c787b19beacaf68f6f7ab63d86af5f1edb2fd` | clean | QA inventory active |
| 36 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-part-time-fixture` | `s21/part-time-fixture` | `3704473a131be84a73ef70cecefc8969f83d89f9` | clean | Historical; owner unknown |
| 37 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-people-ui` | `s21/people-supply-ui` | `6d46390f8dd5093ed7b80fdc60621d05db11cebb` | clean | Historical; owner unknown |
| 38 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-pipeline-fixtures` | `s21/pipeline-fixture-projection` | `ad9356992b60134771d3d5ef7d9faa35b464f3c7` | clean | Historical; owner unknown |
| 39 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-plan-binding` | `s21/plan-staffing-binding` | `8e36c8922da1d66ba4b30333949acd1f3205ba45` | clean | Historical; owner unknown |
| 40 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-plan-source` | `s21/plan-source-provenance` | `8bbd3e23add55d28ed83f89c1e68641bf886aba7` | clean | Historical; owner unknown |
| 41 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-project-source-scope` | `s21/project-source-scope` | `0a54345c876cd118c1cfb1cf8979b5085dae3ebb` | clean | Historical; owner unknown |
| 42 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-publication-boundary-fixture` | `s21/publication-boundary-fixture` | `a5642dabd021b27c68d8e8115c4d2c1b71d4689c` | clean | Historical; owner unknown |
| 43 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa` | `s21/qa` | `a7dab1e603b47f7b433035bf17e28a1cbe8b91bb` | clean | Historical; owner unknown |
| 44 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-actuals` | `s21/qa-actuals` | `b86a72520059bb480168bffd162ee253940a74df` | clean | Historical; owner unknown |
| 45 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-commercial-ui` | `s21/qa-commercial-ui` | `a127e71b568c20d46d35b4a216876ffef0d93838` | clean | Historical; owner unknown |
| 46 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-company-demand` | `s21/qa-company-demand` | `fb6586270d97acc01ef5d7b27b87794ca3f66f65` | clean | Historical; owner unknown |
| 47 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-confirmation-races` | `s21/qa-confirmation-races` | `561b46d5f5e7d28ff9790ecfc77017be04304c84` | clean | Historical; owner unknown |
| 48 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-coverage` | `s21/qa-coverage` | `99df2a7d21db2101c7e843b9c2d4e9c2a337fc0e` | clean | Historical; owner unknown |
| 49 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-coverage-locks` | `s21/qa-coverage-locks` | `a3b4070f8a355965691a718ae4e61b1c0397cd99` | clean | Historical; owner unknown |
| 50 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-deletion` | `s21/qa-deletion` | `5565273d2b1e4f6b206f427de590df7d4b809537` | clean | Historical; owner unknown |
| 51 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-demand` | `s21/qa-demand-publication` | `15129dd951250631c19e2b5741ebda5576e5e61e` | clean | Historical; owner unknown |
| 52 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-extraction-review` | `s21/qa-extraction-review` | `46da7efb53618571c95e75001438e7dfd7a3b965` | clean | Historical; owner unknown |
| 53 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-overview` | `s21/qa-overview` | `e3858b9e914177031079ea1aefec66ec501c44c2` | clean | Historical; owner unknown |
| 54 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-parent-cleanup` | `s21/qa-parent-cleanup` | `0b0f90300e7b535971aecb1649192922deff242c` | clean | Historical; owner unknown |
| 55 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-people` | `s21/qa-people-allocation` | `367d11a91e53eb4c3e4b1cf8dedffde868b456e4` | clean | Historical; owner unknown |
| 56 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-pipeline` | `s21/qa-pipeline` | `287bb8f3ed946a03ce60a5f8c24fff88568d83fe` | clean | Historical; owner unknown |
| 57 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-plans` | `s21/qa-plans` | `bdb5f6c2bbfdbac81fb1fcf2d87908d67e91e028` | clean | Historical; owner unknown |
| 58 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-project-scope` | `s21/qa-project-scope` | `1e0bceb097ec7a12465be73c3ef49f2ab9bf792e` | clean | Historical; owner unknown |
| 59 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-publication` | `s21/qa-publication-service` | `f6d4c08a0cd97f4d9b521b9a67a39a50962bff10` | clean | Historical; owner unknown |
| 60 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-regression-gap` | `s21/qa-regression-gap` | `da4de2dca62053ca05135f35e025a8eaa0177b52` | clean | Historical; owner unknown |
| 61 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-retained-demand` | `s21/qa-retained-demand` | `4c6a05bc6ef7fdaf40720af0d038443b6674c503` | clean | Historical; owner unknown |
| 62 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-scan` | `s21/qa-scan` | `93853c526c7d9f64b287cba93d3046d262060217` | clean | Historical; owner unknown |
| 63 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-sourcing` | `s21/qa-sourcing` | `f3bbe9c6e279a56b3de8f0a7ac1182d3eee7e424` | clean | Historical; owner unknown |
| 64 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-qa-workforce` | `s21/qa-workforce-import` | `49c67f1eae7e8da49a6828725311c6a244486414` | clean | Historical; owner unknown |
| 65 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-renewal-calendar` | `s21/renewal-calendar` | `30b8bf2e737e9c6ca628bca0267c9d3d32a9b595` | clean | Historical; owner unknown |
| 66 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-reviewer-plan-fixture` | `s21/reviewer-plan-fixture` | `379ffdfd4ea46d13e17a4ba4d99756c41b7d9d14` | clean | Historical; owner unknown |
| 67 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-smoke-service-binding` | `s21/smoke-service-binding` | `35d60acdb0a23a09cd765d7b0dade7c313ccec06` | clean | Historical; owner unknown |
| 68 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-sourcing-dates` | `s21/sourcing-dates` | `b7c8d54cacb1deb5915b21baf374622666cabf52` | clean | Historical; owner unknown |
| 69 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-sourcing-ui` | `s21/sourcing-ui` | `010554294066ae2c9a08ec71a5a9dfaa4ea81ac4` | clean | Historical; owner unknown |
| 70 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-stage-qualified` | `s21/stage-qualified` | `6a64321f6fddc8b301f412e5dc4644a4c93b9f5a` | clean | Historical; owner unknown |
| 71 | `/Users/srikanthparimi/OfficeApp/dealgate-s21-tracking-boundaries` | `s21/tracking-boundaries` | `f969d6b512870b8c3e9522c152ef2d1679130986` | clean | Historical; owner unknown |

## Exact Dirty Paths

Status below is literal `git status --porcelain=v1 --untracked-files=all`: leading space plus `M` means unstaged tracked modification; `??` means untracked. No listed path was edited, cleaned, staged or reset by this inventory task. Dirty historical content remains preserved; its owner, intent, readiness and integration are unknown.

### dealgate

```text
 M docs/reports/s19-1/clients-view.png
 M docs/reports/s19-1/expanded-client.png
 M docs/reports/s19-1/opportunities-view.png
 M docs/reports/s19-1/stage-strip.png
 M docs/reports/s19-1/summary-bar.png
 M docs/reports/s19-1/sync-banner.png
```

### dealgate-s20-W1

```text
 M api/app/services/hubspot_intake.py
 M worker/hubspot_intake.py
```

### dealgate-s20-W2

```text
 M web/src/App.tsx
 M web/src/api/client.ts
 M web/src/pages/v2/Pipeline.tsx
?? api/tests/test_hubspot_pipeline_reconciliation.py
?? web/node_modules
?? web/src/__tests__/v2/PipelineUrlState.test.tsx
?? web/src/pages/v2/ClientDetail.tsx
?? web/src/pages/v2/DealDetail.tsx
```

### dealgate-s20-W4

```text
?? api/.venv
?? web/node_modules
```

### dealgate-s21-forecast

```text
 M docs/s21/claude-handoff.md
 M tests/e2e/local/s21-five-views.spec.ts
?? dev.db
?? docs/s21/evidence/baseline/full-commercial.xml
?? docs/s21/evidence/baseline/t18-empty-account.xml
```

## Collection Commands And Limits

Commands were run serially. For each registered path, status used `--no-optional-locks` to avoid writing an index refresh in another worktree.

```sh
git status --short --branch --untracked-files=all
git branch --list s21/t18-inventory
git switch -c s21/t18-inventory fa0c787b19beacaf68f6f7ab63d86af5f1edb2fd
git worktree list --porcelain
git --no-optional-locks status --porcelain=v1 --untracked-files=all
git for-each-ref --format='%(refname:short) %(objectname)' refs/heads/s21/ocr-evidence refs/heads/s21/actual-coverage refs/heads/s21/t18-account-label refs/heads/feat/s21-forecast refs/heads/s21/t18-inventory
git merge-base --is-ancestor 3044163 s21/ocr-evidence
git merge-base --is-ancestor 3044163 fa0c787b19beacaf68f6f7ab63d86af5f1edb2fd
git merge-base --is-ancestor ae753de fa0c787b19beacaf68f6f7ab63d86af5f1edb2fd
```

The three ancestry exit statuses were respectively 0, 1 and 0. Full commit IDs and subjects were read with `git show -s`; active HEADs were rechecked with `git rev-parse HEAD`. No source-content scan, application import, suite, installation, browser, DB, cloud or shared runtime was started. Only this file is authored, and only the QA worktree branch/index is changed.
