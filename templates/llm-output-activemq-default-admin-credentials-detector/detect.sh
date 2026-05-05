#!/usr/bin/env bash
# detect.sh — flag Apache ActiveMQ configuration / setup snippets that ship
# the broker with the well-known default admin credentials (admin/admin) or
# the equally infamous default `system/manager`, `user/password` pairs in
# `conf/users.properties`, `conf/jetty-realm.properties`, or
# `conf/credentials.properties`. Also flags activemq.xml that wires a
# `simpleAuthenticationPlugin` whose `users` element contains `admin`/`admin`.
#
# LLMs often regenerate the stock ActiveMQ users file verbatim when asked
# "how do I enable the web console" or "give me a working broker config",
# leaving the broker's JMX, web console, and STOMP/OpenWire endpoints
# protected only by `admin:admin`.
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

# Strip comments (# … and <!-- … --> on a single line) before matching, so a
# commented-out example doesn't trip the detector.
strip_comments() {
  sed -e 's/<!--.*-->//g' -e 's/#.*$//' "$1"
}

is_bad() {
  local f="$1"
  local stripped
  stripped="$(strip_comments "$f")"

  # Rule 1: jetty-realm.properties / users.properties literal `admin: admin,`
  # or `admin=admin` (with optional role suffix). Covers the file ActiveMQ
  # ships by default.
  if printf '%s\n' "$stripped" | grep -Eiq '^[[:space:]]*admin[[:space:]]*[:=][[:space:]]*admin([[:space:]]*,|[[:space:]]*$)'; then
    return 0
  fi

  # Rule 2: credentials.properties shipping `activemq.username=system` AND
  # `activemq.password=manager` (or any pair where password is `manager`,
  # `password`, `admin`, or `secret`).
  if printf '%s\n' "$stripped" | grep -Eiq '^[[:space:]]*activemq\.password[[:space:]]*=[[:space:]]*(manager|password|admin|secret|changeme)[[:space:]]*$'; then
    return 0
  fi

  # Rule 3: activemq.xml `<simpleAuthenticationPlugin>` whose `<authenticationUser>`
  # has username="admin" and password="admin" (case-insensitive, attribute
  # order independent).
  if printf '%s\n' "$stripped" \
     | tr '\n' ' ' \
     | grep -Eiq '<authenticationUser[^>]*username="admin"[^>]*password="admin"'; then
    return 0
  fi
  if printf '%s\n' "$stripped" \
     | tr '\n' ' ' \
     | grep -Eiq '<authenticationUser[^>]*password="admin"[^>]*username="admin"'; then
    return 0
  fi

  # Rule 4: docker-compose / env-file style `ACTIVEMQ_ADMIN_LOGIN=admin` paired
  # with `ACTIVEMQ_ADMIN_PASSWORD=admin` in the same file.
  if printf '%s\n' "$stripped" | grep -Eiq '^[[:space:]]*ACTIVEMQ_ADMIN_LOGIN[[:space:]]*[:=][[:space:]]*"?admin"?[[:space:]]*$' \
     && printf '%s\n' "$stripped" | grep -Eiq '^[[:space:]]*ACTIVEMQ_ADMIN_PASSWORD[[:space:]]*[:=][[:space:]]*"?admin"?[[:space:]]*$'; then
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
