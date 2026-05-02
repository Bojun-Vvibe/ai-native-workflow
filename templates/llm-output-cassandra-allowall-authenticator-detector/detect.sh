#!/usr/bin/env bash
# detect.sh — flag Cassandra cassandra.yaml snippets (or rendered docs) that:
#   1. set `authenticator: AllowAllAuthenticator` (anyone can connect, no creds)
#   2. set `authorizer: AllowAllAuthorizer` (everyone has every permission)
#   3. set `role_manager: AllowAllRoleManager` (no role enforcement)
#   4. enable client_encryption with `internode_encryption: none` AND no auth
#      (network-exposed cluster with neither auth nor encryption)
#
# Exit 0 iff bad/bad/* are all flagged AND good/* are all clean.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

is_bad() {
  local f="$1"
  # Rule 1: AllowAllAuthenticator (uncommented)
  if grep -Eq '^[[:space:]]*authenticator:[[:space:]]*AllowAllAuthenticator' "$f"; then return 0; fi
  # Rule 2: AllowAllAuthorizer (uncommented)
  if grep -Eq '^[[:space:]]*authorizer:[[:space:]]*AllowAllAuthorizer' "$f"; then return 0; fi
  # Rule 3: AllowAllRoleManager (uncommented; the secure default is CassandraRoleManager)
  if grep -Eq '^[[:space:]]*role_manager:[[:space:]]*AllowAllRoleManager' "$f"; then return 0; fi
  # Rule 4: internode_encryption: none paired with an AllowAll* setting anywhere in the file
  if grep -Eq '^[[:space:]]*internode_encryption:[[:space:]]*none' "$f" \
     && grep -Eq 'AllowAll(Authenticator|Authorizer|RoleManager)' "$f"; then
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
