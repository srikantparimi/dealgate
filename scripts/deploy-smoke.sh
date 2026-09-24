#!/usr/bin/env bash
# S15 · Kanna addition 3 — golden-path smoke suite that runs against staging
# after EVERY deploy by anyone. Red blocks the deploy. The extraction step
# of this smoke is precisely what would have caught the fake `claude-opus-5`
# model id on day one.
#
# The smoke drives the full journey via the deployed API endpoints, not
# through a browser — one HTTP client, one canonical document, one green
# / red exit code. Deploy pipelines should invoke it as the last gate
# before flipping traffic (staging today, prod once we have one).
#
# Usage:
#   scripts/deploy-smoke.sh                       # against staging default
#   S15_BASE_URL=... scripts/deploy-smoke.sh      # against any other env
#
# Requirements: AWS creds (bedrock:ListInferenceProfiles for the readiness
# check + s3:GetObject on the SOW bucket for the extract retry). Kills
# the run at the first failing step with a summary of what broke — the
# whole point is one deploy failure instead of N silent uploads.

set -euo pipefail

BASE_URL="${S15_BASE_URL:-https://app.dealgateapp.com}"
FIXTURE_KEY="${S15_FIXTURE_KEY:-sow/63ed09bf-3984-4d9c-a198-d28786e81e24/20260922T193327Z-9c2c7892-Peppermill_Casino_AI_Assessment_SOW.docx.docx}"
FIXTURE_SOW_VERSION_ID="${S15_FIXTURE_SOW_VERSION_ID:-83f1a58d-734f-4af1-b8ac-47b202836e72}"
FIXTURE_OPPORTUNITY_ID="${S15_FIXTURE_OPPORTUNITY_ID:-4aab5ea6-f788-43f8-a2de-c759cfde1004}"
E2E_SECRET_ID="${S15_E2E_SECRET_ID:-officeapp-dev-e2e-user}"
AWS_REGION_="${AWS_REGION:-us-east-2}"

log() { printf '[s15-smoke] %s\n' "$*" >&2; }
fail() { printf '[s15-smoke] FAIL: %s\n' "$*" >&2; exit 1; }

log "target: $BASE_URL"

# ---- Step 0: mint an ID token for the e2e user via Cognito ---------------
# Staging (`DEALGATE_ENV=dev`) does NOT honour the X-Test-User header — the
# API only accepts a real Cognito ID token. Same secret + admin_initiate_auth
# pattern the Playwright staging fixture uses. Local (`DEALGATE_ENV=local`)
# can skip this and set S15_TEST_USER instead.
log "step 0 · mint Cognito token for e2e user"
CREDS_JSON=$(aws --region "$AWS_REGION_" secretsmanager get-secret-value \
  --secret-id "$E2E_SECRET_ID" --query SecretString --output text 2>/dev/null || true)
[ -n "$CREDS_JSON" ] || fail "cannot read Secrets Manager $E2E_SECRET_ID (need e2e user creds)"
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

# ---- Step 1: liveness -----------------------------------------------------
log "step 1 · /healthz"
code=$(curl -sS -o /dev/null -w '%{http_code}' "$BASE_URL/api/healthz" || true)
[ "$code" = "200" ] || fail "healthz returned $code (expected 200)"

# ---- Step 2: extract-model guard proof ------------------------------------
# The API's startup guard passed if we can reach this endpoint at all —
# the bad-id case would have exited uvicorn non-zero and the deploy would
# never have converged. Re-check the same profile list from here so a
# regression that puts a fictional id back is caught even if the guard
# ever gets skipped.
log "step 2 · bedrock inference profile in region"
model_id=$(aws ecs describe-task-definition --task-definition officeapp-dev-api \
  --query 'taskDefinition.containerDefinitions[0].environment[?name==`SOW_EXTRACT_MODEL_ID`].value | [0]' \
  --output text 2>/dev/null || true)
[ -n "$model_id" ] && [ "$model_id" != "None" ] || fail "task-def does not set SOW_EXTRACT_MODEL_ID"
live=$(aws bedrock list-inference-profiles --region us-east-2 \
  --query "inferenceProfileSummaries[?inferenceProfileId==\`$model_id\`].inferenceProfileId | [0]" \
  --output text 2>/dev/null || true)
[ "$live" = "$model_id" ] || fail "SOW_EXTRACT_MODEL_ID=$model_id is not a live Bedrock profile in us-east-2"

# ---- Step 3: extraction runs end-to-end -----------------------------------
# Retry against the canonical fixture SOW. A green re-extract proves the
# API image can (a) read the bytes from S3, (b) call Bedrock, (c) validate
# the response, and (d) persist a `complete` row. The exact failure class
# opus-5 masked as 15 per-field defects.
log "step 3 · POST /sow/versions/$FIXTURE_SOW_VERSION_ID/reextract"
status=$(curl -sS -o /tmp/s15-reextract.json -w '%{http_code}' \
  -X POST "${AUTH_H[@]}" \
  "$BASE_URL/api/sow/versions/$FIXTURE_SOW_VERSION_ID/reextract" || true)
[ "$status" = "200" ] || fail "reextract returned $status (expected 200): $(head -c 400 /tmp/s15-reextract.json)"
extract_status=$(python3 -c "import json,sys; print(json.load(open('/tmp/s15-reextract.json')).get('extract_status'))")
[ "$extract_status" = "complete" ] || fail "extract_status=$extract_status (expected complete)"

# ---- Step 4: confirm page reflects the extract ---------------------------
log "step 4 · GET /sow/$FIXTURE_OPPORTUNITY_ID/confirmation"
status=$(curl -sS -o /tmp/s15-confirm.json -w '%{http_code}' \
  "${AUTH_H[@]}" \
  "$BASE_URL/api/sow/$FIXTURE_OPPORTUNITY_ID/confirmation" || true)
[ "$status" = "200" ] || fail "confirmation returned $status (expected 200)"
sow_status=$(python3 -c "import json; print(json.load(open('/tmp/s15-confirm.json'))['sow_version']['extract_status'])")
[ "$sow_status" = "complete" ] || fail "confirmation.sow_version.extract_status=$sow_status"

# ---- Step 5: draft SOW list responds -------------------------------------
log "step 5 · GET /sows/drafts?mine=false"
status=$(curl -sS -o /dev/null -w '%{http_code}' \
  "${AUTH_H[@]}" \
  "$BASE_URL/api/sows/drafts?mine=false" || true)
[ "$status" = "200" ] || fail "drafts list returned $status"

log "GREEN — deploy is safe to keep."
