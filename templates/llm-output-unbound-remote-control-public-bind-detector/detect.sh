#!/usr/bin/env bash
# detect.sh — flag unbound remote-control configurations that LLMs
# commonly emit with the control channel bound to a non-loopback
# address. The unbound recursive resolver ships an out-of-band control
# socket (`unbound-control`) that, when enabled, accepts commands like
# `reload`, `flush_zone`, `local_data` (cache poisoning primitive),
# `dump_cache`, and `stop`. The hardening default is to bind the
# control channel to `127.0.0.1` (and `::1`) and gate it behind an
# mTLS pair (`control-key-file` / `control-cert-file`).
#
# When asked "set up unbound with remote control", LLMs routinely:
#   * Set `control-enable: yes` AND `control-interface: 0.0.0.0`
#     (or `::`, or a routable address) without changing
#     `control-use-cert: yes` to a deliberate hardened pair.
#   * Set `control-use-cert: no` while leaving `control-interface`
#     at a non-loopback address — the channel becomes a plaintext
#     command shell reachable from the network.
#   * Pass `unbound-control` CLI flags `-s 0.0.0.0@8953` in a wrapper
#     script that also `unbound-control-setup`s the binary into
#     listen-everywhere mode.
#
# Bad patterns we flag (any one is sufficient):
#   1. A `remote-control:` block whose `control-enable:` is `yes`
#      AND whose `control-interface:` is a non-loopback literal
#      (anything other than `127.0.0.1`, `::1`, `localhost`, or a
#      `127.x.x.x` literal).
#   2. A `remote-control:` block with `control-use-cert: no`
#      regardless of interface — plaintext control is unsafe even on
#      loopback when the host is multi-tenant, and is never what an
#      LLM should emit by default.
#   3. An `unbound-control` invocation that passes
#      `-s <non-loopback>@<port>` (the `-s` flag picks the server
#      address; aiming it at a non-loopback host means the daemon
#      side is listening publicly).
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

is_unbound_yaml() {
  # unbound.conf is YAML-ish (key: value, indentation-scoped blocks).
  # The strongest marker is a `server:` or `remote-control:` top-level
  # block.
  local s="$1"
  printf '%s\n' "$s" | grep -Eiq '^[[:space:]]*remote-control:[[:space:]]*$' \
    || printf '%s\n' "$s" | grep -Eiq '^[[:space:]]*server:[[:space:]]*$'
}

is_unbound_control_invocation() {
  local s="$1"
  printf '%s\n' "$s" | grep -Eiq '(^|[[:space:]/"=])unbound-control\b'
}

# Walk the conf file with an indentation-aware awk pass and emit the
# values that sit inside the `remote-control:` block. We do not need a
# real parser — unbound.conf is flat key/value at one indentation
# level under each top-level header.
remote_control_field() {
  # remote_control_field <field-name> <text>  -> prints values, one per line
  local field="$1"; local text="$2"
  awk -v field="$field" '
    function indent(s,   i) { i = match(s, /[^ ]/); return (i == 0 ? 0 : i - 1) }
    BEGIN { in_rc=0; rc_indent=-1 }
    {
      line=$0
      if (line ~ /^[[:space:]]*$/) next
      ind = indent(line)
      stripped = line
      sub(/^[[:space:]]+/, "", stripped)

      if (in_rc && ind <= rc_indent) { in_rc=0; rc_indent=-1 }

      if (!in_rc && stripped ~ /^remote-control:[[:space:]]*$/) {
        in_rc=1; rc_indent=ind; next
      }
      if (in_rc && ind > rc_indent) {
        # Match `field: value` (value may be quoted).
        if (match(stripped, "^" field ":[[:space:]]*")) {
          val = substr(stripped, RLENGTH + 1)
          gsub(/^[[:space:]]+|[[:space:]]+$/, "", val)
          gsub(/^"|"$/, "", val)
          print val
        }
      }
    }
  ' <<<"$text"
}

interface_is_loopback() {
  # Accept exact loopback literals only.
  local v="$1"
  case "$v" in
    127.0.0.1|::1|localhost|127.*) return 0 ;;
    *) return 1 ;;
  esac
}

invocation_targets_non_loopback_server() {
  # `unbound-control -s 192.0.2.10@8953 ...` or `--server=...`
  local s="$1"
  local normalized
  normalized="$(printf '%s\n' "$s" | tr -d '",[]')"
  # Pull out the value after `-s` or `--server[ =]`.
  local hits
  hits="$(printf '%s\n' "$normalized" \
    | grep -Eo '(^|[^[:alnum:]_-])(-s|--server)[[:space:]=]+[^[:space:]]+' \
    || true)"
  if [ -z "$hits" ]; then return 1; fi
  while IFS= read -r line; do
    # Strip leading flag.
    local v
    v="$(printf '%s\n' "$line" | sed -E 's/^.*(-s|--server)[[:space:]=]+//')"
    # Drop `@port` suffix if present.
    v="${v%@*}"
    if ! interface_is_loopback "$v"; then return 0; fi
  done <<<"$hits"
  return 1
}

is_bad() {
  local f="$1"
  local stripped
  stripped="$(strip_comments "$f")"

  # Rule 3 — unbound-control invocation with non-loopback server.
  if is_unbound_control_invocation "$stripped" && ! is_unbound_yaml "$stripped"; then
    if invocation_targets_non_loopback_server "$stripped"; then return 0; fi
    return 1
  fi

  # Rules 1 & 2 — unbound.conf with a remote-control: block.
  if is_unbound_yaml "$stripped"; then
    local enable use_cert ifaces
    enable="$(remote_control_field 'control-enable' "$stripped" | tail -n1)"
    use_cert="$(remote_control_field 'control-use-cert' "$stripped" | tail -n1)"
    ifaces="$(remote_control_field 'control-interface' "$stripped")"

    # If remote-control isn't enabled, neither rule fires.
    if [ -z "$enable" ] || [ "$(printf '%s\n' "$enable" | tr 'A-Z' 'a-z')" != "yes" ]; then
      return 1
    fi

    # Rule 2 — plaintext control channel.
    if [ -n "$use_cert" ] && [ "$(printf '%s\n' "$use_cert" | tr 'A-Z' 'a-z')" = "no" ]; then
      return 0
    fi

    # Rule 1 — any non-loopback control-interface entry is bad.
    if [ -n "$ifaces" ]; then
      while IFS= read -r v; do
        [ -z "$v" ] && continue
        if ! interface_is_loopback "$v"; then return 0; fi
      done <<<"$ifaces"
    fi
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
