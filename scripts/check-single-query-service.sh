#!/usr/bin/env bash
# S19 slice 1 C8/F3: single-truth guarantee.
#
# Every router that lists opportunities routes through
# `api/app/services/hubspot_pipeline.py`. Grep-fail the build if any
# other module in `api/app/routers/` runs `select(Opportunity)` for
# listing — that path silently forks the query surface and breaks the
# Command center ↔ Pipeline ↔ SOW picker consistency contract (F1/F2).
#
# Allowed exemptions:
# - services/hubspot_pipeline.py itself (the single truth)
# - services/hubspot_backfill.py, services/hubspot_intake.py,
#   services/hubspot_reconcile.py, services/hubspot_writeback.py:
#     these WRITE opportunities (upsert), which is a legitimate
#     select(Opportunity) → merge path, not a list query.
# - services/deals.py, services/sow_*.py, services/dashboards.py etc.:
#     select single opportunities for detail/edit; not list surfaces.
#     These are permitted because they never render a paged deal list;
#     see the F1/F2 test for the contract that guards them.

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ROUTER_DIR="${REPO_ROOT}/api/app/routers"

if [ ! -d "${ROUTER_DIR}" ]; then
    echo "error: router directory not found at ${ROUTER_DIR}" >&2
    exit 2
fi

# Grep for `select(Opportunity` (open paren) — this is the SQLAlchemy
# form that starts a query. A list-style query does NOT constrain on
# `Opportunity.id ==` immediately (that pattern is a detail lookup and
# is a separate — permitted — concern). The gate flags list-style
# calls only.
OFFENDERS=$(grep -RIn --include="*.py" 'select(Opportunity' "${ROUTER_DIR}" || true)

# Whitelist:
#   - pipeline.py — routes through the service.
#   - deals.py — legacy path scheduled to migrate.
#   - Any hit that also contains `Opportunity.id ==` (single-row lookup).
FILTERED=$(printf '%s\n' "${OFFENDERS}" | grep -v '/pipeline\.py:' || true)
FILTERED=$(printf '%s\n' "${FILTERED}" | grep -v '/deals\.py:' || true)
FILTERED=$(printf '%s\n' "${FILTERED}" | grep -v 'Opportunity\.id ==' || true)

if [ -n "${FILTERED}" ] && [ "${FILTERED}" != "" ]; then
    echo "S19 slice 1 C8/F3 failure — the following routers select from Opportunity" >&2
    echo "outside the shared hubspot_pipeline service:" >&2
    echo "" >&2
    printf '%s\n' "${FILTERED}" >&2
    echo "" >&2
    echo "Route every list-of-deals view through" >&2
    echo "app/services/hubspot_pipeline.py instead." >&2
    exit 1
fi

echo "single-truth guarantee ok — every router lists deals through hubspot_pipeline"
