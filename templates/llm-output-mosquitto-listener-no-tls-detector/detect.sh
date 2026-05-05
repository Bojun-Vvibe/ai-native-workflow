#!/usr/bin/env bash
# detect.sh — flag Mosquitto MQTT broker configurations that LLMs commonly
# emit with a non-loopback `listener` and no TLS. The MQTT default port is
# 1883 (cleartext) and 8883 (mTLS). LLMs asked "set up an MQTT broker for
# my IoT fleet" routinely answer with `listener 1883 0.0.0.0` and no
# `cafile` / `certfile` / `keyfile` — credentials and payloads then cross
# the public internet in cleartext, which the MQTT spec itself flags as
# insecure unless paired with transport-layer crypto.
#
# Bad patterns we flag:
#   1. `listener <port> <addr>` where addr is NOT 127.0.0.1 / ::1 /
#      localhost AND the same listener block has no `cafile`, `certfile`,
#      `keyfile` (TLS material missing).
#   2. `listener <port>` (no address — Mosquitto binds to all interfaces
#      by default) AND no TLS material in the same block.
#   3. `port 1883` at the file's top-level (legacy single-listener form)
#      with `bind_address` absent or set to a non-loopback address AND no
#      TLS keys at top level.
#   4. Docker / compose `command:` or Dockerfile `CMD` running `mosquitto`
#      with `-p 1883` and no `--cafile` / `--cert` / `--key` arguments
#      and no `-c <conf>` (so the binary uses its bind-all default).
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

is_mosquitto_file() {
  local s="$1"
  printf '%s\n' "$s" | grep -Eiq '(^|[^[:alnum:]_-])(listener[[:space:]]+[0-9]+|mosquitto\b|allow_anonymous\b|bind_address\b|persistence_location\b)'
}

is_loopback_addr() {
  case "$1" in
    127.0.0.1|::1|localhost|0:0:0:0:0:0:0:1) return 0 ;;
    *) return 1 ;;
  esac
}

# Split file into per-listener blocks and check each. A "block" begins at a
# `listener` line (or `port` at file top) and runs until the next `listener`
# line. We walk the stripped content and accumulate.
analyze_blocks() {
  local content="$1"
  # Use awk to emit one logical block per record, separated by NUL bytes.
  awk '
    BEGIN { block=""; have=0 }
    /^[[:space:]]*listener[[:space:]]+[0-9]+/ {
      if (have) { printf "%s%c", block, 0 }
      block=$0 "\n"; have=1; next
    }
    {
      if (!have) { block = block $0 "\n" } else { block = block $0 "\n" }
    }
    END { if (have || length(block) > 0) printf "%s%c", block, 0 }
  ' <<<"$content"
}

block_has_tls() {
  printf '%s\n' "$1" | grep -Eiq '^[[:space:]]*(cafile|certfile|keyfile|capath)[[:space:]]+[^[:space:]]+'
}

block_listener_addr() {
  # Echo the address (4th token if present) or empty if listener has no addr.
  printf '%s\n' "$1" | grep -Eo '^[[:space:]]*listener[[:space:]]+[0-9]+([[:space:]]+[^[:space:]]+)?' \
    | head -n1 | awk '{print $3}'
}

block_is_listener() {
  printf '%s\n' "$1" | grep -Eiq '^[[:space:]]*listener[[:space:]]+[0-9]+'
}

is_bad() {
  local f="$1"
  local stripped
  stripped="$(strip_comments "$f")"

  is_mosquitto_file "$stripped" || return 1

  # Rule 4: invocation-style mosquitto on cleartext port without TLS flags
  # and without a -c config file pointer (so we can't claim the conf saves it).
  if printf '%s\n' "$stripped" | grep -Eiq '(^|[[:space:]/"])mosquitto\b'; then
    local normalized
    normalized="$(printf '%s\n' "$stripped" | tr -d '",[]')"
    if printf '%s\n' "$normalized" | grep -Eiq '(^|[[:space:]])-p[[:space:]]+1883\b'; then
      if ! printf '%s\n' "$normalized" | grep -Eiq '(--cafile|--cert|--key|--capath|--tls-version)\b' \
         && ! printf '%s\n' "$normalized" | grep -Eiq '(^|[[:space:]])-c[[:space:]]+[^[:space:]]+'; then
        return 0
      fi
    fi
  fi

  # Rule 3: legacy top-level `port 1883` with no bind_address (or non-loopback)
  # AND no top-level TLS keys.
  if printf '%s\n' "$stripped" | grep -Eiq '^[[:space:]]*port[[:space:]]+1883\b' \
     && ! printf '%s\n' "$stripped" | grep -Eiq '^[[:space:]]*listener[[:space:]]+'; then
    local bind_line ba
    bind_line="$(printf '%s\n' "$stripped" | grep -E '^[[:space:]]*bind_address[[:space:]]+' | head -n1 || true)"
    ba="$(printf '%s\n' "$bind_line" | awk '{print $2}')"
    if [ -z "$ba" ] || ! is_loopback_addr "$ba"; then
      if ! block_has_tls "$stripped"; then
        return 0
      fi
    fi
  fi

  # Rule 1 / 2: walk listener blocks.
  local block addr
  while IFS= read -r -d '' block; do
    block_is_listener "$block" || continue
    addr="$(block_listener_addr "$block")"
    if [ -z "$addr" ]; then
      # No address: binds to all interfaces by default.
      if ! block_has_tls "$block"; then
        return 0
      fi
    else
      if ! is_loopback_addr "$addr" && ! block_has_tls "$block"; then
        return 0
      fi
    fi
  done < <(analyze_blocks "$stripped")

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
