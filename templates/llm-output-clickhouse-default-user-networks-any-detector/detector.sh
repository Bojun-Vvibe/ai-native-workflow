#!/usr/bin/env bash
# detector.sh — flag ClickHouse user configs that allow connections from
# any IP (CWE-284 / CWE-1188).
#
# Rules (any one fires => BAD):
#  R1: <ip>::/0</ip>                                 (XML, IPv6 catch-all)
#  R2: <ip>0.0.0.0/0</ip>                            (XML, IPv4 catch-all)
#  R3: <host_regex>.*</host_regex> or equivalent     (XML, regex-as-allowlist)
#  R4: networks: ip: '::/0' / "0.0.0.0/0"            (YAML form)
#
# We only flag if the user block is "active" — i.e., the file is a users
# config (users.xml / users.yaml) or a clickhouse-config snippet that
# defines users.

set -u

is_users_config() {
  case "$1" in
    *users*.xml|*users*.yaml|*users*.yml) return 0 ;;
  esac
  # Heuristic: file mentions <users> or 'users:' top-level.
  if grep -Eq '^[[:space:]]*<users>|^users:' "$1"; then
    return 0
  fi
  return 1
}

is_bad() {
  local f="$1"
  if ! is_users_config "$f"; then
    return 1
  fi

  # R1 / R2: XML <ip> catch-all values. Allow optional surrounding whitespace.
  if grep -Eq '<ip>[[:space:]]*::/0[[:space:]]*</ip>' "$f"; then
    return 0
  fi
  if grep -Eq '<ip>[[:space:]]*0\.0\.0\.0/0[[:space:]]*</ip>' "$f"; then
    return 0
  fi

  # R3: <host_regex> that matches everything: ".*" or "^.*$" or just ".+".
  if grep -Eq '<host_regex>[[:space:]]*(\^?\.\*\$?|\.\+)[[:space:]]*</host_regex>' "$f"; then
    return 0
  fi

  # R4: YAML form. Look for an `ip:` value of '::/0' or '0.0.0.0/0' (quoted or not).
  if grep -Eq "^[[:space:]]*-?[[:space:]]*ip[[:space:]]*:[[:space:]]*['\"]?(::/0|0\.0\.0\.0/0)['\"]?[[:space:]]*$" "$f"; then
    return 0
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
