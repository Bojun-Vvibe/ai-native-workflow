#!/usr/bin/env bash
# detect.sh — flag Redis Sentinel configurations that LLMs commonly emit
# with no authentication, leaving the failover quorum unprotected.
#
# Sentinel is a separate daemon (default port 26379) that controls master
# promotion. If it has no auth and is reachable, an attacker can:
#   - call SENTINEL FAILOVER to forcibly demote the master
#   - call SENTINEL SET to change configuration / scripts
#   - read full topology with SENTINEL MASTERS / SLAVES
# It also needs to know the data-plane password to reach a protected master,
# via `sentinel auth-pass <name> <password>`. LLMs that "just get it
# working" routinely emit configs with all of these missing.
#
# Bad patterns we flag:
#   1. A `sentinel.conf` (port 26379 / `sentinel monitor` directive) that
#      has neither `requirepass` nor `sentinel sentinel-pass` set, AND
#      binds to a non-loopback address (or has no `bind` line, which on
#      modern Sentinel still listens on all interfaces unless
#      protected-mode catches it).
#   2. A `sentinel monitor <name> <host> <port> <quorum>` line where the
#      same file never declares `sentinel auth-pass <name> ...` for that
#      master name — Sentinel cannot authenticate to the data plane and
#      will mis-report the master as down.
#   3. `protected-mode no` together with a `sentinel monitor` directive
#      and no `requirepass` — explicit opt-out of the safety net.
#   4. Docker/compose `command:` or Dockerfile `CMD` running
#      `redis-sentinel` (or `redis-server --sentinel`) with `--bind 0.0.0.0`
#      or `--protected-mode no` and no `--requirepass` flag.
#
# Exit 0 iff every bad sample is flagged AND zero good samples are flagged.
set -u

bad_hits=0; bad_total=0; good_hits=0; good_total=0

# Strip shell-style `#` comments before matching. Sentinel/Redis configs
# use `#` for comments; directives are bare words at the start of a line.
strip_comments() {
  sed -E -e 's/[[:space:]]+#.*$//' -e 's/^[[:space:]]*#.*$//' "$1"
}

is_sentinel_file() {
  local s="$1"
  # Heuristic: any of these strongly indicate a Sentinel config or invocation.
  printf '%s\n' "$s" | grep -Eiq '(^|[^[:alnum:]_-])(sentinel[[:space:]]+monitor\b|redis-sentinel\b|--sentinel\b|port[[:space:]]+26379\b)'
}

has_requirepass() {
  printf '%s\n' "$1" | grep -Eiq '^[[:space:]]*requirepass[[:space:]]+[^[:space:]]+' \
   || printf '%s\n' "$1" | grep -Eiq '(^|[[:space:]])--requirepass[[:space:]]+[^[:space:]]+'
}

has_sentinel_auth_pass() {
  # sentinel auth-pass <master-name> <password>
  printf '%s\n' "$1" | grep -Eiq '^[[:space:]]*sentinel[[:space:]]+auth-pass[[:space:]]+[^[:space:]]+[[:space:]]+[^[:space:]]+'
}

binds_non_loopback() {
  local s="$1"
  # Explicit non-loopback bind, OR explicit bind to 0.0.0.0 / ::, OR no
  # bind directive at all in a file that is clearly a sentinel.conf.
  if printf '%s\n' "$s" | grep -Eiq '^[[:space:]]*bind[[:space:]]+([^[:space:]]+[[:space:]]+)*0\.0\.0\.0\b'; then
    return 0
  fi
  if printf '%s\n' "$s" | grep -Eiq '(^|[[:space:]])--bind[[:space:]]+([^[:space:]]+[[:space:]]+)*0\.0\.0\.0\b'; then
    return 0
  fi
  if printf '%s\n' "$s" | grep -Eiq '^[[:space:]]*bind[[:space:]]+([^[:space:]]+[[:space:]]+)*::[[:space:]]*$'; then
    return 0
  fi
  if ! printf '%s\n' "$s" | grep -Eiq '^[[:space:]]*bind[[:space:]]+'; then
    # No bind line at all: treat as non-loopback (Sentinel default behavior).
    return 0
  fi
  return 1
}

protected_mode_no() {
  printf '%s\n' "$1" | grep -Eiq '^[[:space:]]*protected-mode[[:space:]]+no\b' \
   || printf '%s\n' "$1" | grep -Eiq '(^|[[:space:]])--protected-mode[[:space:]]+no\b'
}

monitor_master_name() {
  # Echo the first master name appearing on a `sentinel monitor` line.
  printf '%s\n' "$1" \
    | grep -Eo '^[[:space:]]*sentinel[[:space:]]+monitor[[:space:]]+[^[:space:]]+' \
    | head -n1 \
    | awk '{print $3}'
}

is_bad() {
  local f="$1"
  local stripped
  stripped="$(strip_comments "$f")"

  is_sentinel_file "$stripped" || return 1

  # Determine flavor: a sentinel.conf-style file (declares `sentinel monitor`
  # at column 0) vs an invocation file (Dockerfile CMD / compose command:).
  # Config-style and invocation-style get different rule sets — invocation
  # files do not require a `bind` line, so absence of `bind` is not a
  # finding for them.
  local is_config_file=1
  if printf '%s\n' "$stripped" | grep -Eiq '^[[:space:]]*sentinel[[:space:]]+monitor\b'; then
    is_config_file=0
  fi

  if [ "$is_config_file" = 0 ]; then
    # Rule 1: bound to non-loopback, no requirepass, no sentinel-pass.
    if binds_non_loopback "$stripped" \
       && ! has_requirepass "$stripped" \
       && ! grep -Eiq '^[[:space:]]*sentinel[[:space:]]+sentinel-pass[[:space:]]+' <<<"$stripped"; then
      return 0
    fi

    # Rule 2: monitor declared but no matching auth-pass for that master.
    local mname
    mname="$(monitor_master_name "$stripped")"
    if [ -n "$mname" ] && ! has_sentinel_auth_pass "$stripped"; then
      return 0
    fi

    # Rule 3: protected-mode no + sentinel monitor + no requirepass.
    if protected_mode_no "$stripped" \
       && ! has_requirepass "$stripped"; then
      return 0
    fi
  fi

  # Rule 4: command-line redis-sentinel / --sentinel with EXPLICIT
  # --bind 0.0.0.0 or --protected-mode no and no --requirepass.
  # Tolerate JSON-array CMD form by stripping `"`, `,` and `[` `]` first.
  if printf '%s\n' "$stripped" | grep -Eiq '(redis-sentinel|--sentinel)\b'; then
    local normalized
    normalized="$(printf '%s\n' "$stripped" | tr -d '",[]')"
    local explicit_open=1
    if printf '%s\n' "$normalized" | grep -Eiq '(^|[[:space:]])--bind[[:space:]]+([^[:space:]]+[[:space:]]+)*0\.0\.0\.0\b'; then
      explicit_open=0
    fi
    if printf '%s\n' "$normalized" | grep -Eiq '(^|[[:space:]])--protected-mode[[:space:]]+no\b'; then
      explicit_open=0
    fi
    if [ "$explicit_open" = 0 ] \
       && ! printf '%s\n' "$normalized" | grep -Eiq '(^|[[:space:]])--requirepass[[:space:]]+[^[:space:]]+'; then
      return 0
    fi
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
