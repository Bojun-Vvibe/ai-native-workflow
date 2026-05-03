#!/usr/bin/env bash
# detect.sh — flag Qdrant configurations / launch scripts that disable the API key:
#   1. config.yaml setting service.api_key to "" / null / commented out
#      while exposing 6333/6334 on a non-loopback host
#   2. docker-compose / k8s manifest exposing 6333 (or 6334) without
#      QDRANT__SERVICE__API_KEY env var
#   3. env / shell file that exports QDRANT__SERVICE__API_KEY="" (empty)
#   4. config or env enabling JWT/RBAC ineffectively: enable_tls=false AND
#      no api_key set AND host bound to 0.0.0.0
#
# Exit 0 iff every bad sample fires and zero good samples fire.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

is_bad() {
  local f="$1"

  # Rule 3: explicit empty env var
  if grep -Eq '^[[:space:]]*(export[[:space:]]+)?QDRANT__SERVICE__API_KEY[[:space:]]*=[[:space:]]*("")[[:space:]]*$' "$f"; then
    return 0
  fi

  # Rule 1: config.yaml with service.api_key empty / null / commented and host not loopback
  if grep -Eq '^[[:space:]]*host:[[:space:]]*(0\.0\.0\.0|"0\.0\.0\.0")' "$f" \
     && ! grep -Eq '^[[:space:]]*api_key:[[:space:]]*[^[:space:]"#'"'"'][^#]*$' "$f" \
     && ! grep -Eq '^[[:space:]]*api_key:[[:space:]]*"[^"]+"' "$f" \
     && ! grep -Eq "^[[:space:]]*api_key:[[:space:]]*'[^']+'" "$f"; then
    return 0
  fi

  # Rule 2: container manifest exposing 6333/6334 without API key env
  if grep -Eq '("6333"|"6334"|6333:6333|6334:6334|containerPort:[[:space:]]*633[34])' "$f" \
     && ! grep -Eiq 'QDRANT__SERVICE__API_KEY' "$f"; then
    return 0
  fi

  # Rule 4: tls disabled + host 0.0.0.0 + no api_key in same file
  if grep -Eq '^[[:space:]]*enable_tls:[[:space:]]*false' "$f" \
     && grep -Eq '^[[:space:]]*host:[[:space:]]*(0\.0\.0\.0|"0\.0\.0\.0")' "$f" \
     && ! grep -Eq '^[[:space:]]*api_key:[[:space:]]*["'"'"']?[A-Za-z0-9._${}-]+' "$f"; then
    return 0
  fi

  return 1
}

for f in "$@"; do
  case "$f" in
    *samples/bad/*) bad_total=$((bad_total+1)) ;;
    *samples/good/*) good_total=$((good_total+1)) ;;
  esac
  if is_bad "$f"; then
    echo "BAD  $f"
    case "$f" in
      *samples/bad/*) bad_hits=$((bad_hits+1)) ;;
      *samples/good/*) good_hits=$((good_hits+1)) ;;
    esac
  else
    echo "GOOD $f"
  fi
done

status="FAIL"
if [ "$bad_hits" = "$bad_total" ] && [ "$good_hits" = 0 ]; then
  status="PASS"
fi
echo "bad=${bad_hits}/${bad_total} good=${good_hits}/${good_total} ${status}"
[ "$status" = "PASS" ]
