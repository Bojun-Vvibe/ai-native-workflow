#!/usr/bin/env bash
# detector.sh — flag Redis ACL configs that leave a user "on nopass" with
# broad command/key wildcards (CWE-521 / CWE-287).
#
# Rules (any one fires => BAD):
#  R1: A user line is "on" + "nopass" AND has both a key wildcard (~*)
#      and a command wildcard (+@all OR allcommands).
#  R2: A redis-cli "ACL SETUSER ... on nopass ... ~* ... (+@all|allcommands)"
#      invocation appears (shell / Dockerfile bootstrap).
#
# Notes:
#  - Lines starting with '#' (comments) are skipped.
#  - "off" users are ignored (they cannot authenticate).
#  - A user with nopass but a SCOPED key pattern (e.g. ~probe:*) is NOT flagged.

set -u

is_bad() {
  local f="$1"

  # Strip comments per line; check user directives.
  # R1: standalone or inline "user <name> on ... nopass ..." in conf/acl files
  # We accept the full line and look for required tokens.
  while IFS= read -r line; do
    # drop leading whitespace + skip comments
    case "$line" in
      \#*|"") continue ;;
    esac
    # Match either "user <name> ..." (redis.conf inline) OR ACL file lines starting with "user "
    if [[ "$line" =~ ^[[:space:]]*user[[:space:]]+[^[:space:]]+[[:space:]] ]]; then
      # must contain " on " (active)
      if [[ ! " $line " == *" on "* ]]; then continue; fi
      # must NOT contain " off "
      if [[ " $line " == *" off "* ]]; then continue; fi
      # must contain nopass
      if [[ " $line " != *" nopass "* && "$line" != *" nopass" ]]; then continue; fi
      # must contain key wildcard ~*
      if [[ " $line " != *" ~* "* && "$line" != *" ~*" ]]; then continue; fi
      # must contain command wildcard
      if [[ " $line " == *" +@all "* || "$line" == *" +@all" || " $line " == *" allcommands "* || "$line" == *" allcommands" ]]; then
        return 0
      fi
    fi
  done < "$f"

  # R2: ACL SETUSER bootstrap with the same dangerous combo on one line
  if grep -Eq 'ACL[[:space:]]+SETUSER[[:space:]]+' "$f"; then
    while IFS= read -r line; do
      case "$line" in \#*|"") continue ;; esac
      if [[ "$line" == *"ACL SETUSER"* || "$line" == *"acl setuser"* ]]; then
        if [[ " $line " == *" on "* ]] && [[ " $line " != *" off "* ]] \
           && [[ " $line " == *" nopass "* || "$line" == *" nopass" ]] \
           && [[ " $line " == *" ~* "* || "$line" == *" ~*" ]] \
           && { [[ " $line " == *" +@all "* || "$line" == *" +@all" ]] || [[ " $line " == *" allcommands "* || "$line" == *" allcommands" ]]; }; then
          return 0
        fi
      fi
    done < "$f"
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
