#!/usr/bin/env bash
# detect.sh — flag Salt master configurations that LLMs commonly emit
# with `open_mode: True`. The Salt master normally requires every new
# minion to present a public key that an operator explicitly accepts
# via `salt-key -a <id>`. Setting `open_mode: True` disables that
# accept step entirely: every minion key the master sees is auto-
# accepted on first contact, and any host on the network that can
# reach the master's `4505/4506` ports can claim a minion id (including
# the id of an existing trusted minion, which causes a key collision
# the master resolves by trusting the new key) and immediately receive
# `state.apply` / `cmd.run` payloads. The vendor docs flag this as a
# debug-only knob; the SaltStack hardening guide says it must never
# appear in a production master config.
#
# When asked "set up a Salt master" or "why won't my minions connect",
# LLMs routinely:
#   * Add `open_mode: True` to `/etc/salt/master` "to skip the key
#     accept step during bootstrap" and never remove it.
#   * Add `auto_accept: True` for the same reason — auto_accept also
#     bypasses the operator-in-the-loop check, but it at least requires
#     the master to have already seen the key file. open_mode skips
#     even that check.
#   * Pass `--open-mode` on `salt-master` startup in a systemd
#     `ExecStart=` line.
#
# Bad patterns we flag (any one is sufficient):
#   1. A Salt master config (YAML; the master file lives at
#      `/etc/salt/master` or under `/etc/salt/master.d/*.conf`) that
#      sets `open_mode: True` (case-insensitive; YAML accepts True /
#      true / yes / on as truthy).
#   2. The same config with `auto_accept: True` — same blast radius
#      from the LLM-output perspective; both are "skip the human" knobs
#      and both produce the same insecure outcome.
#   3. A `salt-master` invocation (shell / systemd unit / Dockerfile
#      CMD) that passes `--open-mode` or `--auto-accept` on the
#      command line.
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

is_salt_master_invocation() {
  local s="$1"
  printf '%s\n' "$s" | grep -Eiq '(^|[[:space:]/"=])salt-master\b'
}

# YAML truthy: True/true/yes/on (and the capitalised forms).
yaml_truthy_match() {
  # yaml_truthy_match <key> <text>
  printf '%s\n' "$2" \
    | grep -Eiq "^[[:space:]]*${1}:[[:space:]]*(True|true|yes|on)[[:space:]]*$"
}

invocation_has_flag() {
  # invocation_has_flag <flag> <text>
  local flag="$1"; local text="$2"
  local normalized
  normalized="$(printf '%s\n' "$text" | tr -d '",[]')"
  printf '%s\n' "$normalized" \
    | grep -Eiq "(^|[^[:alnum:]_-])${flag}([^[:alnum:]_-]|=|\$)"
}

is_bad() {
  local f="$1"
  local stripped
  stripped="$(strip_comments "$f")"

  # Rule 3 — invocation form.
  if is_salt_master_invocation "$stripped"; then
    if invocation_has_flag '--open-mode' "$stripped"; then return 0; fi
    if invocation_has_flag '--auto-accept' "$stripped"; then return 0; fi
    # Fall through — an invocation with neither flag is fine.
  fi

  # Rules 1 & 2 — YAML form. We do not require a "this is a Salt
  # master config" marker because the keys `open_mode` and
  # `auto_accept` are Salt-specific enough that any file that sets
  # them as truthy at top-level is, in practice, a Salt master config.
  if yaml_truthy_match 'open_mode' "$stripped"; then return 0; fi
  if yaml_truthy_match 'auto_accept' "$stripped"; then return 0; fi

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
