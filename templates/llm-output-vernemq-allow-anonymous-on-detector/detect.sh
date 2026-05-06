#!/usr/bin/env bash
# detect.sh — flag VerneMQ `vernemq.conf` snippets that LLMs
# commonly emit with `allow_anonymous = on`. VerneMQ is an MQTT
# broker; with `allow_anonymous = on` any TCP client that can
# reach the listener can publish/subscribe to any topic without
# presenting a username + password and without going through the
# auth chain. On the default listener (1883/tcp, 0.0.0.0) this is
# an open MQTT broker on the public internet.
#
# Bad patterns (any one is sufficient):
#   1. `allow_anonymous = on`    (the canonical bad form).
#   2. `allow_anonymous = true`  (LLMs emit YAML/JSON-shaped
#                                 booleans even though VerneMQ
#                                 uses on/off).
#   3. `allow_anonymous = yes`   (same).
#   4. `allow_anonymous = 1`     (same).
#
# Good patterns are the inverse: `allow_anonymous = off` (or
# `false`/`no`/`0`) on every uncommented occurrence, OR no
# `allow_anonymous` line at all in a file that fingerprints as a
# VerneMQ config (default is `off`).
#
# We strip `#` comments. We only scan files whose content
# fingerprints as VerneMQ config — at least one of:
#   - `listener.tcp.default = ...`
#   - `listener.ssl.default = ...`
#   - `listener.ws.default = ...`
#   - `plugins.vmq_acl = ...`
#   - `vmq_acl.acl_file = ...`
#   - `plugins.vmq_passwd = ...`
#   - `vmq_passwd.password_file = ...`
#   - `allow_anonymous = ...`
#
# Bash 3.2+ / awk / coreutils only. No network calls.

set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

is_vernemq_conf() {
  local s="$1"
  printf '%s\n' "$s" \
    | grep -Eq '^[[:space:]]*(listener\.(tcp|ssl|ws|wss|http|https)\.[A-Za-z0-9_.-]+|plugins\.vmq_(acl|passwd|diversity|bridge|webhooks)|vmq_(acl|passwd)\.[A-Za-z_]+|allow_anonymous|allow_register_during_netsplit|allow_publish_during_netsplit|allow_subscribe_during_netsplit|allow_unsubscribe_during_netsplit|max_client_id_size|retry_interval|max_inflight_messages|max_message_size|max_online_messages|max_offline_messages|persistent_client_expiration|message_size_limit|upgrade_outgoing_qos)[[:space:]]*='
}

allow_anon_lines() {
  printf '%s\n' "$1" \
    | grep -E '^[[:space:]]*allow_anonymous[[:space:]]*='
}

allow_anon_value() {
  printf '%s' "$1" \
    | sed -E 's/^[[:space:]]*allow_anonymous[[:space:]]*=[[:space:]]*//' \
    | sed -E 's/[[:space:]]+$//' \
    | tr 'A-Z' 'a-z'
}

is_truthy() {
  case "$1" in
    "on"|"true"|"yes"|"1") return 0 ;;
  esac
  return 1
}

is_bad() {
  local f="$1"
  local s
  s="$(strip_comments "$f")"
  is_vernemq_conf "$s" || return 1

  local lines line val any_bad=1
  lines="$(allow_anon_lines "$s")"
  if [ -z "$lines" ]; then
    return 1
  fi
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    val="$(allow_anon_value "$line")"
    if is_truthy "$val"; then
      any_bad=0
    fi
  done <<EOF
$lines
EOF
  return $any_bad
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
