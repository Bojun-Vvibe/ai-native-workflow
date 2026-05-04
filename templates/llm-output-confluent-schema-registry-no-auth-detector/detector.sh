#!/usr/bin/env bash
# detector.sh — flag Confluent Schema Registry configs that leave the REST
# API unauthenticated (no authentication.method, NONE, or no realm wired).
# Usage: detector.sh <file> [<file>...]
# Output: one FLAG line per finding. Always exits 0.

set -u

flag() {
  printf 'FLAG %s %s:%s %s\n' "$1" "$2" "$3" "$4"
}

scan_file() {
  local f="$1"
  [ -r "$f" ] || return 0

  # Signal 1: explicit authentication.method=NONE (or none / "")
  grep -nE '^[[:space:]]*authentication\.method[[:space:]]*=[[:space:]]*(NONE|none|"")[[:space:]]*$' "$f" 2>/dev/null \
    | while IFS=: read -r ln rest; do
        flag S1 "$f" "$ln" "$rest"
      done

  # Signal 2: listeners on http:// bound to 0.0.0.0 or wildcard with no
  # authentication.method line anywhere in the file.
  if grep -nE '^[[:space:]]*listeners[[:space:]]*=[[:space:]]*http://(0\.0\.0\.0|\[::\]|[^/]*0\.0\.0\.0)' "$f" >/dev/null 2>&1 \
     && ! grep -E '^[[:space:]]*authentication\.method[[:space:]]*=[[:space:]]*(BASIC|basic)' "$f" >/dev/null 2>&1; then
    grep -nE '^[[:space:]]*listeners[[:space:]]*=[[:space:]]*http://(0\.0\.0\.0|\[::\]|[^/]*0\.0\.0\.0)' "$f" 2>/dev/null \
      | while IFS=: read -r ln rest; do
          flag S2 "$f" "$ln" "$rest"
        done
  fi

  # Signal 3: docker/compose env SCHEMA_REGISTRY_AUTHENTICATION_METHOD=NONE
  grep -nE 'SCHEMA_REGISTRY_AUTHENTICATION_METHOD[[:space:]]*[:=][[:space:]]*"?(NONE|none|"")"?' "$f" 2>/dev/null \
    | while IFS=: read -r ln rest; do
        flag S3 "$f" "$ln" "$rest"
      done

  # Signal 4: confluent.schema.registry.auth.basic.enabled=false (downstream
  # client / proxy disabling the basic check).
  grep -nE '^[[:space:]]*(schema\.registry\.basic\.auth\.credentials\.source[[:space:]]*=[[:space:]]*$|basic\.auth\.credentials\.source[[:space:]]*=[[:space:]]*$|schema_registry\.basic_auth\.enabled[[:space:]]*[:=][[:space:]]*false)' "$f" 2>/dev/null \
    | while IFS=: read -r ln rest; do
        flag S4 "$f" "$ln" "$rest"
      done
}

for f in "$@"; do
  scan_file "$f"
done
exit 0
