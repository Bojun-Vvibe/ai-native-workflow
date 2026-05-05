#!/usr/bin/env bash
# detect.sh — flag coturn (turnserver) configurations that LLMs
# routinely emit with authentication disabled. coturn implements
# TURN/STUN relay: when a client successfully allocates a relay,
# every UDP/TCP packet the client sends is forwarded out of the
# server's network interface. With auth turned off, the server is an
# open SOCKS-grade UDP relay — abusable for anonymising attack
# traffic, NAT-punch reflection, bandwidth theft, and as a pivot into
# private networks reachable from the coturn host.
#
# The two stable knobs that disable auth are documented in
# `turnserver --help`:
#   * `--no-auth`   /  config line `no-auth`           => skip auth entirely.
#   * `--no-auth-pings` is NOT the same; do not flag.
# A subtler form is "auth is technically on but the shared secret is
# the placeholder one":
#   * `use-auth-secret` enabled with `static-auth-secret=` set to the
#     literal placeholder values seen in upstream sample configs
#     (`changeme`, `please_change_me`, `secret`, `coturn`, `turn`,
#     `your_secret_here`, empty string).
#
# Bad patterns we flag (any one is sufficient):
#   1. `turnserver.conf`-style file containing an uncommented
#      `no-auth` line (with or without `=` / value), at column 0
#      indentation (coturn ignores leading-tab/space lines).
#   2. CLI invocation `turnserver ... --no-auth ...`.
#   3. `turnserver.conf` containing `use-auth-secret` AND a
#      `static-auth-secret=<placeholder>` value from the well-known
#      list above (case-insensitive).
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  # coturn config: `#` starts a line comment. Also strip trailing
  # `#...` so a comment can't shield a directive on the same line.
  sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

is_turnserver_conf() {
  # Strong markers: a `listening-port=` line, `realm=`, `lt-cred-mech`,
  # `use-auth-secret`, or any `turnserver` mention near a config-style
  # `key=value` shape.
  local s="$1"
  printf '%s\n' "$s" | grep -Eiq '^[[:space:]]*(listening-port|realm|lt-cred-mech|use-auth-secret|no-auth|static-auth-secret|fingerprint|min-port|max-port)[[:space:]=]'
}

is_turnserver_cli() {
  local s="$1"
  printf '%s\n' "$s" | grep -Eiq '(^|[[:space:]/"=])turnserver\b'
}

has_no_auth_directive() {
  # `no-auth` on its own line, optionally `no-auth=true` / `=1`.
  local s="$1"
  printf '%s\n' "$s" \
    | grep -Eiq '^[[:space:]]*no-auth[[:space:]]*(=[[:space:]]*(1|true|yes|on))?[[:space:]]*$'
}

has_no_auth_cli_flag() {
  local s="$1"
  # Match `--no-auth` as a standalone token. Reject `--no-auth-pings`
  # explicitly.
  printf '%s\n' "$s" \
    | grep -Eiq '(^|[[:space:]])--no-auth($|[[:space:]=])' \
    && ! printf '%s\n' "$s" | grep -Eiq -- '--no-auth($|[[:space:]=])\S*pings'
  # The `&& !` chain returns the status of the last command. Re-check
  # without the negative.
  if printf '%s\n' "$s" | grep -Eiq '(^|[[:space:]])--no-auth-pings\b'; then
    # Still allowed only if a bare `--no-auth` also appears.
    printf '%s\n' "$s" \
      | grep -Eiq '(^|[[:space:]])--no-auth($|[[:space:]=])'
    return $?
  fi
  printf '%s\n' "$s" | grep -Eiq '(^|[[:space:]])--no-auth($|[[:space:]=])'
}

placeholder_secret() {
  # case-insensitive token check
  local v
  v="$(printf '%s\n' "$1" | tr 'A-Z' 'a-z')"
  case "$v" in
    ""|changeme|please_change_me|please-change-me|secret|coturn|turn|your_secret_here|your-secret-here|defaultsecret|default_secret) return 0 ;;
    *) return 1 ;;
  esac
}

has_placeholder_auth_secret() {
  local s="$1"
  # use-auth-secret must be enabled (line present, optionally =true)
  printf '%s\n' "$s" \
    | grep -Eiq '^[[:space:]]*use-auth-secret[[:space:]]*(=[[:space:]]*(1|true|yes|on))?[[:space:]]*$' \
    || return 1
  # Pull static-auth-secret value(s).
  local vals
  vals="$(printf '%s\n' "$s" \
    | grep -Ei '^[[:space:]]*static-auth-secret[[:space:]]*=' \
    | sed -E 's/^[[:space:]]*static-auth-secret[[:space:]]*=[[:space:]]*//' \
    | sed -E 's/[[:space:]]+$//' \
    | sed -E 's/^"|"$//g' \
    || true)"
  if [ -z "$vals" ]; then
    # use-auth-secret on but no static secret line at all => degenerate.
    return 0
  fi
  while IFS= read -r v; do
    if placeholder_secret "$v"; then return 0; fi
  done <<<"$vals"
  return 1
}

is_bad() {
  local f="$1"
  local stripped
  stripped="$(strip_comments "$f")"

  if is_turnserver_cli "$stripped" && ! is_turnserver_conf "$stripped"; then
    if has_no_auth_cli_flag "$stripped"; then return 0; fi
    return 1
  fi

  if is_turnserver_conf "$stripped"; then
    if has_no_auth_directive "$stripped"; then return 0; fi
    if has_placeholder_auth_secret "$stripped"; then return 0; fi
    return 1
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
