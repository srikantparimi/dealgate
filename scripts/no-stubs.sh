#!/usr/bin/env bash
# CLAUDE.md rule 11 — no "not wired" throwers.
# Fails the build if any of the forbidden phrases appear in shipped code.

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
    -e 'not wired' \
    -e 'TODO:? stub' \
    -e 'Not implemented' \
    -e 'Follow-up story' \
    -e 'sizable but the right shape' \
    -e 'the right approach is to' \
    "${ROOT}" 2>/dev/null || true
)

if [ -n "${HITS}" ]; then
  printf 'CLAUDE.md rule 11: forbidden stub language detected.\n\n'
  printf '%s\n' "${HITS}"
  printf '\nBuild the path or delete the button.\n'
  exit 1
fi

printf 'no-stubs: clean\n'
