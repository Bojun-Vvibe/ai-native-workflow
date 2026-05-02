#!/usr/bin/env bash
# detect.sh — flag InfluxDB v1 / v2 config snippets that disable auth or expose
# the admin/HTTP API without a credential boundary:
#   1. influxdb.conf [http] section with `auth-enabled = false`
#   2. influxdb.conf [http] section with `pprof-enabled = true` AND no auth-enabled = true
#   3. environment-variable form `INFLUXDB_HTTP_AUTH_ENABLED=false`
#   4. v2 setup commands using `--http-bind-address 0.0.0.0:8086` paired with
#      a hard-coded password flag (telltale of demo-grade configs leaking from LLMs)
#   5. influxdb.conf with `[admin]` section enabled (`enabled = true`) — the
#      legacy admin UI had no auth and was removed for that reason
#
# Exit 0 iff bad/* are all flagged AND good/* are all clean.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

# Returns 0 if file looks bad.
is_bad() {
  local f="$1"
  # Rule 3: env-var form
  if grep -Eq '^[[:space:]]*(export[[:space:]]+)?INFLUXDB_HTTP_AUTH_ENABLED[[:space:]]*=[[:space:]]*"?(false|0|no)"?' "$f"; then
    return 0
  fi
  # Rule 1: auth-enabled = false (uncommented)
  if grep -Eq '^[[:space:]]*auth-enabled[[:space:]]*=[[:space:]]*false' "$f"; then return 0; fi
  # Rule 5: legacy [admin] enabled
  # crude but effective: an uncommented `enabled = true` within ~5 lines after [admin]
  if awk '
    /^[[:space:]]*\[admin\]/ {in_admin=1; lines=0; next}
    in_admin && /^[[:space:]]*\[/ {in_admin=0}
    in_admin {
      lines++
      if (lines<=8 && $0 ~ /^[[:space:]]*enabled[[:space:]]*=[[:space:]]*true/) {found=1; exit}
    }
    END {exit !found}
  ' "$f"; then
    return 0
  fi
  # Rule 2: pprof-enabled = true with no auth-enabled = true
  if grep -Eq '^[[:space:]]*pprof-enabled[[:space:]]*=[[:space:]]*true' "$f" \
     && ! grep -Eq '^[[:space:]]*auth-enabled[[:space:]]*=[[:space:]]*true' "$f"; then
    return 0
  fi
  # Rule 4: v2 setup binding 0.0.0.0 + cleartext password flag
  if grep -Eq -- '--http-bind-address[[:space:]=]+0\.0\.0\.0' "$f" \
     && grep -Eq -- '--password[[:space:]=]+[^[:space:]$]' "$f"; then
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
