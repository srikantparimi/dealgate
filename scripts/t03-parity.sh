#!/usr/bin/env bash
#
# T03 · SQL parity harness (S20 · W5).
#
# Captures the same deal from every reachable surface (HubSpot source,
# our mirror, list API, client detail API, deal detail API, export CSV)
# and writes each JSON blob under docs/reports/s20/t03-parity/<slug>/.
# The comparison table itself is filled in by hand in
# docs/reports/s20/t03-parity.md — automation here is capture only, so
# an invented value in any layer is caught by human diff.
#
# Requires:
#   - AWS profile lm-arbiter-poc (or STAGING_E2E_PROFILE).
#   - staging Cognito access via Secrets Manager (officeapp-dev-e2e-user).
#   - HubSpot read-only token in Secrets Manager (dealgate/staging/hubspot_token).
#
# Isolation §6 F1 confirms the token is read-only, so the source pull
# cannot mutate HubSpot. The API + mirror queries are equally read-only.
#
# Usage:
#   scripts/t03-parity.sh "BSC Staffing - UX/UI Designer"
#   scripts/t03-parity.sh --list       # print candidate names
set -euo pipefail

PROFILE="${STAGING_E2E_PROFILE:-lm-arbiter-poc}"
REGION="${STAGING_E2E_REGION:-us-east-2}"
BASE="${E2E_BASE_URL:-https://app.dealgateapp.com}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_ROOT="$REPO_ROOT/docs/reports/s20/t03-parity"
mkdir -p "$OUT_ROOT"

usage() {
  cat <<'USAGE'
Usage:
  scripts/t03-parity.sh "<deal name>"     capture one deal's parity blobs
  scripts/t03-parity.sh --list            list candidate deal names from the list API
Environment:
  STAGING_E2E_PROFILE  (default: lm-arbiter-poc)
  STAGING_E2E_REGION   (default: us-east-2)
  E2E_BASE_URL         (default: https://app.dealgateapp.com)
USAGE
}

if [[ $# -eq 0 ]]; then
  usage
  exit 1
fi

get_secret() {
  aws --profile "$PROFILE" --region "$REGION" \
    secretsmanager get-secret-value --secret-id "$1" \
    --query SecretString --output text
}

mint_access_token() {
  local blob; blob="$(get_secret officeapp-dev-e2e-user)"
  local pool client user pass
  pool=$(jq -r .user_pool_id <<<"$blob")
  client=$(jq -r .client_id <<<"$blob")
  user=$(jq -r .username <<<"$blob")
  pass=$(jq -r .password <<<"$blob")
  aws --profile "$PROFILE" --region "$REGION" cognito-idp admin-initiate-auth \
    --user-pool-id "$pool" --client-id "$client" \
    --auth-flow ADMIN_USER_PASSWORD_AUTH \
    --auth-parameters "USERNAME=$user,PASSWORD=$pass" \
    --query AuthenticationResult.AccessToken --output text
}

hubspot_token() {
  local blob; blob="$(get_secret dealgate/staging/hubspot_token)"
  # Secret is either raw string or JSON with `token` / `HUBSPOT_TOKEN`.
  if jq -e . >/dev/null 2>&1 <<<"$blob"; then
    jq -r '.token // .HUBSPOT_TOKEN // .' <<<"$blob"
  else
    printf '%s' "$blob"
  fi
}

if [[ "$1" == "--list" ]]; then
  ACCESS="$(mint_access_token)"
  curl -sS -H "Authorization: Bearer $ACCESS" \
    "$BASE/api/pipeline/opportunities?page_size=100" |
    jq -r '.items[]? | "\(.name // .hubspot_deal_id)\t\(.client_name)\t\(.owner_name // "-")"'
  exit 0
fi

DEAL_NAME="$1"
SLUG="$(echo "$DEAL_NAME" | tr '[:upper:]' '[:lower:]' | tr -c '[:alnum:]' '-' | sed 's/-\+/-/g;s/^-//;s/-$//')"
OUT_DIR="$OUT_ROOT/$SLUG"
mkdir -p "$OUT_DIR"

echo "==> capturing parity for: $DEAL_NAME"
echo "    output: $OUT_DIR"

ACCESS="$(mint_access_token)"
HS_TOKEN="$(hubspot_token)"

# 1. List API (pipeline surface used by /pipeline SPA).
echo "==> [1/6] list API"
curl -sS -H "Authorization: Bearer $ACCESS" \
  "$BASE/api/pipeline/opportunities?search=$(python3 -c "import urllib.parse;import sys;print(urllib.parse.quote(sys.argv[1]))" "$DEAL_NAME")&page_size=25" \
  > "$OUT_DIR/1-list.json"

# Extract the matching row's ids for downstream lookups.
OPP_ID=$(jq -r --arg n "$DEAL_NAME" '.items[]? | select(.name==$n or (.name|test($n; "i"))) | .opportunity_id' "$OUT_DIR/1-list.json" | head -n 1 || true)
CLIENT_ID=$(jq -r --arg n "$DEAL_NAME" '.items[]? | select(.name==$n or (.name|test($n; "i"))) | .client_id' "$OUT_DIR/1-list.json" | head -n 1 || true)
HUBSPOT_DEAL_ID=$(jq -r --arg n "$DEAL_NAME" '.items[]? | select(.name==$n or (.name|test($n; "i"))) | .hubspot_deal_id' "$OUT_DIR/1-list.json" | head -n 1 || true)

if [[ -z "$OPP_ID" || "$OPP_ID" == "null" ]]; then
  echo "!! opportunity_id not found in list response for name: $DEAL_NAME"
  echo "   dumping list.json summary:"
  jq -r '.items[]? | "\(.hubspot_deal_id)\t\(.name)\t\(.client_name)"' "$OUT_DIR/1-list.json" | head -20
  exit 2
fi

echo "    opportunity_id: $OPP_ID"
echo "    client_id:      $CLIENT_ID"
echo "    hubspot_deal_id: $HUBSPOT_DEAL_ID"

# 2. HubSpot source of truth (read-only).
echo "==> [2/6] HubSpot source (read-only)"
curl -sS -H "Authorization: Bearer $HS_TOKEN" \
  "https://api.hubapi.com/crm/v3/objects/deals/${HUBSPOT_DEAL_ID}?properties=dealname,pipeline,dealstage,amount,closedate,hubspot_owner_id,dealstage,hs_deal_stage_probability,industry" \
  > "$OUT_DIR/2-hubspot.json"

# 3. Mirror table via internal /api/dev/mirror (read-only if exposed on staging).
echo "==> [3/6] Mirror row (via /api/dev/mirror)"
curl -sS -H "Authorization: Bearer $ACCESS" \
  "$BASE/api/dev/mirror/opportunities/${OPP_ID}" \
  > "$OUT_DIR/3-mirror.json" || echo "    (mirror endpoint not exposed; W1 to add)" > "$OUT_DIR/3-mirror.json"

# 4. Client detail.
echo "==> [4/6] Client detail"
curl -sS -H "Authorization: Bearer $ACCESS" \
  "$BASE/api/clients/${CLIENT_ID}" \
  > "$OUT_DIR/4-client.json"

# 5. Deal detail.
echo "==> [5/6] Deal detail"
curl -sS -H "Authorization: Bearer $ACCESS" \
  "$BASE/api/pipeline/opportunities/${OPP_ID}" \
  > "$OUT_DIR/5-deal.json"

# 6. Export CSV.
echo "==> [6/6] Export CSV"
curl -sS -H "Authorization: Bearer $ACCESS" \
  "$BASE/api/pipeline/opportunities/export.csv?search=$(python3 -c "import urllib.parse;import sys;print(urllib.parse.quote(sys.argv[1]))" "$DEAL_NAME")" \
  > "$OUT_DIR/6-export.csv" || echo "    (export endpoint not exposed; W2 to add)" > "$OUT_DIR/6-export.csv"

echo
echo "captured. next: fill in the parity table in"
echo "  docs/reports/s20/t03-parity.md"
echo "  (one row per field × one column per source, human-diff to catch invented values)"
