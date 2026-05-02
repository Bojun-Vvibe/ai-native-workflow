#!/usr/bin/env bash
# detect.sh — flag Harbor (container registry) configuration that ships with the
# upstream-default admin password `Harbor12345` (or with HARBOR_ADMIN_PASSWORD
# explicitly set to that string). LLMs frequently emit this shape when asked to
# "set up Harbor with docker-compose" because it mirrors the upstream sample
# `harbor.yml`, producing an unauthenticated-equivalent registry the moment it
# is exposed.
#
# Reads each path in $@ (or stdin if no args). Prints per-file BAD/GOOD lines
# and a trailing tally:
#   bad=<hits>/<bad-total> good=<hits>/<good-total> PASS|FAIL
# Exits 0 only if every bad sample is flagged and no good sample is flagged.
set -u

bad_hits=0
bad_total=0
good_hits=0
good_total=0

# A file is BAD if it contains any of:
#   - harbor_admin_password: Harbor12345    (harbor.yml shape, any case for key)
#   - HARBOR_ADMIN_PASSWORD=Harbor12345     (env / docker-compose shape)
#   - HARBOR_ADMIN_PASSWORD: "Harbor12345"  (compose environment list shape)
# Quotes around the value are optional. Whitespace tolerated.
is_bad() {
  local f="$1"
  awk '
    BEGIN { IGNORECASE=1; bad=0 }
    # YAML key form, e.g. "harbor_admin_password: Harbor12345"
    /^[[:space:]]*harbor_admin_password[[:space:]]*:[[:space:]]*"?Harbor12345"?[[:space:]]*$/ { bad=1 }
    # Env-style assignment, e.g. "HARBOR_ADMIN_PASSWORD=Harbor12345"
    /(^|[[:space:]])HARBOR_ADMIN_PASSWORD[[:space:]]*=[[:space:]]*"?Harbor12345"?([[:space:]]|$)/ { bad=1 }
    # Compose environment list form, e.g. "  - HARBOR_ADMIN_PASSWORD=Harbor12345"
    /^[[:space:]]*-[[:space:]]*HARBOR_ADMIN_PASSWORD[[:space:]]*=[[:space:]]*"?Harbor12345"?[[:space:]]*$/ { bad=1 }
    # Compose environment map form, e.g. "  HARBOR_ADMIN_PASSWORD: Harbor12345"
    /^[[:space:]]*HARBOR_ADMIN_PASSWORD[[:space:]]*:[[:space:]]*"?Harbor12345"?[[:space:]]*$/ { bad=1 }
    END { exit bad ? 0 : 1 }
  ' "$f"
}

scan_one() {
  local f="$1"
  case "$f" in
    *samples/bad-*)  bad_total=$((bad_total+1))  ;;
    *samples/good-*) good_total=$((good_total+1)) ;;
  esac
  if is_bad "$f"; then
    echo "BAD  $f"
    case "$f" in
      *samples/bad-*)  bad_hits=$((bad_hits+1))  ;;
      *samples/good-*) good_hits=$((good_hits+1)) ;;
    esac
  else
    echo "GOOD $f"
  fi
}

if [ "$#" -eq 0 ]; then
  tmp="$(mktemp)"
  cat > "$tmp"
  scan_one "$tmp"
  rm -f "$tmp"
else
  for f in "$@"; do scan_one "$f"; done
fi

status="FAIL"
if [ "$bad_hits" = "$bad_total" ] && [ "$bad_total" -gt 0 ] && [ "$good_hits" = 0 ]; then
  status="PASS"
fi
echo "bad=${bad_hits}/${bad_total} good=${good_hits}/${good_total} ${status}"
[ "$status" = "PASS" ]
