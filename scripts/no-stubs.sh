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
  grep -rEn \
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

printf 'no-stubs: clean\n'
