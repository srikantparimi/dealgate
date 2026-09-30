#!/usr/bin/env bash
# S15 + S17 · golden-path smoke suite that runs against staging after
# every deploy. Red blocks the deploy.
#
# S17 addendum §2: the smoke owns its fixture. Each run uploads a fresh
# tagged Peppermill SOW, verifies the deploy end to end against it, and
# hard-deletes the client (which cascades everything the smoke created)
# in a trap EXIT — so nothing ever surfaces in Kanna's lists.
#
# Usage:
#   scripts/deploy-smoke.sh                        # against staging default
#   S15_BASE_URL=... scripts/deploy-smoke.sh       # against any other env

set -euo pipefail

BASE_URL="${S15_BASE_URL:-https://app.dealgateapp.com}"
E2E_SECRET_ID="${S15_E2E_SECRET_ID:-officeapp-dev-e2e-user}"
AWS_REGION_="${AWS_REGION:-us-east-2}"
RUN_TAG="smoke $(date -u +%Y%m%dT%H%M%SZ)"
FIXTURE_FILE="${S17_FIXTURE_FILE:-docs/reports/s15/input/Peppermill_Casino_AI_Assessment_SOW.docx}"

log() { printf '[smoke] %s\n' "$*" >&2; }
fail() { printf '[smoke] FAIL: %s\n' "$*" >&2; exit 1; }

# S18 §1: tag-based cleanup + hard gate. Every exit path (success, fail,
# early crash) sweeps the run's own tag first, then invokes the gate
# script which fails the run if any e2e/smoke row survives anywhere on
# staging. Nothing test-tagged is allowed to persist after a smoke run.
export RUN_TAG
GATE_SCRIPT="$(cd "$(dirname "$0")" && pwd)/check-test-data-clean.sh"
cleanup() {
  status=$?
  if [ -n "${AUTH_H+x}" ]; then
    local body ids id
    body=$(curl -sS -o - "${AUTH_H[@]}" "$BASE_URL/api/clients?size=200" || echo '{}')
    ids=$(printf '%s' "$body" | python3 -c "
import json, sys, os
tag = os.environ.get('RUN_TAG', '')
try:
  data = json.load(sys.stdin)
except Exception:
  sys.exit(0)
for c in data.get('items', []):
  if tag and tag in (c.get('name') or ''):
    print(c['id'])
" || true)
    for id in $ids; do
      log "cleanup · DELETE client $id"
      curl -sS -o /dev/null -X DELETE "${AUTH_H[@]}" \
        "$BASE_URL/api/clients/$id?reason=smoke%20teardown" || true
    done
  fi
  if [ -x "$GATE_SCRIPT" ]; then
    if ! "$GATE_SCRIPT"; then
      log "gate FAIL — a test-tagged row survived the run"
      status=1
    fi
  fi
  exit "$status"
}
trap cleanup EXIT

log "target: $BASE_URL"
log "run tag: $RUN_TAG"

# ---- Step 0: mint an ID token for the e2e user via Cognito ---------------
log "step 0 · mint Cognito token for e2e user"
CREDS_JSON=$(aws --region "$AWS_REGION_" secretsmanager get-secret-value \
  --secret-id "$E2E_SECRET_ID" --query SecretString --output text 2>/dev/null || true)
[ -n "$CREDS_JSON" ] || fail "cannot read Secrets Manager $E2E_SECRET_ID"
POOL=$(printf '%s' "$CREDS_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["user_pool_id"])')
CLIENT=$(printf '%s' "$CREDS_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["client_id"])')
USER=$(printf '%s' "$CREDS_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["username"])')
PASS=$(printf '%s' "$CREDS_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])')
AUTH_JSON=$(aws --region "$AWS_REGION_" cognito-idp admin-initiate-auth \
  --user-pool-id "$POOL" --client-id "$CLIENT" \
  --auth-flow ADMIN_USER_PASSWORD_AUTH \
  --auth-parameters USERNAME="$USER",PASSWORD="$PASS" 2>/dev/null || true)
[ -n "$AUTH_JSON" ] || fail "cognito admin_initiate_auth failed"
ID_TOKEN=$(printf '%s' "$AUTH_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["AuthenticationResult"]["IdToken"])')
[ -n "$ID_TOKEN" ] || fail "no IdToken in cognito response"
AUTH_H=(-H "Authorization: Bearer $ID_TOKEN")

# ---- Step 0.5 · S19 slice 1 single-truth grep gate (C8/F3) ---------------
# Every router that lists deals routes through
# app/services/hubspot_pipeline.py. Local grep runs before any curl.
log "step 0.5 · single-truth grep gate"
"$(cd "$(dirname "$0")" && pwd)/check-single-query-service.sh" \
  || fail "single-query-service gate failed"

# ---- Step 1: liveness ----------------------------------------------------
log "step 1 · /healthz"
code=$(curl -sS -o /dev/null -w '%{http_code}' "$BASE_URL/api/healthz" || true)
[ "$code" = "200" ] || fail "healthz returned $code"

# ---- Step 2: extract-model guard proof -----------------------------------
log "step 2 · bedrock inference profile in region"
model_id=$(aws ecs describe-task-definition --task-definition officeapp-dev-api \
  --query 'taskDefinition.containerDefinitions[0].environment[?name==`SOW_EXTRACT_MODEL_ID`].value | [0]' \
  --output text 2>/dev/null || true)
[ -n "$model_id" ] && [ "$model_id" != "None" ] || fail "task-def does not set SOW_EXTRACT_MODEL_ID"
live=$(aws bedrock list-inference-profiles --region us-east-2 \
  --query "inferenceProfileSummaries[?inferenceProfileId==\`$model_id\`].inferenceProfileId | [0]" \
  --output text 2>/dev/null || true)
[ "$live" = "$model_id" ] || fail "SOW_EXTRACT_MODEL_ID=$model_id is not a live Bedrock profile"

# ---- Step 3: upload a fresh Peppermill fixture ---------------------------
# Append 64 random bytes so the file_hash is unique every run — otherwise
# the dedupe short-circuit returns whichever stale job first uploaded
# these bytes, and the smoke reads someone else's extract_status.
[ -f "$FIXTURE_FILE" ] || fail "fixture file $FIXTURE_FILE missing"
UNIQUE_FILE=$(mktemp -t smoke-fixture-XXXXXX.docx)
cat "$FIXTURE_FILE" > "$UNIQUE_FILE"
head -c 64 /dev/urandom >> "$UNIQUE_FILE"
log "step 3 · POST /sows/upload"
UPLOAD_JSON=$(curl -sS -X POST "${AUTH_H[@]}" \
  -F "file=@${UNIQUE_FILE};type=application/vnd.openxmlformats-officedocument.wordprocessingml.document;filename=smoke-${RUN_TAG// /_}.docx" \
  "$BASE_URL/api/sows/upload" || true)
rm -f "$UNIQUE_FILE"
JOB_ID=$(printf '%s' "$UPLOAD_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("job_id",""))')
[ -n "$JOB_ID" ] || fail "upload failed: $(printf '%s' "$UPLOAD_JSON" | head -c 300)"

log "step 4 · POST /sows/jobs/$JOB_ID/pick (create_new: $RUN_TAG)"
PICK_JSON=$(curl -sS -X POST "${AUTH_H[@]}" \
  -H "Content-Type: application/json" \
  -d "{\"create_new\":{\"legal_name\":\"smoke ${RUN_TAG}\",\"domain\":null,\"address_lines\":[]}}" \
  "$BASE_URL/api/sows/jobs/$JOB_ID/pick" || true)

# Poll until done
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  sleep 2
  JOB_STATUS=$(curl -sS "${AUTH_H[@]}" "$BASE_URL/api/sows/jobs/$JOB_ID" || true)
  st=$(printf '%s' "$JOB_STATUS" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status",""))' 2>/dev/null || echo "")
  case "$st" in
    done)
      OPP_ID=$(printf '%s' "$JOB_STATUS" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("opportunity_id",""))')
      SOW_VERSION_ID=$(printf '%s' "$JOB_STATUS" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("sow_version_id",""))')
      break
      ;;
    failed)
      fail "sow upload job failed: $(printf '%s' "$JOB_STATUS" | head -c 400)"
      ;;
  esac
done
[ -n "${OPP_ID:-}" ] || fail "job never reached done"
CONFIRM=$(curl -sS "${AUTH_H[@]}" "$BASE_URL/api/sow/$OPP_ID/confirmation" || true)
CLIENT_ID_TO_DELETE=$(printf '%s' "$CONFIRM" | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d.get("source",{}) or {}).get("client",{}).get("id") or (d.get("opportunity") or {}).get("client_id") or "")')

# ---- Step 5: verify the extract landed complete --------------------------
log "step 5 · confirmation.extract_status"
extract_status=$(printf '%s' "$CONFIRM" | python3 -c 'import json,sys; print(json.load(sys.stdin)["sow_version"]["extract_status"])')
[ "$extract_status" = "complete" ] || fail "extract_status=$extract_status (expected complete)"

# ---- Step 6: draft SOW list responds -------------------------------------
log "step 6 · GET /sows/drafts?mine=false"
status=$(curl -sS -o /dev/null -w '%{http_code}' \
  "${AUTH_H[@]}" \
  "$BASE_URL/api/sows/drafts?mine=false" || true)
[ "$status" = "200" ] || fail "drafts list returned $status"

log "GREEN — deploy is safe to keep. (cleanup + gate run next)"
