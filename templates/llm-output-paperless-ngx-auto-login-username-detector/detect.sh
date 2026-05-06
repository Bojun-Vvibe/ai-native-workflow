#!/usr/bin/env bash
# detect.sh — flag Paperless-NGX environment / docker-compose
# snippets that LLMs routinely emit with `PAPERLESS_AUTO_LOGIN_USERNAME`
# set to a real username. Paperless-NGX honours that variable as a
# "skip the login form, treat every incoming request as user X"
# bypass; it was added to ease reverse-proxy SSO setups but ships
# with NO check that the request actually came from the proxy. If
# the Paperless web port is reachable on the LAN (or, worse,
# exposed publicly), every request is silently authenticated as
# the configured user, including admin actions if that user has
# is_staff / is_superuser.
#
# Bad patterns (any one is sufficient):
#   1. `PAPERLESS_AUTO_LOGIN_USERNAME=<non-empty value>` in a
#      Paperless env file (`.env`, `docker-compose.env`,
#      `paperless.conf`).
#   2. `PAPERLESS_AUTO_LOGIN_USERNAME: <non-empty>` as a YAML
#      `environment:` entry inside a Paperless service block.
#   3. `- PAPERLESS_AUTO_LOGIN_USERNAME=<non-empty>` as a YAML
#      list-form environment entry.
#   4. `PAPERLESS_AUTO_LOGIN_USERNAME=<placeholder-like-admin>`
#      where the value is one of the obviously-wrong defaults
#      (admin, root, paperless, user) — these are strictly worse
#      than a typo because they match the canonical superuser
#      name and grant full admin to anyone who can reach the port.
#
# Good patterns are the inverse: variable absent, explicitly
# empty (`PAPERLESS_AUTO_LOGIN_USERNAME=`), or only mentioned
# inside a `#` comment in a documentation/example file.
#
# We require the file to fingerprint as Paperless-related (presence
# of at least one other `PAPERLESS_*` key, or a docker service
# whose image is `paperless` / `paperless-ngx`). A bare
# `PAPERLESS_AUTO_LOGIN_USERNAME=foo` line in some unrelated env
# file does not fire.
#
# Bash 3.2+ / awk / coreutils only. No network calls.

set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  # Both `.env` and YAML use `#` line comments.
  sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

is_paperless_scope() {
  local s="$1"
  printf '%s\n' "$s" \
    | grep -Eq 'PAPERLESS_(URL|SECRET_KEY|REDIS|DBHOST|DBNAME|DBUSER|DBPASS|TIME_ZONE|OCR_LANGUAGE|CONSUMPTION_DIR|DATA_DIR|MEDIA_ROOT|ADMIN_USER|ADMIN_PASSWORD|FILENAME_FORMAT|ALLOWED_HOSTS|CSRF_TRUSTED_ORIGINS)\b' \
  || printf '%s\n' "$s" \
    | grep -Eqi 'image:[[:space:]]*[^[:space:]]*paperless(-ngx)?(:[^[:space:]]*)?[[:space:]]*$'
}

auto_login_lines() {
  # All three syntaxes:
  #   PAPERLESS_AUTO_LOGIN_USERNAME=foo
  #   PAPERLESS_AUTO_LOGIN_USERNAME: foo
  #   - PAPERLESS_AUTO_LOGIN_USERNAME=foo
  printf '%s\n' "$1" \
    | grep -E '^[[:space:]]*-?[[:space:]]*PAPERLESS_AUTO_LOGIN_USERNAME[[:space:]]*[:=]'
}

extract_value() {
  # Strip leading `- `, the key, the separator, surrounding quotes.
  printf '%s' "$1" \
    | sed -E 's/^[[:space:]]*-?[[:space:]]*PAPERLESS_AUTO_LOGIN_USERNAME[[:space:]]*[:=][[:space:]]*//' \
    | sed -E 's/[[:space:]]+$//' \
    | sed -E 's/^"(.*)"$/\1/' \
    | sed -E "s/^'(.*)'$/\1/"
}

is_bad() {
  local f="$1"
  local s
  s="$(strip_comments "$f")"
  is_paperless_scope "$s" || return 1

  local lines line val
  lines="$(auto_login_lines "$s")"
  [ -n "$lines" ] || return 1

  while IFS= read -r line; do
    [ -n "$line" ] || continue
    val="$(extract_value "$line")"
    if [ -n "$val" ]; then
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
