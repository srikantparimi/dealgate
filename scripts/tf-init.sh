#!/usr/bin/env bash
# CLAUDE.md rule 15: guarded wrapper for `terraform init`.
#
# S14a.1 migrated the DealGate state from local `terraform.tfstate` into
# S3 + a DynamoDB lock table. The post-migration step in the ADR was
# "delete the local `terraform.tfstate*` files". On operator laptops
# where that never happened, a subsequent `terraform init -reconfigure`
# prompts:
#   "Do you want to overwrite the state in the new backend with the
#   previous state?"
# and defaults to no meaningful default — an answer of "yes" copies the
# stale local file up to S3, which is exactly the incident recorded in
# `docs/reports/s19-1-progress.md` §"Incident during I1".
#
# This wrapper refuses to run `terraform init` when any local
# `terraform.tfstate*` file sits in `infra-tf/`. Rename the file to
# `.stale.bak` (or delete it) before re-running.
#
# Any argument passed to this script is forwarded to `terraform init`.

set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
TF_DIR="${REPO_ROOT}/infra-tf"

if [ ! -d "${TF_DIR}" ]; then
    echo "error: ${TF_DIR} not found" >&2
    exit 2
fi

# Find every terraform.tfstate* file that is NOT a .stale.bak sibling.
# `find -maxdepth 1` — no traversal into modules or the bootstrap root.
# Portable to macOS system bash (3.2, no mapfile) — collect via a
# command substitution + newline-safe count.
stale=$(find "${TF_DIR}" -maxdepth 1 -type f -name 'terraform.tfstate*' \
    ! -name '*.stale.bak' -print)

if [ -n "${stale}" ]; then
    echo "" >&2
    echo "rule 15 · refusing terraform init: local state files exist in ${TF_DIR}:" >&2
    printf '  - %s\n' ${stale} >&2
    echo "" >&2
    echo "The S14a.1 ADR moved state to the S3 backend; these local files" >&2
    echo "are stale. If you run \`terraform init -reconfigure\` with them" >&2
    echo "present, terraform will prompt to migrate them up — and answering" >&2
    echo "yes overwrites the real S3 state." >&2
    echo "" >&2
    echo "Fix (pick one):" >&2
    echo "  mv terraform.tfstate terraform.tfstate.stale.bak" >&2
    echo "  # or, once you've confirmed S3 is authoritative, rm terraform.tfstate*" >&2
    echo "" >&2
    exit 1
fi

cd "${TF_DIR}"
echo "rule 15 · no local state files present; forwarding to terraform init $*" >&2
exec terraform init "$@"
