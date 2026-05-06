#!/usr/bin/env bash
# detect.sh — flag Prosody XMPP server configurations that LLMs
# routinely emit with `c2s_require_encryption` (and/or its
# server-to-server twin `s2s_require_encryption`) explicitly turned
# off. Prosody is a Lua-configured XMPP server. Encryption on the
# client-to-server (c2s) channel is what protects user passwords
# during SASL PLAIN; turning it off downgrades every client login to
# plaintext on the wire.
#
# Bad patterns (any one is sufficient):
#   1. Prosody Lua config with `c2s_require_encryption = false`.
#   2. Prosody Lua config with `s2s_require_encryption = false`
#      AND no `s2s_secure_auth` override. (s2s without TLS leaks
#      every federated message between servers.)
#   3. Prosody Lua config that sets the legacy
#      `require_encryption = false` knob (pre-0.10) without any
#      stricter per-channel override.
#   4. Docker / systemd env exposing
#      `PROSODY_C2S_REQUIRE_ENCRYPTION=false` (or the s2s twin) and
#      no countervailing override file.
#
# Good patterns are the inverse: the encryption-required toggles are
# either absent (defaults to true on modern Prosody) or set to true.
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  # Prosody Lua config uses `--` line comments and `--[[ ]]` blocks.
  # We only need line-comment stripping for our patterns; block
  # comments are rare in generated configs.
  sed -E -e 's@[[:space:]]+--.*$@@' -e 's@^[[:space:]]*--.*$@@' \
         -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

is_prosody_config() {
  local s="$1"
  # Prosody Lua marker: a `VirtualHost` or `Component` directive,
  # OR a top-level `modules_enabled` table, OR any of the
  # encryption-related knobs we care about.
  printf '%s\n' "$s" | grep -Eq '(^|[[:space:]])(VirtualHost|Component)[[:space:]]+"' && return 0
  printf '%s\n' "$s" | grep -Eq '^[[:space:]]*modules_enabled[[:space:]]*=' && return 0
  printf '%s\n' "$s" | grep -Eq '^[[:space:]]*(c2s|s2s)_require_encryption[[:space:]]*=' && return 0
  printf '%s\n' "$s" | grep -Eq '^[[:space:]]*require_encryption[[:space:]]*=' && return 0
  return 1
}

is_prosody_env() {
  local s="$1"
  printf '%s\n' "$s" | grep -Eq 'PROSODY_(C2S|S2S)_REQUIRE_ENCRYPTION\b'
}

config_has_c2s_false() {
  printf '%s\n' "$1" \
    | grep -Eq '^[[:space:]]*c2s_require_encryption[[:space:]]*=[[:space:]]*false\b'
}

config_has_s2s_false() {
  printf '%s\n' "$1" \
    | grep -Eq '^[[:space:]]*s2s_require_encryption[[:space:]]*=[[:space:]]*false\b'
}

config_has_s2s_secure_auth_true() {
  printf '%s\n' "$1" \
    | grep -Eq '^[[:space:]]*s2s_secure_auth[[:space:]]*=[[:space:]]*true\b'
}

config_has_legacy_require_false() {
  # Pre-0.10 single knob; matches `require_encryption = false` but
  # not `c2s_require_encryption` / `s2s_require_encryption`.
  printf '%s\n' "$1" \
    | grep -Eq '^[[:space:]]*require_encryption[[:space:]]*=[[:space:]]*false\b' \
    && ! printf '%s\n' "$1" \
        | grep -Eq '^[[:space:]]*(c2s|s2s)_require_encryption[[:space:]]*=[[:space:]]*true\b'
}

env_get_value() {
  local s="$1" key="$2"
  printf '%s\n' "$s" \
    | grep -E "(^|[[:space:]]|^export[[:space:]]+)${key}=" \
    | head -n1 \
    | sed -E "s/.*${key}=//" \
    | sed -E 's/[[:space:]].*$//' \
    | sed -E 's/^"(.*)"$/\1/' \
    | sed -E "s/^'(.*)'\$/\1/"
}

env_falsy() {
  local v
  v="$(printf '%s' "$1" | tr 'A-Z' 'a-z')"
  case "$v" in
    0|false|no|off) return 0 ;;
    *) return 1 ;;
  esac
}

is_bad_config() {
  local s="$1"
  is_prosody_config "$s" || return 1

  if config_has_c2s_false "$s"; then return 0; fi
  if config_has_s2s_false "$s" && ! config_has_s2s_secure_auth_true "$s"; then
    return 0
  fi
  if config_has_legacy_require_false "$s"; then return 0; fi
  return 1
}

is_bad_env() {
  local s="$1"
  is_prosody_env "$s" || return 1

  local c2s s2s
  c2s="$(env_get_value "$s" PROSODY_C2S_REQUIRE_ENCRYPTION)"
  s2s="$(env_get_value "$s" PROSODY_S2S_REQUIRE_ENCRYPTION)"
  if [ -n "$c2s" ] && env_falsy "$c2s"; then return 0; fi
  if [ -n "$s2s" ] && env_falsy "$s2s"; then return 0; fi
  return 1
}

is_bad() {
  local f="$1"
  local stripped
  stripped="$(strip_comments "$f")"
  is_bad_config "$stripped" && return 0
  is_bad_env    "$stripped" && return 0
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
