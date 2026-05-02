#!/usr/bin/env bash
# detect.sh — flag ClickHouse user configs where the `default` user has an empty
# password (or no password element at all) while still being reachable, which is
# a frequent insecure pattern that LLMs emit when asked to "set up ClickHouse".
#
# Exits 0 only if NO bad files match. Prints a per-file BAD/GOOD summary plus a
# trailing tally line: bad=<hits>/<bad-total> good=<hits>/<good-total> PASS|FAIL
set -u

bad_hits=0
bad_total=0
good_hits=0
good_total=0

is_bad() {
  local f="$1"
  # Look for a <default> user block. Within that block, flag if either:
  #   - <password></password> appears (empty password), OR
  #   - <password_sha256_hex></password_sha256_hex> appears empty, OR
  #   - no <password*> tag is present at all inside the <default> block.
  awk '
    BEGIN { inblk=0; saw_pw=0; bad=0 }
    /<default>/ { inblk=1; saw_pw=0; next }
    inblk && /<\/default>/ {
      if (!saw_pw) bad=1
      inblk=0
      next
    }
    inblk && /<password>[[:space:]]*<\/password>/ { bad=1; saw_pw=1 }
    inblk && /<password_sha256_hex>[[:space:]]*<\/password_sha256_hex>/ { bad=1; saw_pw=1 }
    inblk && /<password_double_sha1_hex>[[:space:]]*<\/password_double_sha1_hex>/ { bad=1; saw_pw=1 }
    inblk && /<password>[^<]+<\/password>/ { saw_pw=1 }
    inblk && /<password_sha256_hex>[0-9a-fA-F]+<\/password_sha256_hex>/ { saw_pw=1 }
    inblk && /<password_double_sha1_hex>[0-9a-fA-F]+<\/password_double_sha1_hex>/ { saw_pw=1 }
    END { exit bad ? 0 : 1 }
  ' "$f"
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
