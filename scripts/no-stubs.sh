#!/usr/bin/env bash
# CLAUDE.md rule 11 — no "not wired" throwers.
# Fails the build if any of the forbidden phrases appear in shipped code.
#
# S10-04: the original pattern list missed the one that mattered most.
# `BedrockSowExtract.extract` shipped to production returning
# ManualRequired("bedrock caller not yet implemented"), with the docstring
# "the real Bedrock call is deferred to a later story" and the comment
# "for now the safe answer is manual" — so every deployed upload silently
# derived nothing. None of those phrases were on the list. They are now.

set -euo pipefail

ROOT="${1:-.}"

HITS=$(
  grep -rEin \
    --include='*.py' \
    --include='*.ts' \
    --include='*.tsx' \
    --include='*.js' \
    --include='*.jsx' \
    --exclude-dir=node_modules \
    --exclude-dir=.venv \
    --exclude-dir=dist \
    --exclude-dir=build \
    --exclude-dir=__pycache__ \
    --exclude-dir=docs \
    --exclude-dir=scripts \
    -e 'not wired' \
    -e 'TODO:? stub' \
    -e 'Not implemented' \
    -e 'Follow-up story' \
    -e 'sizable but the right shape' \
    -e 'the right approach is to' \
    -e 'not yet implemented' \
    -e 'lands in the wave' \
    -e 'lands in a follow-up' \
    -e 'deferred to a later story' \
    -e 'real .* call is deferred' \
    -e 'for now the safe answer' \
    "${ROOT}" 2>/dev/null || true
)

# Filter out known, tracked debt (see scripts/no-stubs-baseline.txt). The
# baseline exists so the pattern list can stay strict: anything NEW still
# fails the build. Tests that *document* a fixed stub bug are also excluded —
# describing the defect is not shipping it.
BASELINE="$(dirname "$0")/no-stubs-baseline.txt"
if [ -f "${BASELINE}" ]; then
  while IFS= read -r path; do
    case "${path}" in ''|\#*) continue ;; esac
    HITS=$(printf '%s\n' "${HITS}" | grep -v "${path}" || true)
  done < "${BASELINE}"
fi
HITS=$(printf '%s\n' "${HITS}" | grep -v '/tests\?/' | grep -v '__tests__' || true)
HITS=$(printf '%s\n' "${HITS}" | sed '/^$/d')

if [ -n "${HITS}" ]; then
  printf 'CLAUDE.md rule 11: forbidden stub language detected.\n\n'
  printf '%s\n' "${HITS}"
  printf '\nBuild the path or delete the button.\n'
  exit 1
fi

# S12 (one-staffing-model.md rule 3): the phantom-roster templates are
# deleted for good. If `auto_staffing.py` ever mentions Architect, Engineer,
# Consultant or Analyst as a role literal again, CI fails. Comments are
# stripped so the deletion story itself can name what was removed.
AUTO_STAFFING="${ROOT}/api/app/services/auto_staffing.py"
if [ -f "${AUTO_STAFFING}" ]; then
  CODE_ONLY=$(python3 -c "
import re,sys,pathlib
t = pathlib.Path('${AUTO_STAFFING}').read_text()
t = re.sub(r'#.*', '', t)
t = re.sub(r'\"\"\"[\s\S]*?\"\"\"', '', t)
sys.stdout.write(t)
")
  BAD_ROLES=$(printf '%s' "${CODE_ONLY}" | grep -oE 'Architect|Engineer|Consultant|Analyst' | sort -u || true)
  if [ -n "${BAD_ROLES}" ]; then
    printf 'no-stubs: phantom role literal detected in auto_staffing.py:\n\n'
    printf '  %s\n' ${BAD_ROLES}
    printf '\nAuto-staffing must never fabricate a role name. See docs/directives/one-staffing-model.md rule 3.\n'
    exit 1
  fi
fi

printf 'no-stubs: clean\n'
