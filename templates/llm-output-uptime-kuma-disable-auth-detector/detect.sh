#!/usr/bin/env bash
# detect.sh — flag Uptime Kuma deployment snippets that LLMs
# routinely emit with authentication disabled.
#
# Uptime Kuma supports a "no auth" mode intended only for
# single-user kiosks behind a trusted reverse proxy. It can be
# enabled three ways:
#
#   1. Environment variable in `.env` / `docker-compose.yml`:
#        UPTIME_KUMA_DISABLE_AUTH=true
#      (also accepts "1", "yes", "on")
#   2. CLI flag passed to `node server/server.js` or to the
#      docker `command:` / `entrypoint:`:
#        --disable-auth
#   3. Settings dump / restore JSON containing
#        "disableAuth": true
#      (Uptime Kuma persists its settings to the SQLite DB, but
#      LLMs sometimes render a settings backup blob to "pre-seed"
#      the install).
#
# When auth is disabled the entire dashboard — including monitor
# configs that store HTTP basic-auth headers, bearer tokens for
# API monitors, MQTT credentials, and the status-page admin —
# becomes accessible to anyone who can reach the port. The web
# UI also exposes a one-click "Reveal" button on each saved
# secret, so anyone who reaches the dashboard can read the
# stored credentials in cleartext.
#
# Bad patterns (any one is sufficient):
#   1. `UPTIME_KUMA_DISABLE_AUTH=true|1|yes|on` in a Kuma env
#      file, dotenv form.
#   2. `UPTIME_KUMA_DISABLE_AUTH: true|1|yes|on` as a YAML
#      mapping-form environment entry inside a Kuma service.
#   3. `- UPTIME_KUMA_DISABLE_AUTH=true|...` as a YAML list-form
#      environment entry inside a Kuma service.
#   4. The `--disable-auth` flag in a Kuma `command:` /
#      `entrypoint:` line, or in a settings-dump JSON with
#      `"disableAuth": true`.
#
# Good patterns are the inverse: variable absent, explicitly
# false / 0 / no / off, only mentioned inside a `#` comment, or
# the file is not a Kuma file at all (no Kuma image reference
# and no Kuma-specific knob).
#
# We require the file to fingerprint as Uptime Kuma related
# (presence of an `image:` reference to `louislam/uptime-kuma`,
# or another `UPTIME_KUMA_*` env key). A bare `--disable-auth`
# flag in some unrelated tool's command line does not fire.
#
# Bash 3.2+ / awk / coreutils only. No network calls.

set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  # `.env` / YAML use `#`; JSON does not have line comments but
  # operators sometimes write `// ...` — strip both, conservatively.
  sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' \
         -e 's://[^"]*$::' "$1"
}

is_kuma_scope() {
  local s="$1"
  printf '%s\n' "$s" \
    | grep -Eqi 'image:[[:space:]]*[^[:space:]]*louislam/uptime-kuma(:[^[:space:]]*)?[[:space:]]*$' \
    && return 0
  printf '%s\n' "$s" \
    | grep -Eq '(^|[[:space:]-])UPTIME_KUMA_[A-Z_]+[[:space:]]*[:=]' \
    && return 0
  # Settings-dump fingerprint: a JSON file with a "uptimeKumaVersion"
  # / "primaryBaseURL" / "appName": "Uptime Kuma" key.
  printf '%s\n' "$s" \
    | grep -Eqi '"(uptimeKumaVersion|primaryBaseURL)"[[:space:]]*:' \
    && return 0
  printf '%s\n' "$s" \
    | grep -Eqi '"appName"[[:space:]]*:[[:space:]]*"Uptime Kuma"' \
    && return 0
  return 1
}

is_truthy() {
  case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
    true|1|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

env_disable_auth_lines() {
  printf '%s\n' "$1" \
    | grep -E '^[[:space:]]*-?[[:space:]]*UPTIME_KUMA_DISABLE_AUTH[[:space:]]*[:=]'
}

extract_env_value() {
  printf '%s' "$1" \
    | sed -E 's/^[[:space:]]*-?[[:space:]]*UPTIME_KUMA_DISABLE_AUTH[[:space:]]*[:=][[:space:]]*//' \
    | sed -E 's/[[:space:]]+$//' \
    | sed -E 's/^"(.*)"$/\1/' \
    | sed -E "s/^'(.*)'$/\1/"
}

has_cli_disable_auth() {
  # Match the flag on a YAML `command:` / `entrypoint:` array or
  # string, or in a shell command line. We do not allow it inside
  # a quoted documentation string because comments are stripped
  # already; what remains is real config.
  printf '%s\n' "$1" \
    | grep -Eq '(^|[[:space:]"'\''[,])--disable-auth([[:space:]"'\''=,\]]|$)'
}

has_settings_disable_auth() {
  # JSON form: "disableAuth": true (case-sensitive key).
  printf '%s\n' "$1" \
    | grep -Eq '"disableAuth"[[:space:]]*:[[:space:]]*true\b'
}

is_bad() {
  local f="$1"
  local s
  s="$(strip_comments "$f")"
  is_kuma_scope "$s" || return 1

  # 1) env-var truthy?
  local lines line val
  lines="$(env_disable_auth_lines "$s")"
  if [ -n "$lines" ]; then
    while IFS= read -r line; do
      [ -n "$line" ] || continue
      val="$(extract_env_value "$line")"
      if is_truthy "$val"; then
        return 0
      fi
    done <<EOF
$lines
EOF
  fi

  # 2) CLI flag present?
  if has_cli_disable_auth "$s"; then
    return 0
  fi

  # 3) settings-dump disableAuth: true?
  if has_settings_disable_auth "$s"; then
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
