#!/usr/bin/env bash
# detect.sh — flag Nomad agent configs that leave the ACL system
# disabled or unconfigured. See README.md for rationale.
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  # HCL: # and // line comments. JSON: technically no comments, but
  # we strip // to be safe (some examples use JSONC). YAML/Dockerfile: #.
  # We don't strip /* */ block comments — rare in agent configs and
  # the cost of missing them is a missed false-positive only.
  sed -E -e 's|^[[:space:]]*//.*$||' \
         -e 's|[[:space:]]+//.*$||' \
         -e 's/^[[:space:]]*#.*$//' \
         -e 's/[[:space:]]+#.*$//' "$1"
}

# Scope: does this snippet look like a Nomad agent config?
is_nomad_agent_config() {
  local s="$1"
  # Image + agent command
  printf '%s\n' "$s" | grep -Eiq 'hashicorp/nomad' \
    && printf '%s\n' "$s" | grep -Eiq 'nomad[[:space:]]+agent\b' && return 0
  # Direct CLI: `nomad agent -server` or `nomad agent -client`
  printf '%s\n' "$s" | grep -Eiq '(^|[[:space:]/"=])nomad[[:space:]]+agent[[:space:]]+-(server|client|config|dev)\b' && return 0
  # NOMAD_* env vars (but not NOMAD_ADDR alone, which is client tooling)
  if printf '%s\n' "$s" | grep -Eo 'NOMAD_[A-Z_]+' | grep -Ev '^NOMAD_ADDR$' | grep -q .; then
    return 0
  fi
  # HCL: server { ... enabled = true } or client { ... enabled = true }
  # Use awk to check that an `enabled = true` appears within a server/client block.
  if awk '
    /^[[:space:]]*(server|client)[[:space:]]*\{/ { in_block=1; depth=1; next }
    in_block {
      for (i=1;i<=length($0);i++) {
        c=substr($0,i,1)
        if (c=="{") depth++
        else if (c=="}") { depth--; if (depth==0) { in_block=0; break } }
      }
      if (match($0, /enabled[[:space:]]*=[[:space:]]*"?(true|1)"?([^a-zA-Z0-9_]|$)/)) found=1
    }
    END { exit found?0:1 }
  ' "$f"; then
    return 0
  fi
  # JSON: "server": { "enabled": true } or "client": { "enabled": true }
  if printf '%s\n' "$s" | tr -d '\n' | grep -Eq '"(server|client)"[[:space:]]*:[[:space:]]*\{[^{}]*"enabled"[[:space:]]*:[[:space:]]*true'; then
    return 0
  fi
  return 1
}

# Does an `acl` block / attribute set enabled = true?
has_acl_enabled_true() {
  local s="$1"
  # HCL block form: acl { ... enabled = true ... } — scan the block.
  if awk '
    /^[[:space:]]*acl[[:space:]]*\{/ { in_block=1; depth=1; next }
    in_block {
      for (i=1;i<=length($0);i++) {
        c=substr($0,i,1)
        if (c=="{") depth++
        else if (c=="}") { depth--; if (depth==0) { in_block=0; break } }
      }
      if (match($0, /enabled[[:space:]]*=[[:space:]]*"?(true|1)"?([^a-zA-Z0-9_]|$)/)) found=1
    }
    END { exit found?0:1 }
  ' "$f"; then
    return 0
  fi
  # HCL2 attribute form: acl = { enabled = true }
  if printf '%s\n' "$s" | tr -d '\n' \
       | grep -Eq 'acl[[:space:]]*=[[:space:]]*\{[^{}]*enabled[[:space:]]*=[[:space:]]*"?(true|1)"?'; then
    return 0
  fi
  # JSON form
  if printf '%s\n' "$s" | tr -d '\n' \
       | grep -Eq '"acl"[[:space:]]*:[[:space:]]*\{[^{}]*"enabled"[[:space:]]*:[[:space:]]*true'; then
    return 0
  fi
  # Env form
  if printf '%s\n' "$s" \
       | grep -Eiq '(^|[[:space:]"'\''])NOMAD_ACL_ENABLED[[:space:]]*[=:][[:space:]]*"?(true|1|yes|on)"?'; then
    return 0
  fi
  return 1
}

# Does an `acl` block / attribute set enabled = false explicitly?
has_acl_enabled_false() {
  local s="$1"
  if awk '
    /^[[:space:]]*acl[[:space:]]*\{/ { in_block=1; depth=1; next }
    in_block {
      for (i=1;i<=length($0);i++) {
        c=substr($0,i,1)
        if (c=="{") depth++
        else if (c=="}") { depth--; if (depth==0) { in_block=0; break } }
      }
      if (match($0, /enabled[[:space:]]*=[[:space:]]*"?(false|0)"?([^a-zA-Z0-9_]|$)/)) found=1
    }
    END { exit found?0:1 }
  ' "$f"; then
    return 0
  fi
  if printf '%s\n' "$s" | tr -d '\n' \
       | grep -Eq 'acl[[:space:]]*=[[:space:]]*\{[^{}]*enabled[[:space:]]*=[[:space:]]*"?(false|0)"?'; then
    return 0
  fi
  if printf '%s\n' "$s" | tr -d '\n' \
       | grep -Eq '"acl"[[:space:]]*:[[:space:]]*\{[^{}]*"enabled"[[:space:]]*:[[:space:]]*false'; then
    return 0
  fi
  if printf '%s\n' "$s" \
       | grep -Eiq '(^|[[:space:]"'\''])NOMAD_ACL_ENABLED[[:space:]]*[=:][[:space:]]*"?(false|0|no|off)"?'; then
    return 0
  fi
  return 1
}

is_bad_file() {
  local f_orig="$1"
  # Strip comments to a temp working buffer for line-oriented awk;
  # we need a real file for awk's block scanner so write to a temp.
  local tmp
  tmp="$(mktemp)"
  strip_comments "$f_orig" > "$tmp"
  local s
  s="$(cat "$tmp")"
  # Make $f visible to nested awk calls inside the helper functions.
  f="$tmp"

  if ! is_nomad_agent_config "$s"; then rm -f "$tmp"; return 1; fi

  if has_acl_enabled_false "$s"; then rm -f "$tmp"; return 0; fi
  if ! has_acl_enabled_true "$s"; then rm -f "$tmp"; return 0; fi

  rm -f "$tmp"
  return 1
}

for f_arg in "$@"; do
  case "$f_arg" in
    *samples/bad/*) bad_total=$((bad_total+1)) ;;
    *samples/good/*) good_total=$((good_total+1)) ;;
  esac
  if is_bad_file "$f_arg"; then
    echo "BAD  $f_arg"
    case "$f_arg" in
      *samples/bad/*) bad_hits=$((bad_hits+1)) ;;
      *samples/good/*) good_hits=$((good_hits+1)) ;;
    esac
  else
    echo "GOOD $f_arg"
  fi
done

status="FAIL"
if [ "$bad_hits" = "$bad_total" ] && [ "$good_hits" = 0 ]; then
  status="PASS"
fi
echo "bad=${bad_hits}/${bad_total} good=${good_hits}/${good_total} ${status}"
[ "$status" = "PASS" ]
