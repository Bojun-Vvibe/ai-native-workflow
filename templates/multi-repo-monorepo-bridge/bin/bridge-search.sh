#!/usr/bin/env bash
# bridge-search.sh — ripgrep across the bridge with shared ignores.
# Usage: bridge-search.sh <pattern> [<bridge-root>] [-- <rg-extra-args>]
set -eu

if [ $# -lt 1 ]; then
  echo "usage: bridge-search.sh <pattern> [<bridge-root>] [-- <rg-args>]" >&2
  exit 2
fi

pattern="$1"; shift
bridge="${1:-$PWD}"
[ -d "$bridge" ] || { echo "no such bridge: $bridge" >&2; exit 2; }

# Shift past bridge if it was supplied.
if [ $# -gt 0 ] && [ "$1" = "$bridge" ]; then shift; fi
# Allow extra args after `--`.
extra=()
if [ $# -gt 0 ] && [ "$1" = "--" ]; then
  shift
  extra=("$@")
fi

if ! command -v rg >/dev/null 2>&1; then
  echo "[bridge-search] ripgrep (rg) not installed" >&2
  exit 4
fi

# Standard ignores. Keep in sync with MANIFEST.toml [ignore].globs.
IGNORE_ARGS=(
  --glob '!node_modules/**'
  --glob '!target/**'
  --glob '!dist/**'
  --glob '!.venv/**'
  --glob '!__pycache__/**'
  --glob '!.tox/**'
  --glob '!.gradle/**'
  --glob '!.next/**'
  --glob '!build/**'
  --glob '!Pods/**'
)

# rg follows symlinks with -L. Each child repo lives behind one.
exec rg -L -n --no-heading --color=never "${IGNORE_ARGS[@]}" "${extra[@]}" -- "$pattern" "$bridge"
