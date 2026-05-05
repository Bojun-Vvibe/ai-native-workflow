#!/usr/bin/env bash
# detect.sh — flag Mattermost server configurations where
# `ServiceSettings.EnableDeveloper` and/or `ServiceSettings.EnableTesting`
# are set to `true`. The Mattermost handbook is explicit that these
# two flags are intended for local dev only:
#
#   * `EnableDeveloper: true` surfaces unhandled JavaScript exceptions
#     to every connected client and exposes verbose stack traces in the
#     UI. It also relaxes a number of CSP headers.
#   * `EnableTesting: true` mounts the `/test/*` HTTP routes (e.g.
#     `/api/v4/test/email`, `/api/v4/test/site_url`,
#     `/api/v4/test/url`) which are unauthenticated SSRF primitives:
#     the server will issue arbitrary outbound HTTP requests on the
#     caller's behalf to verify reachability.
#
# When asked "give me a Mattermost config.json" or "set up
# Mattermost for testing", LLMs routinely emit both flags as `true`
# without flagging that they MUST be `false` in production. The
# Mattermost ServiceSettings JSON shape is stable across the v5/v6/v7/v8
# server releases and across the chart-rendered configmap form.
#
# Bad patterns we flag (any one is sufficient):
#   1. `config.json`-style JSON containing a `ServiceSettings` object
#      with `EnableDeveloper: true` or `EnableTesting: true`.
#   2. Environment-variable form: `MM_SERVICESETTINGS_ENABLEDEVELOPER=true`
#      or `MM_SERVICESETTINGS_ENABLETESTING=true` (the documented env
#      override Mattermost itself reads at boot).
#   3. CLI override: `mattermost --config ... -ServiceSettings.EnableDeveloper=true`
#      or the `mmctl config set ServiceSettings.EnableDeveloper true` form.
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  # JSON does not have comments, but config.json snippets in LLM
  # output frequently include `//` annotations. Strip them.
  sed -E -e 's://[^"]*$::' -e 's/^[[:space:]]*#.*$//' "$1"
}

is_mattermost_json() {
  local s="$1"
  printf '%s\n' "$s" | grep -Eq '"ServiceSettings"[[:space:]]*:[[:space:]]*\{'
}

is_mattermost_env() {
  local s="$1"
  printf '%s\n' "$s" | grep -Eiq 'MM_SERVICESETTINGS_(ENABLEDEVELOPER|ENABLETESTING)[[:space:]]*='
}

is_mattermost_cli() {
  local s="$1"
  printf '%s\n' "$s" \
    | grep -Eiq '(mattermost|mmctl)\b.*ServiceSettings\.(EnableDeveloper|EnableTesting)'
}

# Walk a `ServiceSettings` JSON object and emit value tokens for the
# named field. Tolerates other keys and nested objects sitting
# alongside. Pure POSIX awk: tracks brace depth manually and uses
# index/substr for capture (BSD awk has no match() capture groups).
service_settings_field() {
  local field="$1" text="$2"
  awk -v field="$field" '
    BEGIN { in_ss=0; depth=0; rx_open="\"ServiceSettings\"[[:space:]]*:[[:space:]]*\\{" }
    {
      line=$0
      if (!in_ss) {
        if (line ~ rx_open) { in_ss=1; depth=1 } else { next }
      } else {
        tmp=line; n_open=gsub(/\{/,"{",tmp)
        tmp=line; n_close=gsub(/\}/,"}",tmp)
        depth += n_open - n_close
        if (depth <= 0) { in_ss=0; next }
      }
      if (in_ss) {
        rx="\"" field "\"[[:space:]]*:[[:space:]]*"
        if (match(line, rx)) {
          rest=substr(line, RSTART+RLENGTH)
          # Trim leading whitespace then capture the bare token.
          sub(/^[[:space:]]+/, "", rest)
          # Drop a leading quote if present so the token is bare.
          sub(/^"/, "", rest)
          # Capture up to the next non-token char.
          if (match(rest, /[^a-zA-Z0-9_]/)) {
            v=substr(rest, 1, RSTART-1)
          } else {
            v=rest
          }
          if (v != "") print v
        }
      }
    }
  ' <<<"$text"
}

env_field_value() {
  # MM_SERVICESETTINGS_ENABLEDEVELOPER=true     -> true
  # export MM_SERVICESETTINGS_ENABLETESTING="true"
  local field="$1" text="$2"
  printf '%s\n' "$text" \
    | grep -Eio "MM_SERVICESETTINGS_${field}[[:space:]]*=[[:space:]]*[\"']?[a-z0-9]+" \
    | sed -E "s/.*=[[:space:]]*[\"']?//"
}

cli_field_value() {
  # -ServiceSettings.EnableDeveloper=true       (mattermost server flag)
  # mmctl config set ServiceSettings.EnableTesting true
  local field="$1" text="$2"
  # form A: -ServiceSettings.<field>=true
  printf '%s\n' "$text" \
    | grep -Eio -- "-?ServiceSettings\.${field}[=[:space:]]+[a-zA-Z0-9]+" \
    | sed -E 's/.*[=[:space:]]+//'
}

is_truthy() {
  case "$(printf '%s' "$1" | tr 'A-Z' 'a-z')" in
    true|1|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

is_bad() {
  local f="$1"
  local stripped
  stripped="$(strip_comments "$f")"

  if is_mattermost_json "$stripped"; then
    for field in EnableDeveloper EnableTesting; do
      while IFS= read -r v; do
        [ -z "$v" ] && continue
        if is_truthy "$v"; then return 0; fi
      done < <(service_settings_field "$field" "$stripped")
    done
  fi

  if is_mattermost_env "$stripped"; then
    for field in ENABLEDEVELOPER ENABLETESTING; do
      while IFS= read -r v; do
        [ -z "$v" ] && continue
        if is_truthy "$v"; then return 0; fi
      done < <(env_field_value "$field" "$stripped")
    done
  fi

  if is_mattermost_cli "$stripped"; then
    for field in EnableDeveloper EnableTesting; do
      while IFS= read -r v; do
        [ -z "$v" ] && continue
        if is_truthy "$v"; then return 0; fi
      done < <(cli_field_value "$field" "$stripped")
      # mmctl form: `mmctl config set ServiceSettings.<field> true`
      if printf '%s\n' "$stripped" \
        | grep -Eiq "mmctl[[:space:]]+config[[:space:]]+set[[:space:]]+ServiceSettings\.${field}[[:space:]]+(true|1|yes|on)\\b"; then
        return 0
      fi
    done
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
