#!/usr/bin/env bash
# Run the Terraform-owned release migration task and fail the apply unless the
# candidate image exits successfully. Alembic upgrades are idempotent, so an
# interrupted apply can safely retry after any still-running task is collected.
set -euo pipefail

if [[ $# -ne 5 ]]; then
  echo "usage: $0 <cluster> <task-definition> <subnets-csv> <security-groups-csv> <region>" >&2
  exit 64
fi

cluster=$1
task_definition=$2
subnets=$3
security_groups=$4
region=$5
started_by="tf-migrate-$(printf '%s' "$task_definition" | shasum -a 256 | cut -c1-16)"

task_arn=$(aws ecs list-tasks \
  --region "$region" \
  --cluster "$cluster" \
  --desired-status RUNNING \
  --started-by "$started_by" \
  --query 'taskArns[0]' \
  --output text)

if [[ -z "$task_arn" || "$task_arn" == "None" ]]; then
  run_result=$(aws ecs run-task \
    --region "$region" \
    --cluster "$cluster" \
    --task-definition "$task_definition" \
    --launch-type FARGATE \
    --started-by "$started_by" \
    --network-configuration "awsvpcConfiguration={subnets=[$subnets],securityGroups=[$security_groups],assignPublicIp=DISABLED}" \
    --output json)

  task_arn=$(printf '%s' "$run_result" | jq -r '.tasks[0].taskArn // empty')
  if [[ -z "$task_arn" ]]; then
    printf '%s' "$run_result" | jq -c '{failures: .failures}' >&2
    exit 1
  fi
fi

echo "[migration] waiting for $task_arn"
aws ecs wait tasks-stopped --region "$region" --cluster "$cluster" --tasks "$task_arn"

read -r exit_code reason < <(aws ecs describe-tasks \
  --region "$region" \
  --cluster "$cluster" \
  --tasks "$task_arn" \
  --query 'tasks[0].containers[0].[exitCode,reason]' \
  --output text)

if [[ "$exit_code" != "0" ]]; then
  echo "[migration] failed: task=$task_arn exit=$exit_code reason=${reason:-unknown}" >&2
  exit 1
fi

echo "[migration] succeeded: task=$task_arn"
