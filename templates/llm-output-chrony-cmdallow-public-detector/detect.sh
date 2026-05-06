#!/usr/bin/env bash
# detect.sh — flag chrony NTP daemon configurations that LLMs
# routinely emit with the command/control socket exposed to the
# public network. chrony's `cmdallow` directive controls who may
# issue chronyc commands (settime, makestep, burst, dump, sources,
# tracking…) over the network; `bindcmdaddress` controls where the
# control socket binds. By default the socket binds to localhost
# only and accepts only local commands. LLMs routinely break that
# default in two distinct ways:
#
# Bad patterns (any one is sufficient):
#   1. `cmdallow all` (or `cmdallow 0.0.0.0/0` / `cmdallow ::/0`) —
#      grants every IP the right to issue chronyc commands.
#   2. `cmdallow <subnet>` paired with `bindcmdaddress 0.0.0.0`
#      (or `::`, or any non-loopback address) — the socket is open
#      on a public interface AND the ACL admits external peers.
#   3. `bindcmdaddress 0.0.0.0` (or `::`) with no `cmdallow` line at
#      all is *not* flagged, because chrony's default ACL denies
#      remote commands. We only flag combinations that actually
#      grant remote access.
#
# Good patterns are the inverse: defaults left alone, explicit
# loopback bind, or `cmddeny all`.
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  # chrony.conf uses `#` and `!` line comments.
  sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' \
         -e 's/[[:space:]]+!.*$//' -e 's/^[[:space:]]*!.*$//' "$1"
}

is_chrony_config() {
  local s="$1"
  # chrony marker: a `pool`, `server`, `peer`, `driftfile`,
  # `makestep`, `rtcsync`, `cmdallow`, `cmddeny`, or
  # `bindcmdaddress` directive.
  printf '%s\n' "$s" \
    | grep -Eq '^[[:space:]]*(pool|server|peer|driftfile|makestep|rtcsync|cmdallow|cmddeny|bindcmdaddress|allow|deny)\b'
}

config_cmdallow_all() {
  # `cmdallow` with no argument == allow-all (chrony semantics);
  # also `cmdallow all`, `cmdallow 0.0.0.0/0`, `cmdallow ::/0`.
  printf '%s\n' "$1" | grep -Eq '^[[:space:]]*cmdallow[[:space:]]*$' && return 0
  printf '%s\n' "$1" \
    | grep -Eq '^[[:space:]]*cmdallow[[:space:]]+(all|0\.0\.0\.0/0|::/0)[[:space:]]*$' && return 0
  return 1
}

config_cmdallow_subnet() {
  # Any `cmdallow <something>` that is not `all` / 0.0.0.0/0 / ::/0
  # AND not a literal loopback (127.0.0.0/8 / ::1).
  printf '%s\n' "$1" \
    | grep -E '^[[:space:]]*cmdallow[[:space:]]+[^[:space:]]+' \
    | grep -Ev '^[[:space:]]*cmdallow[[:space:]]+(all|0\.0\.0\.0/0|::/0)[[:space:]]*$' \
    | grep -Ev '^[[:space:]]*cmdallow[[:space:]]+(127\.[0-9.]+(/[0-9]+)?|::1(/128)?)[[:space:]]*$' \
    | grep -q .
}

config_bindcmd_public() {
  # bindcmdaddress to a non-loopback address. Loopback forms:
  # 127.0.0.1, 127.x.y.z, ::1.
  printf '%s\n' "$1" \
    | grep -E '^[[:space:]]*bindcmdaddress[[:space:]]+[^[:space:]]+' \
    | grep -Ev '^[[:space:]]*bindcmdaddress[[:space:]]+(127\.[0-9.]+|::1)[[:space:]]*$' \
    | grep -q .
}

config_cmddeny_all() {
  printf '%s\n' "$1" | grep -Eq '^[[:space:]]*cmddeny[[:space:]]*$' && return 0
  printf '%s\n' "$1" \
    | grep -Eq '^[[:space:]]*cmddeny[[:space:]]+(all|0\.0\.0\.0/0|::/0)[[:space:]]*$' && return 0
  return 1
}

is_bad_config() {
  local s="$1"
  is_chrony_config "$s" || return 1

  # Pattern 1: cmdallow all — bad regardless of bind.
  if config_cmdallow_all "$s"; then
    # Unless an explicit `cmddeny all` *follows or precedes* it
    # AND there is no later cmdallow… chrony actually applies the
    # last matching rule, so a deliberate `cmddeny all` after the
    # allow does override. Keep it simple: if cmddeny all is
    # present at all, treat it as a deliberate clamp.
    config_cmddeny_all "$s" && return 1
    return 0
  fi

  # Pattern 2: cmdallow on a real subnet AND public bind.
  if config_cmdallow_subnet "$s" && config_bindcmd_public "$s"; then
    return 0
  fi

  return 1
}

is_bad() {
  local f="$1"
  local stripped
  stripped="$(strip_comments "$f")"
  is_bad_config "$stripped"
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
