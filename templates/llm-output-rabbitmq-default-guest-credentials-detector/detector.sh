#!/usr/bin/env bash
# detector.sh — flag RabbitMQ configs/launches that ship the default guest/guest
# superuser reachable from the network.
#
# Rules:
#  R1: rabbitmq.conf with `loopback_users = none` or `loopback_users.guest = false`
#  R2: rabbitmq.config (Erlang) with `{loopback_users, []}`
#  R3: rabbitmqctl invocation that (re)creates `guest` with password `guest`
#  R4: container manifest exposing 5672/15672 on a non-loopback bind AND
#      either no RABBITMQ_DEFAULT_USER override, or RABBITMQ_DEFAULT_PASS=guest
#
# Exit 0 iff every bad sample matches and zero good samples match.
set -u

is_bad() {
  local f="$1"

  # R1: loopback_users override that re-enables guest over the network
  if grep -Eq '^[[:space:]]*loopback_users[[:space:]]*=[[:space:]]*none[[:space:]]*$' "$f"; then
    return 0
  fi
  if grep -Eq '^[[:space:]]*loopback_users\.guest[[:space:]]*=[[:space:]]*false[[:space:]]*$' "$f"; then
    return 0
  fi

  # R2: Erlang term form with empty loopback list
  if grep -Eq '\{[[:space:]]*loopback_users[[:space:]]*,[[:space:]]*\[[[:space:]]*\][[:space:]]*\}' "$f"; then
    return 0
  fi

  # R3: rabbitmqctl creating/resetting guest with literal `guest` password
  if grep -Eq 'rabbitmqctl[[:space:]]+(add_user|change_password)[[:space:]]+guest[[:space:]]+guest([[:space:]]|$)' "$f"; then
    return 0
  fi

  # R4: container manifest exposes AMQP/management on non-loopback without
  # overriding the default guest password to something non-`guest`
  if grep -Eq '("(5672|15672)"|(5672|15672):(5672|15672)|containerPort:[[:space:]]*(5672|15672)|EXPOSE[[:space:]]+(5672|15672))' "$f"; then
    if ! grep -Eq '127\.0\.0\.1:(5672|15672)' "$f"; then
      # explicit bad: default pass left as guest
      if grep -Eq 'RABBITMQ_DEFAULT_PASS[[:space:]]*[:=][[:space:]]*"?guest"?([[:space:]]|$)' "$f"; then
        return 0
      fi
      # implicit bad: no override at all of the default user
      if ! grep -Eq 'RABBITMQ_DEFAULT_USER[[:space:]]*[:=]' "$f"; then
        return 0
      fi
    fi
  fi

  return 1
}

bad_hits=0; bad_total=0; good_hits=0; good_total=0
for f in "$@"; do
  case "$f" in
    *examples/bad/*)  bad_total=$((bad_total+1)) ;;
    *examples/good/*) good_total=$((good_total+1)) ;;
  esac
  if is_bad "$f"; then
    echo "BAD  $f"
    case "$f" in
      *examples/bad/*)  bad_hits=$((bad_hits+1)) ;;
      *examples/good/*) good_hits=$((good_hits+1)) ;;
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
