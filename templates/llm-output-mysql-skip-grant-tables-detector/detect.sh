#!/usr/bin/env bash
# detect.sh — flag MySQL/MariaDB config & startup snippets that disable the
# privilege system entirely:
#   1. my.cnf containing `skip-grant-tables` (or `skip_grant_tables`) — uncommented
#   2. mysqld / mariadbd / docker / systemd command lines passing
#      `--skip-grant-tables`
#   3. SQL/init scripts that set the server variable at runtime via
#      `SET GLOBAL ...` (rare but possible recovery footgun left in scripts)
#
# Exit 0 iff no bad files match.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

is_bad() {
  local f="$1"
  # Rule 1: my.cnf line, not commented, possibly under [mysqld]
  if grep -Eiq '^[[:space:]]*skip[-_]grant[-_]tables([[:space:]]*=[[:space:]]*(1|true|on))?[[:space:]]*(#.*)?$' "$f"; then
    return 0
  fi
  # Rule 2: command-line flag in any context
  if grep -Eq '(^|[[:space:]"'\''])--skip[-_]grant[-_]tables([[:space:]"'\''=]|$)' "$f"; then
    return 0
  fi
  # Rule 3: runtime SQL setting (some recovery docs paste this into init.sql)
  if grep -Eiq '\bSET[[:space:]]+GLOBAL[[:space:]]+skip_grant_tables[[:space:]]*=' "$f"; then
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
