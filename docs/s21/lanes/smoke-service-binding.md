# Smoke Service Binding

Baseline `07c36b8`, isolated branch `s21/smoke-service-binding`. Owned only Step2 of `scripts/deploy-smoke.sh` plus necessary service/cluster/container configuration, new `scripts/smoke_model_binding.py`, dedicated offline tests and this report. Upload, extraction assertions and cleanup remain untouched. No cloud calls, runtime, tests, dependency installation or infrastructure mutation during the initial author-only phase.

## Contract

Observe the configured ECS service in the configured region, require a single converged running task, resolve its exact task-definition ARN and named API container, retain the actual image digest, and validate the exact model environment against active regional inference profiles. Refuse missing/duplicate/wrong identities, revisions, malformed descriptions, partial pagination, model/environment override ambiguity and a changed service binding during observation. Explicit named-container selection permits unrelated sidecars without selecting their settings.

This is an observation/binding guard, not proof of provider invocation permission, extraction accuracy, intended release SHA, worker execution, or atomic infrastructure state. Existing manifest/release and real upload gates retain those responsibilities. It deliberately refuses multiple running tasks rather than choosing an arbitrary task; broader replicas require a separately reviewed all-task consistency contract.

## Test-First Checkpoint

Dedicated tests use in-memory AWS CLI JSON response fixtures and a subprocess boundary replacement. No feature responses, extraction outcomes or live cloud records are fabricated. Tests were authored and committed first as `bdaa9a9`. Lead then authorized implementation while runtime remained held; no preimplementation red run occurred and none is claimed.

The implementation uses only the standard library and AWS CLI JSON, records the named running container's actual digest/model, rechecks service and task-list identity after observation, and rejects explicit stub-selecting environment settings. Step2 invokes the helper with existing region plus `S15_ECS_CLUSTER`, `S15_ECS_SERVICE`, `S15_API_CONTAINER` (defaults `officeapp-dev-cluster`, `officeapp-dev-api`, `api`). No bare task-definition family lookup remains. No upload, extraction assertion, cleanup or other step was changed.

## Executed Verification

Lead granted a sole bounded runtime slot after its full backend and the other worker's short run completed. First executed run: **53 passed, exit0**, no skips/xfails/retries. Shell syntax and `git diff --check` both passed, exit0. Slot released after processes completed. No actual AWS CLI, smoke, HTTP, extraction or database operation ran.

Exact commands from this isolated worktree:

```sh
env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/srikanthparimi/OfficeApp/dealgate-s21-smoke-service-binding/api:/Users/srikanthparimi/OfficeApp/dealgate-s21-smoke-service-binding /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest api/tests/test_s21_smoke_model_binding.py -q -p no:cacheprovider --tb=short
bash -n scripts/deploy-smoke.sh
git diff --check
```

The QA executable/dependencies were reused read-only; imports and source belong only to this tree, bytecode/cache writes were disabled, and no dependencies changed. Tests cover model/runtime selector secrets and explicit stub settings, profile activity, named sidecars, pagination refusal, CLI failures, exact ARN/digest selection and service-change refusal.

Lead owns a subsequent read-only live observation, integration regression and the authorized full staging smoke. The preserved upload/cleanup stages have their previously recorded limitations; this narrow guard does not repair or endorse them. The guard validates consistent observed AWS account/region identities, not a DNS-to-service mapping, approved release digest/source SHA or independently expected account; existing release-manifest controls still provide those separate checks.
