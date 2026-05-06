#!/usr/bin/env bash
# detect.sh — flag BookStack (Laravel-based wiki) configurations that
# LLMs routinely emit with `APP_KEY` empty, a literal placeholder, or
# a too-short base64 payload. APP_KEY drives cookie signing and
# session/field encryption; an attacker who knows it can forge
# sessions and decrypt encrypted DB fields.
#
# Bad patterns (any one is sufficient, on a snippet that mentions
# BookStack OR sets APP_KEY together with at least one other
# Laravel-style APP_*/DB_* key, narrowing scope to a real config):
#
#   1. APP_KEY=  with empty / whitespace-only / quoted-empty value.
#   2. APP_KEY=base64:  with no payload after the colon.
#   3. APP_KEY=base64:<payload> where <payload> length (after
#      stripping quotes) is < 40 chars (a real AES-256 key encodes to
#      44 chars; we accept >=40 to leave a small margin for
#      alternative encodings).
#   4. APP_KEY=<value> matching a known placeholder string,
#      case-insensitive.
#
# We do NOT flag APP_KEY=${VAR} / APP_KEY=$ENV style indirections.
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  sed -E -e 's/^[[:space:]]*#.*$//' -e 's/[[:space:]]+#.*$//' "$1"
}

mentions_bookstack_scope() {
  local s="$1"
  printf '%s\n' "$s" | grep -Eiq 'bookstack' && return 0
  # Or: APP_KEY co-located with at least one other canonical Laravel key.
  if printf '%s\n' "$s" | grep -Eq '(^|[[:space:]"])APP_KEY[[:space:]]*[:=]'; then
    if printf '%s\n' "$s" \
        | grep -Eq '(^|[[:space:]"])(APP_URL|DB_DATABASE|DB_USERNAME|MAIL_FROM_ADDRESS|SESSION_DRIVER|CACHE_DRIVER)[[:space:]]*[:=]'; then
      return 0
    fi
  fi
  return 1
}

# Extract APP_KEY raw value (without surrounding quotes). We handle
# both `KEY=value` (env style) and `KEY: value` (YAML style).
extract_app_key_values() {
  local s="$1"
  # env-style
  printf '%s\n' "$s" \
    | grep -E '(^|[[:space:]"])APP_KEY[[:space:]]*=' \
    | sed -E 's/.*APP_KEY[[:space:]]*=[[:space:]]*//' \
    | sed -E 's/[[:space:]]+$//' \
    | sed -E 's/^"//; s/"$//; s/^'\''//; s/'\''$//'
  # YAML-style: APP_KEY: "value"
  printf '%s\n' "$s" \
    | grep -E '(^|[[:space:]])APP_KEY[[:space:]]*:[[:space:]]*' \
    | sed -E 's/.*APP_KEY[[:space:]]*:[[:space:]]*//' \
    | sed -E 's/[[:space:]]+$//' \
    | sed -E 's/^"//; s/"$//; s/^'\''//; s/'\''$//'
}

is_indirection() {
  # Values that are env/template references — not the secret itself.
  local v="$1"
  case "$v" in
    '${'*'}'|'$'[A-Z_]*|'$ENV'*|'$('*')'|'{{'*'}}'|'<%='*'%>') return 0 ;;
  esac
  # Bash-style: starts with $ and a letter
  printf '%s' "$v" | grep -Eq '^\$[A-Za-z_]' && return 0
  # ${...}
  printf '%s' "$v" | grep -Eq '^\$\{[^}]+\}$' && return 0
  return 1
}

is_placeholder_literal() {
  local v
  v="$(printf '%s' "$1" | tr 'A-Z' 'a-z')"
  case "$v" in
    changeme|please_change_me|please-change-me|somerandomstring|somerandomkeygoeshere|generate_this_key|generate-this-key|your_app_key_here|your-app-key-here|secret|yourkeyhere|your_key_here) return 0 ;;
    *) return 1 ;;
  esac
}

is_bad_app_key_value() {
  local v="$1"
  # 1. empty
  if [ -z "$v" ]; then return 0; fi
  # indirection => not bad (out of scope of this file)
  if is_indirection "$v"; then return 1; fi
  # 4. literal placeholder
  if is_placeholder_literal "$v"; then return 0; fi
  # 2 & 3. base64: prefix
  case "$v" in
    base64:*)
      local payload="${v#base64:}"
      if [ -z "$payload" ]; then return 0; fi
      if [ "${#payload}" -lt 40 ]; then return 0; fi
      # Real-looking key; check it's a known placeholder spelled in
      # base64 form.
      local lower
      lower="$(printf '%s' "$payload" | tr 'A-Z' 'a-z')"
      case "$lower" in
        somerandomkeygoeshere*|generate_this_key*|generate-this-key*|placeholder*) return 0 ;;
      esac
      return 1
      ;;
  esac
  # Bare value, not base64: prefix, not a known placeholder, not
  # indirection. BookStack/Laravel actually requires the base64:
  # prefix so this is also bad — but only flag if it's clearly not a
  # generated key (very short, or matches placeholder substrings).
  if [ "${#v}" -lt 16 ]; then return 0; fi
  return 1
}

is_bad_file() {
  local f="$1"
  local stripped
  stripped="$(strip_comments "$f")"
  mentions_bookstack_scope "$stripped" || return 1

  while IFS= read -r v; do
    # An empty `read` line still counts: APP_KEY= with nothing after it
    # produces an empty string, which we want to flag.
    if is_bad_app_key_value "$v"; then return 0; fi
  done < <(extract_app_key_values "$stripped")
  return 1
}

for f in "$@"; do
  case "$f" in
    *samples/bad/*) bad_total=$((bad_total+1)) ;;
    *samples/good/*) good_total=$((good_total+1)) ;;
  esac
  if is_bad_file "$f"; then
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
