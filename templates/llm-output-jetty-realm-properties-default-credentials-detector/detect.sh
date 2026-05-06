#!/usr/bin/env bash
# detect.sh — flag Jetty `realm.properties` (HashLoginService)
# snippets that LLMs routinely emit shipping the canonical demo
# credentials (`admin: admin, server-administrator, …`) or other
# obvious placeholder credentials. Jetty's HashLoginService loads
# this file at startup; whoever knows a username + password in it
# gets the listed roles, which on Solr / ActiveMQ / standalone
# Jetty installs typically include `server-administrator` /
# `admin` and grants full management access.
#
# realm.properties grammar (per Jetty docs):
#   username: password[,role1,role2,...]
# The password may be plaintext, `OBF:...`, `MD5:...`, or
# `CRYPT:...`. A bare plaintext `admin` (matching the username)
# or any placeholder password is the unsafe shape.
#
# Bad patterns (any one is sufficient):
#   1. A line `<user>: <user>[, ...roles]` — password equals the
#      username (the demo file's shape: `admin: admin, ...`).
#   2. A line `<user>: <placeholder>[, ...roles]` for placeholder
#      ∈ {password, changeme, todo, xxx, placeholder, replaceme,
#         secret, default, jetty, demo, test, 123456, qwerty,
#         letmein, root, pass}.
#   3. A line `<user>: <plaintext-password>[, ...roles]` where
#      one of the roles is an admin-shaped role
#      (`admin`, `administrator`, `server-administrator`,
#      `manager-gui`, `manager-script`, `content-administrator`)
#      AND the password is shorter than 8 characters.
#
# Good patterns are the inverse: hashed passwords (`OBF:`, `MD5:`,
# `CRYPT:`) or plaintext passwords ≥ 8 chars that are not
# placeholders and are not equal to the username.
#
# We strip `#` comments. We only scan files whose content
# fingerprints as a Jetty realm.properties (at least one non-
# comment, non-blank line that matches `<user>: <password>` and
# the file has no obvious other-format markers).
#
# Bash 3.2+ / awk / coreutils only. No network calls.

set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

is_realm_properties() {
  local s="$1"
  # At least one user:pass[,roles] line.
  printf '%s\n' "$s" \
    | grep -Eq '^[[:space:]]*[A-Za-z_][A-Za-z0-9_.-]*[[:space:]]*:[[:space:]]*[^[:space:]].*$' \
    || return 1
  # Reject if it looks like YAML/JSON/INI section headers.
  if printf '%s\n' "$s" | grep -Eq '^[[:space:]]*\['; then
    return 1
  fi
  if printf '%s\n' "$s" | grep -Eq '^[[:space:]]*\{|^[[:space:]]*"[^"]+"[[:space:]]*:'; then
    return 1
  fi
  # Reject YAML-shaped: keys whose value is empty or has nested
  # indentation. realm.properties values are single-line.
  return 0
}

is_placeholder_pw() {
  case "$(printf '%s' "$1" | tr 'A-Z' 'a-z')" in
    "password"|"changeme"|"todo"|"xxx"|"placeholder"|"replaceme"|"secret"|"default"|"jetty"|"demo"|"test"|"123456"|"qwerty"|"letmein"|"root"|"pass"|"admin123") return 0 ;;
  esac
  return 1
}

is_admin_role() {
  case "$(printf '%s' "$1" | tr 'A-Z' 'a-z')" in
    "admin"|"administrator"|"server-administrator"|"manager-gui"|"manager-script"|"content-administrator"|"manager"|"root") return 0 ;;
  esac
  return 1
}

is_hashed() {
  case "$1" in
    "OBF:"*|"MD5:"*|"CRYPT:"*) return 0 ;;
  esac
  return 1
}

scan_lines_bad() {
  # Returns 0 (bad) if any line matches a bad pattern.
  local s="$1"
  local line user pw roles
  while IFS= read -r line; do
    case "$line" in ''|*[![:print:]]*) continue ;; esac
    # Match `user: password[,roles]`
    printf '%s' "$line" | grep -Eq '^[[:space:]]*[A-Za-z_][A-Za-z0-9_.-]*[[:space:]]*:[[:space:]]*[^[:space:]]' || continue
    user="$(printf '%s' "$line" | sed -E 's/^[[:space:]]*([A-Za-z_][A-Za-z0-9_.-]*)[[:space:]]*:.*/\1/')"
    rest="$(printf '%s' "$line" | sed -E 's/^[[:space:]]*[A-Za-z_][A-Za-z0-9_.-]*[[:space:]]*:[[:space:]]*//')"
    # Split on first comma into pw, roles
    if printf '%s' "$rest" | grep -q ','; then
      pw="$(printf '%s' "$rest" | sed -E 's/^([^,]*),.*/\1/' | sed -E 's/[[:space:]]+$//')"
      roles="$(printf '%s' "$rest" | sed -E 's/^[^,]*,(.*)/\1/')"
    else
      pw="$(printf '%s' "$rest" | sed -E 's/[[:space:]]+$//')"
      roles=""
    fi

    # Hashed passwords are fine, skip.
    if is_hashed "$pw"; then
      continue
    fi

    # Pattern 1: password == username.
    if [ "$pw" = "$user" ]; then
      return 0
    fi
    # Pattern 2: placeholder.
    if is_placeholder_pw "$pw"; then
      return 0
    fi
    # Pattern 3: short password + admin-shaped role.
    if [ "${#pw}" -lt 8 ] && [ -n "$roles" ]; then
      # Iterate roles split on comma.
      local r
      local IFSold="$IFS"
      IFS=','
      for r in $roles; do
        r="$(printf '%s' "$r" | sed -E 's/^[[:space:]]+//;s/[[:space:]]+$//')"
        if is_admin_role "$r"; then
          IFS="$IFSold"
          return 0
        fi
      done
      IFS="$IFSold"
    fi
  done <<EOF
$s
EOF
  return 1
}

is_bad() {
  local f="$1"
  local s
  s="$(strip_comments "$f")"
  is_realm_properties "$s" || return 1
  scan_lines_bad "$s"
}

for f in "$@"; do
  case "$f" in
    *samples/bad/*)  bad_total=$((bad_total+1)) ;;
    *samples/good/*) good_total=$((good_total+1)) ;;
  esac
  if is_bad "$f"; then
    echo "BAD  $f"
    case "$f" in
      *samples/bad/*)  bad_hits=$((bad_hits+1)) ;;
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
