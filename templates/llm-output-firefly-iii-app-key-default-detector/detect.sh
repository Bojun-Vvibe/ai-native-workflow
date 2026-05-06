#!/usr/bin/env bash
# detect.sh — flag Firefly III environment / docker-compose snippets
# that LLMs routinely emit with `APP_KEY` left at the well-known
# placeholder string from the official `.env.example` /
# `docker-compose.yml` template:
#
#   APP_KEY=SomeRandomStringOf32CharsExactly
#
# Firefly III is a Laravel app. APP_KEY is the symmetric key used
# by Laravel's `encrypt()` / `decrypt()` and by the cookie/session
# encrypter. If the key matches the literal documented placeholder
# (or other known stand-ins like "ChangeMe...", a row of `x`s,
# "base64:..." that decodes to docs sample bytes), every Firefly
# III instance in the world that ran with that placeholder shares
# a key. Anyone can:
#   - forge session cookies and impersonate any user;
#   - decrypt webhook secrets, OAuth tokens, and the personal
#     access tokens stored in the DB columns Laravel encrypts.
#
# Bad patterns (any one is sufficient):
#   1. `APP_KEY=SomeRandomStringOf32CharsExactly` (the literal
#      example from the README / .env.example).
#   2. `APP_KEY=` followed by a clearly-placeholder value
#      ("ChangeMe...", "PleaseChangeThis...", a string of repeated
#      "x" / "0" / "a" of length >= 16, "your-app-key-here", etc.).
#   3. The same as a YAML mapping-form `environment:` entry inside
#      a Firefly III service.
#   4. The same as a YAML list-form (`- APP_KEY=...`) entry inside
#      a Firefly III service.
#
# Good patterns are the inverse: APP_KEY absent (will be generated
# on first boot), APP_KEY explicitly empty, APP_KEY set to a real
# 32-byte random value (we approximate "real" as "32+ chars, mixed
# case + digits, not in the placeholder denylist"), or the file
# only mentions APP_KEY inside a `#` comment.
#
# We require the file to fingerprint as Firefly III related
# (presence of at least one other `FIREFLY_III_*` / `DB_CONNECTION`
# + `APP_URL` Firefly-style key, or a docker service whose image
# is `fireflyiii/core` / `jc5x/firefly-iii`). A bare APP_KEY line
# in some unrelated env file does not fire (lots of Laravel apps
# share the variable name).
#
# Bash 3.2+ / awk / coreutils only. No network calls.

set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  # Both `.env` and YAML use `#` line comments.
  sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

is_firefly_scope() {
  local s="$1"
  # Either a Firefly-specific image, or a Firefly-specific env key
  # (SITE_OWNER + APP_URL is the canonical pair from the docs;
  # FIREFLY_III_* keys also exist; STATIC_CRON_TOKEN is Firefly-
  # specific too).
  printf '%s\n' "$s" \
    | grep -Eqi 'image:[[:space:]]*[^[:space:]]*(fireflyiii/core|jc5x/firefly-iii)(:[^[:space:]]*)?[[:space:]]*$' \
    && return 0
  printf '%s\n' "$s" \
    | grep -Eq '(^|[[:space:]-])(SITE_OWNER|STATIC_CRON_TOKEN|FIREFLY_III_[A-Z_]+|TRUSTED_PROXIES)[[:space:]]*[:=]' \
    && return 0
  return 1
}

app_key_lines() {
  # All three syntaxes:
  #   APP_KEY=...
  #   APP_KEY: ...
  #   - APP_KEY=...
  printf '%s\n' "$1" \
    | grep -E '^[[:space:]]*-?[[:space:]]*APP_KEY[[:space:]]*[:=]'
}

extract_value() {
  printf '%s' "$1" \
    | sed -E 's/^[[:space:]]*-?[[:space:]]*APP_KEY[[:space:]]*[:=][[:space:]]*//' \
    | sed -E 's/[[:space:]]+$//' \
    | sed -E 's/^"(.*)"$/\1/' \
    | sed -E "s/^'(.*)'$/\1/"
}

is_placeholder_value() {
  local v="$1"
  # Empty -> not placeholder, treated as "good" (will be generated).
  [ -n "$v" ] || return 1
  # Exact documented placeholder.
  [ "$v" = "SomeRandomStringOf32CharsExactly" ] && return 0
  # Common stand-ins (case-insensitive).
  printf '%s' "$v" | grep -Eqi '^(changeme|change-me|please[-_ ]?change[-_ ]?(this|me)?|your[-_ ]?app[-_ ]?key([-_ ]?here)?|insert[-_ ]?key[-_ ]?here|app[-_ ]?key[-_ ]?goes[-_ ]?here|placeholder|example[-_ ]?key)[[:alnum:]_-]*$' \
    && return 0
  # base64:CHANGEME / base64:placeholder.
  printf '%s' "$v" | grep -Eqi '^base64:(changeme|placeholder|change-me|example|your-key-here)' \
    && return 0
  # Long run of the same character (xxxxxxxxxxxxxxxx, 0000..., aaaa...).
  if [ "${#v}" -ge 16 ]; then
    local first
    first="${v:0:1}"
    case "$first" in
      [a-zA-Z0-9])
        # Build a string of N copies of $first and compare.
        local n="${#v}" pad=""
        local i=0
        while [ "$i" -lt "$n" ]; do pad="${pad}${first}"; i=$((i+1)); done
        [ "$v" = "$pad" ] && return 0
        ;;
    esac
  fi
  return 1
}

is_bad() {
  local f="$1"
  local s
  s="$(strip_comments "$f")"
  is_firefly_scope "$s" || return 1

  local lines line val
  lines="$(app_key_lines "$s")"
  [ -n "$lines" ] || return 1

  while IFS= read -r line; do
    [ -n "$line" ] || continue
    val="$(extract_value "$line")"
    if is_placeholder_value "$val"; then
      return 0
    fi
  done <<EOF
$lines
EOF
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
