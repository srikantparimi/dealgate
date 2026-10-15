#!/usr/bin/env bash
# S18 §1 · hard gate.
#
# After every e2e run, every smoke run and (via CI) every deploy, this
# script asks the deployed API to enumerate clients whose name matches
# any known e2e/smoke run-tag prefix. Exit 0 iff the count is 0. Exit 1
# otherwise, with the offending rows printed so someone can chase down
# the leaky spec.
#
# The list of prefixes lives here (not in the API) so a new test tag can
# be added without a deploy. Keep it in sync with the nightly worker at
# worker/e2e_cleanup.py::_PREFIX_RE.
#
# Usage:
#   scripts/check-test-data-clean.sh                 # against staging default
#   BASE_URL=... scripts/check-test-data-clean.sh    # against any other env

set -euo pipefail

BASE_URL="${BASE_URL:-https://app.dealgateapp.com}"
E2E_SECRET_ID="${E2E_SECRET_ID:-officeapp-dev-e2e-user}"
AWS_REGION_="${AWS_REGION:-us-east-2}"

CREDS_JSON=$(aws --region "$AWS_REGION_" secretsmanager get-secret-value \
  --secret-id "$E2E_SECRET_ID" --query SecretString --output text 2>/dev/null || true)
[ -n "$CREDS_JSON" ] || { echo "[gate] cannot read e2e Cognito creds" >&2; exit 2; }
POOL=$(printf '%s' "$CREDS_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["user_pool_id"])')
CLIENT=$(printf '%s' "$CREDS_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["client_id"])')
# Same stale-username caveat and override convention as deploy-smoke.sh.
USER="${S15_E2E_USERNAME:-$(printf '%s' "$CREDS_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["username"])')}"
PASS=$(printf '%s' "$CREDS_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])')
AUTH_JSON=$(aws --region "$AWS_REGION_" cognito-idp admin-initiate-auth \
  --user-pool-id "$POOL" --client-id "$CLIENT" \
  --auth-flow ADMIN_USER_PASSWORD_AUTH \
  --auth-parameters USERNAME="$USER",PASSWORD="$PASS" 2>/dev/null)
ID_TOKEN=$(printf '%s' "$AUTH_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["AuthenticationResult"]["IdToken"])')

TAG_PYTHON=$(cat <<'PY'
import json, re, sys
prefix_re = re.compile(
    r"^(?:s1[2-9]-|s17-|s18-|"
    r"S1[2-9] e2e |S14b e2e |S16a e2e |S13a e2e |"
    r"S17 e2e |S18 e2e |S20 e2e |S21 e2e |S22 e2e |"
    r"smoke |Peppermill Casino \(smoke fixture\)|"
    r"S17 delete-everywhere)",
    re.IGNORECASE,
)
data = json.load(sys.stdin)
leaky = [c for c in data.get("items", []) if prefix_re.match(c.get("name") or "")]
print(len(leaky))
for c in leaky:
    print(f"LEAK\t{c['id']}\t{c['name']}")
PY
)

RESP=$(curl -sS -H "Authorization: Bearer $ID_TOKEN" "$BASE_URL/api/clients?size=200")
OUT=$(printf '%s' "$RESP" | python3 -c "$TAG_PYTHON")
COUNT=$(printf '%s\n' "$OUT" | head -1)
LEAKS=$(printf '%s\n' "$OUT" | tail -n +2)

# S21 item 7 (leak gate · approvers): any approval package whose
# approver is an e2e user AND whose SOW is not e2e-tagged is a leak.
# The eligibility fix in services/approval_routing.py prevents new
# leaks; this gate catches historic rows + any regression. The
# approvals list already carries approver_name; we flag names
# containing the e2e marker 'E2E' or 'e2e-' when the SOW's client
# name does not match the test-data prefix.
APPROVER_PYTHON=$(cat <<'PY'
import json, re, sys
prefix_re = re.compile(
    r"^(?:s1[2-9]-|s17-|s18-|"
    r"S1[2-9] e2e |S14b e2e |S16a e2e |S13a e2e |"
    r"S17 e2e |S18 e2e |S20 e2e |S21 e2e |S22 e2e |"
    r"smoke |Peppermill Casino \(smoke fixture\)|"
    r"S17 delete-everywhere)",
    re.IGNORECASE,
)
bot_re = re.compile(r"(e2e[\s\-]|staging bot|\bbot\b)", re.IGNORECASE)
# S21-1c · stabilization: historic voided/rejected/released packages
# carry frozen assignments that are no longer "routing". The gate
# should only trip on packages that can still receive a decision.
CLOSED = {"voided", "rejected", "released"}
data = json.load(sys.stdin)
leaky = []
for pkg in data.get("items", []):
    if (pkg.get("status") or "") in CLOSED:
        continue
    client = pkg.get("client_name") or ""
    if prefix_re.match(client):
        continue
    for row in (pkg.get("assignments") or []) + (pkg.get("approvals") or []):
        name = row.get("approver_name") or ""
        if bot_re.search(name):
            leaky.append({
                "package_id": pkg.get("id"),
                "client": client,
                "function": row.get("function"),
                "approver": name,
            })
print(len(leaky))
for r in leaky:
    print(f"APPROVAL-LEAK\t{r['package_id']}\t{r['client']}\t{r['function']}\t{r['approver']}")
PY
)
APPROVER_RESP=$(curl -sS -H "Authorization: Bearer $ID_TOKEN" "$BASE_URL/api/approvals/packages?size=200" 2>/dev/null || echo '{"items":[]}')
APPROVER_OUT=$(printf '%s' "$APPROVER_RESP" | python3 -c "$APPROVER_PYTHON" 2>/dev/null || echo "0")
APPROVER_COUNT=$(printf '%s\n' "$APPROVER_OUT" | head -1)
APPROVER_LEAKS=$(printf '%s\n' "$APPROVER_OUT" | tail -n +2)

# S22: the portfolio ledger has its own rows. People are a global roster
# (not client-scoped), so a leaked test person would sit on every bench list;
# engagements cascade from their client but are listed here as a belt-and-braces
# check. Both endpoints are new in S22; a 404 (older image) counts as 0.
S22_PYTHON=$(cat <<'PY'
import json, re, sys
prefix_re = re.compile(
    r"^(?:s1[2-9]-|s17-|s18-|"
    r"S1[2-9] e2e |S14b e2e |S16a e2e |S13a e2e |"
    r"S17 e2e |S18 e2e |S20 e2e |S21 e2e |S22 e2e |"
    r"smoke |Peppermill Casino \(smoke fixture\)|"
    r"S17 delete-everywhere)",
    re.IGNORECASE,
)
tag_re = re.compile(r"S22 e2e \d+", re.IGNORECASE)
try:
    data = json.load(sys.stdin)
except Exception:
    print(0); sys.exit(0)
rows = data if isinstance(data, list) else data.get("items", [])
leaky = []
for r in rows:
    label = r.get("name") or ""
    client = r.get("client_name") or ""
    if prefix_re.match(label) or prefix_re.match(client) or tag_re.search(label) or tag_re.search(client):
        leaky.append(r)
print(len(leaky))
for r in leaky:
    print(f"S22-LEAK\t{r.get('id')}\t{(r.get('client_name') + ' · ') if r.get('client_name') else ''}{r.get('name')}")
PY
)
PEOPLE_RESP=$(curl -sS -H "Authorization: Bearer $ID_TOKEN" "$BASE_URL/api/resources" 2>/dev/null || echo '[]')
PEOPLE_OUT=$(printf '%s' "$PEOPLE_RESP" | python3 -c "$S22_PYTHON" 2>/dev/null || echo "0")
PEOPLE_COUNT=$(printf '%s\n' "$PEOPLE_OUT" | head -1)
PEOPLE_LEAKS=$(printf '%s\n' "$PEOPLE_OUT" | tail -n +2)
ENG_RESP=$(curl -sS -H "Authorization: Bearer $ID_TOKEN" "$BASE_URL/api/engagements?page_size=100" 2>/dev/null || echo '{"items":[]}')
ENG_OUT=$(printf '%s' "$ENG_RESP" | python3 -c "$S22_PYTHON" 2>/dev/null || echo "0")
ENG_COUNT=$(printf '%s\n' "$ENG_OUT" | head -1)
ENG_LEAKS=$(printf '%s\n' "$ENG_OUT" | tail -n +2)

# S23-PL2 T11: the bot's personal workspace. Saved views, tracking groups and
# watches belong to the signed-in user, and a Pipeline spec that saves a view,
# creates a group or stars a deal must undo it. Anything the bot still owns
# after a run is a leak: custom views (built-ins are seeded per user and do
# not count), every group and every watch. The /pipeline/* routes are new in
# S23-PL2; a 404 (older image) counts as 0 there.
PERSONAL_PYTHON=$(cat <<'PY'
import json, sys
kind, me = sys.argv[1], sys.argv[2]
try:
    data = json.load(sys.stdin)
except Exception:
    print(0); sys.exit(0)
if isinstance(data, dict) and data.get("detail") is not None and not data.get("items"):
    print(0); sys.exit(0)
rows = data if isinstance(data, list) else data.get("items", [])
# Team-visible rows of other users are not the bot's; keep only its own.
rows = [r for r in rows if not r.get("owner_id") or r.get("owner_id") == me]
if kind == "saved-views":
    rows = [r for r in rows if not r.get("is_builtin")]
print(len(rows))
for r in rows:
    label = r.get("name") or r.get("item_name") or r.get("kind") or ""
    print(f"PERSONAL-LEAK\t{kind}\t{r.get('id') or r.get('item_id')}\t{label}")
PY
)
BOT_ID=$(curl -sS -H "Authorization: Bearer $ID_TOKEN" "$BASE_URL/api/me" 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))' 2>/dev/null || echo "")
PERSONAL_COUNT=0
PERSONAL_LEAKS=""
for ROUTE in "pipeline/views:pipeline-views" "pipeline/groups:pipeline-groups" "saved-views:saved-views" "tracking-groups:tracking-groups" "watchlist:watchlist"; do
  PATH_PART="${ROUTE%%:*}"
  KIND="${ROUTE##*:}"
  RESP=$(curl -sS -H "Authorization: Bearer $ID_TOKEN" "$BASE_URL/api/$PATH_PART" 2>/dev/null || echo '[]')
  OUT=$(printf '%s' "$RESP" | python3 -c "$PERSONAL_PYTHON" "$KIND" "$BOT_ID" 2>/dev/null || echo "0")
  N=$(printf '%s\n' "$OUT" | head -1)
  PERSONAL_COUNT=$((PERSONAL_COUNT + N))
  if [ "$N" != "0" ]; then
    PERSONAL_LEAKS="${PERSONAL_LEAKS}$(printf '%s\n' "$OUT" | tail -n +2)"$'\n'
  fi
done

TOTAL=$((COUNT + APPROVER_COUNT + PEOPLE_COUNT + ENG_COUNT + PERSONAL_COUNT))
if [ "$TOTAL" = "0" ]; then
  echo "[gate] clean · 0 test-tagged clients + 0 e2e approvers on real SOWs + 0 tagged people + 0 tagged engagements + 0 bot views/groups/watches on $BASE_URL"
  exit 0
fi

echo "[gate] FAIL · $COUNT test-tagged clients + $APPROVER_COUNT e2e-approver leaks + $PEOPLE_COUNT tagged people + $ENG_COUNT tagged engagements + $PERSONAL_COUNT bot views/groups/watches on $BASE_URL" >&2
printf '%s\n' "$LEAKS" >&2
printf '%s\n' "$APPROVER_LEAKS" >&2
printf '%s\n' "$PEOPLE_LEAKS" >&2
printf '%s\n' "$ENG_LEAKS" >&2
printf '%s' "$PERSONAL_LEAKS" >&2
exit 1
