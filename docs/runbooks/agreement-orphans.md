# Runbook — agreement orphan report (S24-AG1 B13)

`python -m worker.agreement_orphans` lists stored objects in the agreements bucket that no database row
points at. It is **read-only**: it lists the bucket (ListObjectVersions) and reads the database, prints one JSON
document, and deletes nothing. Removing anything it finds is a separate decision for Kanna.

## What it reports

- `live_objects`: every key whose latest version is an object (a key whose latest version is a delete marker
  is already deleted and is not listed).
- `referenced`: keys an `agreement` row, an `agreement_file_version` row or a `standard_agreement` row points at.
- `queued_for_cleanup`: unreferenced keys a pending or retrying deletion job will remove (for example an
  upload whose database row could not be committed, B5).
- `unreferenced_younger_than_min_age`: unreferenced keys newer than 24 hours (their row may still be coming).
- `orphans`, `orphan_bytes` and `groups`: every other unreferenced key, grouped by top-level prefix, with
  count, bytes, oldest and newest, and up to 200 keys per group.

It scans the **whole bucket**, not only `agreements/`: the three objects AG0 expects were written by the S21
proof script under `verification/s21/{run}/agreements/…` (scripts/s21_t17_runtime.py), so a scan of
`agreements/` alone would find none of them (docs/bugs/s24-ag1.md, decision 9).

## Where it can run

The API task role may only put and get objects under `agreements/*`; it cannot list the bucket. The
deletion-cleanup task role (`infra-tf/modules/schedulers/s21_jobs.tf`) holds `s3:ListBucketVersions` on the
agreements bucket, and its task definition already carries `AGREEMENTS_BUCKET` and `POSTGRES_URL`. The image is
the same as the API's, so after the image-only roll the module is present in that task definition.

Running it on staging is an AWS CLI action (an ECS `run-task` of the existing deletion-cleanup task definition
with a command override, the same mechanism `scripts/run-ecs-migration.sh` uses). It changes no resource, but a
build lane never runs it: the Lead runs it once, with Kanna's go-ahead, after the deploy:

```bash
aws ecs run-task --region <region> --cluster <cluster> \
  --task-definition <name_prefix>-deletion-cleanup \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<subnets>],securityGroups=[<sg>],assignPublicIp=DISABLED}" \
  --overrides '{"containerOverrides":[{"name":"deletion_cleanup","command":["python","-m","worker.agreement_orphans"]}]}'
```

The report is the task's single log line (CloudWatch, the deletion-cleanup log group). Exit code 0 means the
report printed; 1 means it could not list the bucket or read the database, and the line says why
(`"error": "…"`).

Locally, with credentials that may list the bucket:

```bash
AGREEMENTS_BUCKET=<bucket> POSTGRES_URL=<url> python -m worker.agreement_orphans
```

## Reading the result

Expected on staging at the time of AG1: three orphans under `verification/` (the S21 proof objects) and none
under `agreements/`. Report the groups and counts; do not delete the three objects (directive S10).
