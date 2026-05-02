#!/usr/bin/env bash
# detect.sh — flag ZooKeeper config / ACL snippets that disable authentication:
#   1. zoo.cfg with `skipACL=yes` (or `skipACL = yes`)
#   2. zoo.cfg without any `authProvider.*=` line AND without `requireClientAuthScheme=`
#      AND with a `clientPort` that is reachable (i.e. no `clientPortAddress=127.0.0.1`)
#   3. setAcl-style commands granting `world:anyone:cdrwa`
#   4. zoo.cfg containing `4lw.commands.whitelist=*` paired with no auth (admin exposure)
#
# Exit 0 iff no bad files match.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

is_bad() {
  local f="$1"
  # Rule 1: skipACL=yes
  if grep -Eiq '^[[:space:]]*skipACL[[:space:]]*=[[:space:]]*yes' "$f"; then return 0; fi
  # Rule 3: world:anyone:cdrwa ACL
  if grep -Eq 'world:anyone:[cdrwa]*[a]' "$f"; then return 0; fi
  # Rule 4: 4lw whitelist=* with no auth provider
  if grep -Eq '^[[:space:]]*4lw\.commands\.whitelist[[:space:]]*=[[:space:]]*\*' "$f" \
     && ! grep -Eq '^[[:space:]]*authProvider\.' "$f"; then
    return 0
  fi
  # Rule 2: clientPort set, no authProvider, no requireClientAuthScheme,
  #         and not bound to loopback
  if grep -Eq '^[[:space:]]*clientPort[[:space:]]*=' "$f" \
     && ! grep -Eq '^[[:space:]]*authProvider\.' "$f" \
     && ! grep -Eq '^[[:space:]]*requireClientAuthScheme[[:space:]]*=' "$f" \
     && ! grep -Eq '^[[:space:]]*clientPortAddress[[:space:]]*=[[:space:]]*(127\.0\.0\.1|localhost|::1)' "$f"; then
    return 0
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
