#!/usr/bin/env bash
# detect.sh — flag Meilisearch configs / scripts that run without a master key:
#   1. docker / shell command setting MEILI_MASTER_KEY="" or empty
#   2. config.toml or env file with master_key = "" (or commented out) AND env != development guard absent
#   3. docker-compose / k8s manifest exposing :7700 with no MEILI_MASTER_KEY env var at all
#   4. CLI invocation `meilisearch` / `./meilisearch` with no --master-key flag and no MEILI_MASTER_KEY in scope
#
# Exit 0 iff every bad sample is flagged and zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

is_bad() {
  local f="$1"

  # Rule 1: explicit empty master key
  if grep -Eiq '(MEILI_MASTER_KEY|--master-key)[[:space:]]*[= ][[:space:]]*("")|(MEILI_MASTER_KEY|--master-key)[[:space:]]*[= ][[:space:]]*$' "$f"; then
    return 0
  fi
  if grep -Eiq '^[[:space:]]*master_key[[:space:]]*=[[:space:]]*""[[:space:]]*$' "$f"; then
    return 0
  fi

  # Rule 2: config file with master_key commented out / missing while pointing at production env
  if grep -Eiq 'env[[:space:]]*=[[:space:]]*"production"' "$f" \
     && ! grep -Eiq '^[[:space:]]*master_key[[:space:]]*=[[:space:]]*"[^"]+"' "$f"; then
    return 0
  fi

  # Rule 3: compose/k8s exposing 7700 without master key env
  if grep -Eq '(7700:7700|containerPort:[[:space:]]*7700|"7700")' "$f" \
     && ! grep -Eiq 'MEILI_MASTER_KEY' "$f"; then
    return 0
  fi

  # Rule 4: CLI invocation lacking master key
  if grep -Eq '(^|[[:space:]/])meilisearch([[:space:]]|$)' "$f" \
     && ! grep -Eq '\-\-master-key[[:space:]]+["'\''$A-Za-z0-9._{}-]+' "$f" \
     && ! grep -Eiq 'MEILI_MASTER_KEY=["'\''$A-Za-z0-9._{}-]+' "$f"; then
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
