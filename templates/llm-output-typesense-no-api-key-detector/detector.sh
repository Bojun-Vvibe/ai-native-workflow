#!/usr/bin/env bash
# detector.sh — flag Typesense launch configs that disable / skip the admin API key.
#
# Rules:
#  R1: typesense-server invocation present but no --api-key / -k= flag anywhere in file
#  R2: --api-key="" or --api-key= (empty), or -k="" / -k=
#  R3: TYPESENSE_API_KEY exported as "" or as the docs sample "xyz"
#  R4: container manifest exposes 8108 on non-loopback bind AND TYPESENSE_API_KEY
#      is missing or empty
#
# Exit 0 iff every bad sample matches and zero good samples match.
set -u

is_bad() {
  local f="$1"

  # R3: empty or default-docs env var
  if grep -Eq '^[[:space:]]*(export[[:space:]]+)?TYPESENSE_API_KEY[[:space:]]*=[[:space:]]*""[[:space:]]*$' "$f"; then
    return 0
  fi
  if grep -Eq '^[[:space:]]*(export[[:space:]]+)?TYPESENSE_API_KEY[[:space:]]*=[[:space:]]*"?xyz"?[[:space:]]*$' "$f"; then
    return 0
  fi

  # R2: empty --api-key / -k value on a typesense-server line or anywhere in a launch script
  if grep -Eq '(--api-key|(^|[[:space:]])-k)([[:space:]]+|=)("")' "$f"; then
    return 0
  fi
  if grep -Eq '(--api-key|(^|[[:space:]])-k)=([[:space:]]|$)' "$f"; then
    return 0
  fi

  # R1: typesense-server invoked without any api-key flag anywhere in the file
  if grep -Eq 'typesense-server' "$f" && ! grep -Eq '(--api-key|(^|[[:space:]])-k=|TYPESENSE_API_KEY)' "$f"; then
    return 0
  fi

  # R4: container manifest exposes 8108 on non-loopback without non-empty TYPESENSE_API_KEY
  if grep -Eq '("8108"|8108:8108|containerPort:[[:space:]]*8108|EXPOSE[[:space:]]+8108)' "$f"; then
    if ! grep -Eq '127\.0\.0\.1:8108' "$f"; then
      if ! grep -Eq 'TYPESENSE_API_KEY[[:space:]]*[:=][[:space:]]*"?[A-Za-z0-9._/+-]{6,}"?' "$f"; then
        return 0
      fi
    fi
  fi

  return 1
}

bad_hits=0; bad_total=0; good_hits=0; good_total=0
for f in "$@"; do
  case "$f" in
    *examples/bad/*)  bad_total=$((bad_total+1)) ;;
    *examples/good/*) good_total=$((good_total+1)) ;;
  esac
  if is_bad "$f"; then
    echo "BAD  $f"
    case "$f" in
      *examples/bad/*)  bad_hits=$((bad_hits+1)) ;;
      *examples/good/*) good_hits=$((good_hits+1)) ;;
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
