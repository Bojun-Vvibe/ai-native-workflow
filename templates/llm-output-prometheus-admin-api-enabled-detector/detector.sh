#!/usr/bin/env bash
# detector.sh — flag Prometheus configs that enable admin / lifecycle APIs
# without an external auth layer.
# Usage: detector.sh <file> [<file>...]
# Output: one FLAG line per finding. Always exits 0.

set -u

flag() {
  printf 'FLAG %s %s:%s %s\n' "$1" "$2" "$3" "$4"
}

scan_file() {
  local f="$1"
  [ -r "$f" ] || return 0

  # Signal 1: --web.enable-admin-api
  grep -nE -- '--web\.enable-admin-api(=true)?($|[[:space:]"\\])' "$f" 2>/dev/null \
    | while IFS=: read -r ln rest; do
        flag S1 "$f" "$ln" "$rest"
      done

  # Signal 2: --web.enable-lifecycle
  grep -nE -- '--web\.enable-lifecycle(=true)?($|[[:space:]"\\])' "$f" 2>/dev/null \
    | while IFS=: read -r ln rest; do
        flag S2 "$f" "$ln" "$rest"
      done

  # Signal 3: web.listen-address on non-loopback AND admin/lifecycle present
  if grep -E -- '--web\.(enable-admin-api|enable-lifecycle)' "$f" >/dev/null 2>&1; then
    addr_lines=$(grep -nE -- '--web\.listen-address[ =]+["'"'"']?(0\.0\.0\.0|\[::\]|[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+):' "$f" 2>/dev/null \
                 | grep -vE '(127\.|localhost|\[::1\])')
    if [ -n "$addr_lines" ]; then
      while IFS=: read -r ln rest; do
        flag S3 "$f" "$ln" "$rest"
      done <<< "$addr_lines"
    fi
  fi

  # Signal 4: Helm-style YAML keys
  grep -nE '^[[:space:]]*(enableAdminAPI|enableLifecycle)[[:space:]]*:[[:space:]]*true([[:space:]]|$)' "$f" 2>/dev/null \
    | while IFS=: read -r ln rest; do
        flag S4 "$f" "$ln" "$rest"
      done
}

for f in "$@"; do
  scan_file "$f"
done
exit 0
