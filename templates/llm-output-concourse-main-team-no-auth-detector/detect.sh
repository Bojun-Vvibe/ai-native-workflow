#!/usr/bin/env bash
# detect.sh — flag Concourse `web` configurations that LLMs routinely
# emit with the `main` team left unauthenticated. The `main` team is
# the bootstrap admin team and owns every other team and pipeline; if
# its auth is wrong, the cluster is open.
#
# Bad patterns we flag (any one is sufficient, on a snippet that
# references `concourse web` or sets CONCOURSE_* env vars):
#
#   1. References a main-team local user (CLI `--main-team-local-user=X`
#      or env `CONCOURSE_MAIN_TEAM_LOCAL_USER=X`) but does NOT define
#      that user via `--add-local-user=X:...` or
#      `CONCOURSE_ADD_LOCAL_USER` (which takes a comma-separated list
#      of `name:password`).
#
#   2. Defines a local user via --add-local-user / CONCOURSE_ADD_LOCAL_USER
#      whose password is empty or a known placeholder
#      (admin, password, concourse, changeme, please_change_me, test,
#      secret, 123456).
#
#   3. Sets `--enable-noauth-main-team` or
#      `CONCOURSE_ENABLE_NOAUTH_MAIN_TEAM=true` explicitly.
#
# A snippet that only mentions `concourse worker` is ignored.
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

strip_comments() {
  # Shell-style `#` comments at start of line or after whitespace.
  # YAML uses the same convention. We don't strip mid-string `#`.
  sed -E -e 's/^[[:space:]]*#.*$//' -e 's/[[:space:]]+#.*$//' "$1"
}

mentions_concourse_web() {
  local s="$1"
  # Direct CLI invocation, OR any CONCOURSE_* env var (which only the
  # web node reads for these keys), OR an image reference followed by
  # `web` as the command.
  printf '%s\n' "$s" | grep -Eiq '(^|[[:space:]/"=])concourse[[:space:]]+web\b' && return 0
  printf '%s\n' "$s" | grep -Eq 'CONCOURSE_(MAIN_TEAM|ADD_LOCAL_USER|ENABLE_NOAUTH_MAIN_TEAM)' && return 0
  printf '%s\n' "$s" | grep -Eiq '(^|[[:space:]])--main-team-local-user(=|[[:space:]])' && return 0
  printf '%s\n' "$s" | grep -Eiq '(^|[[:space:]])--add-local-user(=|[[:space:]])' && return 0
  printf '%s\n' "$s" | grep -Eiq '(^|[[:space:]])--enable-noauth-main-team\b' && return 0
  return 1
}

is_placeholder_pw() {
  local v
  v="$(printf '%s' "$1" | tr 'A-Z' 'a-z')"
  case "$v" in
    ""|admin|password|concourse|changeme|please_change_me|please-change-me|test|secret|123456|qwerty|root) return 0 ;;
    *) return 1 ;;
  esac
}

# Collect every "name:password" pair declared via --add-local-user OR
# CONCOURSE_ADD_LOCAL_USER (comma-separated list). Emit one pair per line.
collect_local_users() {
  local s="$1"
  # CLI flag form: --add-local-user=foo:bar, --add-local-user foo:bar,
  # or quoted --add-local-user "foo:bar" / --add-local-user='foo:bar'.
  # Normalize by stripping the matched quotes from the captured value.
  printf '%s\n' "$s" \
    | grep -Eo -- '--add-local-user[[:space:]=]+("[^"]*"|'\''[^'\'']*'\''|[^[:space:]`]+)' \
    | sed -E 's/^--add-local-user[[:space:]=]+//' \
    | sed -E 's/^"//; s/"$//; s/^'\''//; s/'\''$//' \
    | tr ',' '\n'
  # Env form: CONCOURSE_ADD_LOCAL_USER=foo:bar,baz:qux  (with optional quotes)
  printf '%s\n' "$s" \
    | grep -E 'CONCOURSE_ADD_LOCAL_USER[[:space:]]*[=:][[:space:]]*' \
    | sed -E 's/.*CONCOURSE_ADD_LOCAL_USER[[:space:]]*[=:][[:space:]]*//' \
    | sed -E 's/^"//; s/"$//; s/^'\''//; s/'\''$//' \
    | sed -E 's/[[:space:]]+$//' \
    | tr ',' '\n'
}

# Collect every main-team-local-user *username* declared.
collect_main_team_users() {
  local s="$1"
  printf '%s\n' "$s" \
    | grep -Eo -- '--main-team-local-user[[:space:]=]+("[^"]*"|'\''[^'\'']*'\''|[^[:space:]`]+)' \
    | sed -E 's/^--main-team-local-user[[:space:]=]+//' \
    | sed -E 's/^"//; s/"$//; s/^'\''//; s/'\''$//'
  printf '%s\n' "$s" \
    | grep -E 'CONCOURSE_MAIN_TEAM_LOCAL_USER[[:space:]]*[=:][[:space:]]*' \
    | sed -E 's/.*CONCOURSE_MAIN_TEAM_LOCAL_USER[[:space:]]*[=:][[:space:]]*//' \
    | sed -E 's/^"//; s/"$//; s/^'\''//; s/'\''$//' \
    | sed -E 's/[[:space:]]+.*$//'
}

has_enable_noauth() {
  local s="$1"
  printf '%s\n' "$s" | grep -Eiq '(^|[[:space:]])--enable-noauth-main-team\b' && return 0
  printf '%s\n' "$s" \
    | grep -Eiq 'CONCOURSE_ENABLE_NOAUTH_MAIN_TEAM[[:space:]]*[=:][[:space:]]*("?)(1|true|yes|on)\1' \
    && return 0
  return 1
}

is_bad_file() {
  local f="$1"
  local stripped
  stripped="$(strip_comments "$f")"

  mentions_concourse_web "$stripped" || return 1

  # Pattern 3: explicit no-auth toggle
  if has_enable_noauth "$stripped"; then return 0; fi

  # Pattern 2: any defined local-user has placeholder/empty password
  while IFS= read -r pair; do
    [ -z "$pair" ] && continue
    # pair is name:password (password may itself contain colons, but
    # Concourse splits on the first one; mirror that)
    local name pw
    name="${pair%%:*}"
    pw="${pair#*:}"
    [ "$name" = "$pair" ] && pw=""   # no colon at all => empty pw
    if is_placeholder_pw "$pw"; then return 0; fi
  done < <(collect_local_users "$stripped")

  # Pattern 1: main-team-local-user references a username that is
  # never defined via --add-local-user / CONCOURSE_ADD_LOCAL_USER.
  local declared
  declared="$(collect_local_users "$stripped" | awk -F: 'NF{print $1}' | sort -u)"
  while IFS= read -r u; do
    [ -z "$u" ] && continue
    if ! printf '%s\n' "$declared" | grep -Fxq "$u"; then
      return 0
    fi
  done < <(collect_main_team_users "$stripped")

  return 1
}

for f in "$@"; do
  case "$f" in
    *samples/bad/*) bad_total=$((bad_total+1)) ;;
    *samples/good/*) good_total=$((good_total+1)) ;;
  esac
  if is_bad_file "$f"; then
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
