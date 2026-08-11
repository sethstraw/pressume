#!/usr/bin/env bash
# The verification gate. CI, /verify, and a person all run this.
#
# Every step runs even after one fails, so one pass reports every problem.

set -uo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

FAILED=()

# Records the failure and returns 0, so the caller keeps going.
step() {
  local label="$1"
  shift
  printf '\n== %s\n' "$label"
  if "$@"; then
    return 0
  fi
  printf '\n!! %s failed\n' "$label"
  FAILED+=("$label")
  return 0
}

# --with, so pip-licenses is not a project dependency.
step "licences shippable under MIT" \
  uv run --with pip-licenses python scripts/audit_licenses.py
step "ruff format" uv run ruff format --check src tests scripts
step "ruff check" uv run ruff check src tests scripts
step "mypy" uv run mypy
step "pytest" uv run pytest --cov --cov-report=term-missing

if ((${#FAILED[@]})); then
  printf '\n== gate failed: %s\n' "${FAILED[*]}"
  exit 1
fi

printf '\n== gate passed\n'
