#!/usr/bin/env bash
# detector.sh — flag MongoDB configs/launches that bind every interface
# without enabling authorization.
#
# Rules:
#  R1: mongod.conf YAML with bindIp 0.0.0.0 (or bindIpAll: true) AND either
#      security.authorization is "disabled" or no security.authorization line exists
#  R2: mongod CLI with --bind_ip 0.0.0.0 or --bind_ip_all and no --auth
#  R3: Dockerfile CMD/ENTRYPOINT running mongod with --bind_ip_all without --auth
#  R4: container manifest exposing 27017 on a non-loopback bind AND no
#      MONGO_INITDB_ROOT_USERNAME defined
#
# Exit 0 iff every bad sample matches and zero good samples match.
set -u

is_bad() {
  local f="$1"

  # R1: mongod.conf YAML — bindIp 0.0.0.0 / bindIpAll true without auth enabled
  local binds_all=0
  if grep -Eq '^[[:space:]]*bindIp[[:space:]]*:[[:space:]]*([\"'\'']?)0\.0\.0\.0\1[[:space:]]*$' "$f"; then
    binds_all=1
  fi
  if grep -Eq '^[[:space:]]*bindIpAll[[:space:]]*:[[:space:]]*true[[:space:]]*$' "$f"; then
    binds_all=1
  fi
  if [ "$binds_all" = 1 ]; then
    if grep -Eq '^[[:space:]]*authorization[[:space:]]*:[[:space:]]*disabled[[:space:]]*$' "$f"; then
      return 0
    fi
    if ! grep -Eq '^[[:space:]]*authorization[[:space:]]*:[[:space:]]*enabled[[:space:]]*$' "$f"; then
      # Only treat as YAML "no security block" form when this looks like a YAML config
      case "$f" in
        *.yaml|*.yml|*.conf) return 0 ;;
      esac
    fi
  fi

  # R2 / R3: CLI / Dockerfile mongod invocation with bind-all and no --auth
  if grep -Eq 'mongod([[:space:]]|.*[[:space:]])(--bind_ip_all|--bind_ip[[:space:]]+0\.0\.0\.0)' "$f"; then
    if ! grep -Eq 'mongod.*--auth([[:space:]]|$)' "$f"; then
      return 0
    fi
  fi

  # R4: container manifest exposes 27017 on non-loopback bind without root user
  if grep -Eq '("27017"|27017:27017|containerPort:[[:space:]]*27017|EXPOSE[[:space:]]+27017)' "$f"; then
    if ! grep -Eq '127\.0\.0\.1:27017' "$f"; then
      if ! grep -Eq 'MONGO_INITDB_ROOT_USERNAME[[:space:]]*[:=]' "$f"; then
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
