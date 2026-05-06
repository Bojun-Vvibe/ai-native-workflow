#!/usr/bin/env bash
# detect.sh — flag Pi-hole `setupVars.conf` snippets that LLMs
# routinely emit with `WEBPASSWORD=` set to the empty string,
# missing entirely on a configured install, or set to a literal
# placeholder like `CHANGEME`. Pi-hole's admin Web UI gates query
# log access, blocklist edits, DNS-record edits, and `dnsmasq`
# config writes behind WEBPASSWORD; an empty value disables the
# login screen entirely so any host that can reach the Pi-hole
# admin port (default 80) gets full DNS-rewriter privileges.
#
# Bad patterns (any one is sufficient):
#   1. `WEBPASSWORD=` with nothing after the `=` (empty value).
#   2. `WEBPASSWORD=""` or `WEBPASSWORD=''` (empty quoted value).
#   3. `WEBPASSWORD=<placeholder>` for placeholder ∈ {CHANGEME,
#      TODO, xxx, placeholder, replaceme, password, admin}.
#   4. A configured Pi-hole file (PIHOLE_INTERFACE / IPV4_ADDRESS /
#      BLOCKING_ENABLED present, signalling a real install rather
#      than a stub) with no `WEBPASSWORD=` line at all — this is
#      the "I just installed and skipped the password prompt"
#      shape that ships an unauthenticated admin UI.
#
# Good patterns are the inverse: WEBPASSWORD set to a non-empty,
# non-placeholder value (Pi-hole stores it as a doubled SHA-256
# hex digest, so 64 hex chars is the canonical real shape, but we
# accept any non-placeholder string of length >= 8 as "looks
# real").
#
# We strip `#` line comments so that documentation comments that
# quote `WEBPASSWORD=` don't false-fire. We only scan files whose
# content fingerprints as `setupVars.conf` (presence of at least
# one of the canonical Pi-hole keys).
#
# Bash 3.2+ / awk / coreutils only. No network calls.

set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  # setupVars.conf uses shell-style `#` comments.
  sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

is_setupvars() {
  local s="$1"
  printf '%s\n' "$s" \
    | grep -Eq '^[[:space:]]*(PIHOLE_INTERFACE|IPV4_ADDRESS|IPV6_ADDRESS|PIHOLE_DNS_[12]|QUERY_LOGGING|INSTALL_WEB_SERVER|INSTALL_WEB_INTERFACE|LIGHTTPD_ENABLED|BLOCKING_ENABLED|DNSMASQ_LISTENING)\b'
}

is_real_install() {
  # Strong fingerprint: at least one of these keys present means
  # this is not just a stub or doc snippet.
  local s="$1"
  printf '%s\n' "$s" \
    | grep -Eq '^[[:space:]]*(PIHOLE_INTERFACE|IPV4_ADDRESS|BLOCKING_ENABLED|PIHOLE_DNS_1)\b'
}

webpassword_line() {
  printf '%s\n' "$1" \
    | grep -E '^[[:space:]]*WEBPASSWORD[[:space:]]*=' \
    | tail -n1
}

webpassword_value() {
  # Strip leading/trailing surrounding quotes.
  printf '%s' "$1" \
    | sed -E 's/^[[:space:]]*WEBPASSWORD[[:space:]]*=[[:space:]]*//' \
    | sed -E 's/[[:space:]]+$//' \
    | sed -E 's/^"(.*)"$/\1/' \
    | sed -E "s/^'(.*)'$/\1/"
}

is_placeholder() {
  case "$(printf '%s' "$1" | tr 'A-Z' 'a-z')" in
    "changeme"|"todo"|"xxx"|"placeholder"|"replaceme"|"password"|"admin"|"pihole"|"yourpassword"|"yourpasswordhere") return 0 ;;
  esac
  return 1
}

is_bad() {
  local f="$1"
  local s
  s="$(strip_comments "$f")"
  is_setupvars "$s" || return 1

  local line val
  line="$(webpassword_line "$s")"

  if [ -z "$line" ]; then
    # Pattern 4: real install with no WEBPASSWORD line at all.
    if is_real_install "$s"; then
      return 0
    fi
    return 1
  fi

  val="$(webpassword_value "$line")"
  # Pattern 1 & 2: empty.
  if [ -z "$val" ]; then
    return 0
  fi
  # Pattern 3: placeholder.
  if is_placeholder "$val"; then
    return 0
  fi
  # Too short to plausibly be a real hash or password.
  if [ "${#val}" -lt 8 ]; then
    return 0
  fi
  return 1
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
