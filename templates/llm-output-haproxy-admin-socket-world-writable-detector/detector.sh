#!/usr/bin/env bash
# detector.sh — flag HAProxy configs that expose the admin/runtime socket
# in a way that lets unprivileged local (or remote) callers issue admin
# commands. The HAProxy stats socket, when reachable with `level admin`
# and weak permissions, allows `disable server`, `set server ... agent`,
# `add map`, and other state-changing commands.
# Usage: detector.sh <file> [<file>...]
# Output: one FLAG line per finding. Always exits 0.

set -u

flag() {
  printf 'FLAG %s %s:%s %s\n' "$1" "$2" "$3" "$4"
}

scan_file() {
  local f="$1"
  [ -r "$f" ] || return 0

  # Signal 1: stats socket bound to a TCP address (ipv4:port or *:port)
  # with level admin and no `accept-netmask`/`accept-proxy` restriction.
  grep -nE '^[[:space:]]*stats[[:space:]]+socket[[:space:]]+(ipv4@|ipv6@|\*:|0\.0\.0\.0:|\[::\]:)[^[:space:]]+([[:space:]].*)?level[[:space:]]+admin' "$f" 2>/dev/null \
    | while IFS=: read -r ln rest; do
        flag S1 "$f" "$ln" "$rest"
      done

  # Signal 2: stats socket on a unix path with mode 666 / 777 / world-rw,
  # explicit or via "user nobody" + admin level + permissive mode.
  grep -nE '^[[:space:]]*stats[[:space:]]+socket[[:space:]]+(/[^[:space:]]+|unix@/[^[:space:]]+)[[:space:]]+.*mode[[:space:]]+(0?666|0?777)' "$f" 2>/dev/null \
    | while IFS=: read -r ln rest; do
        flag S2 "$f" "$ln" "$rest"
      done

  # Signal 3: stats socket with level admin and NO `mode` clause AND NO
  # `user`/`group` clause — relies on default mode (0600 if root, but
  # often misread as safe; plus default user is whoever runs haproxy,
  # which under docker is often root with a host-mounted socket).
  # We flag the *combination* of "level admin" + bare unix path + no
  # mode + no user/group restriction.
  while IFS= read -r line; do
    ln="${line%%:*}"
    rest="${line#*:}"
    case "$rest" in
      *"level admin"*)
        if ! printf '%s' "$rest" | grep -qE 'mode[[:space:]]+0?[0-7]{3,4}'; then
          if ! printf '%s' "$rest" | grep -qE '(user|group|uid|gid)[[:space:]]+[A-Za-z0-9_-]+'; then
            flag S3 "$f" "$ln" "$rest"
          fi
        fi
        ;;
    esac
  done < <(grep -nE '^[[:space:]]*stats[[:space:]]+socket[[:space:]]+(/[^[:space:]]+|unix@/[^[:space:]]+)' "$f" 2>/dev/null)

  # Signal 4: explicit `expose-fd listeners` or `level admin` granted to a
  # TCP socket without an `accept-proxy` / source ACL — i.e., remote admin
  # over plain TCP.
  grep -nE '^[[:space:]]*stats[[:space:]]+socket[[:space:]]+(ipv4@|ipv6@)[^[:space:]]+([[:space:]].*)?expose-fd[[:space:]]+listeners' "$f" 2>/dev/null \
    | while IFS=: read -r ln rest; do
        flag S4 "$f" "$ln" "$rest"
      done
}

for f in "$@"; do
  scan_file "$f"
done
exit 0
