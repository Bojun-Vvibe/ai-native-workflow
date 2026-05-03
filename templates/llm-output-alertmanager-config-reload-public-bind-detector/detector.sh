#!/usr/bin/env bash
# detector.sh — flag Alertmanager configs that expose /-/reload and /-/quit
# on a non-loopback listener with no auth fronting.
# Usage: detector.sh <file> [<file>...]
# Output: one FLAG line per finding. Always exits 0.

set -u

flag() {
  printf 'FLAG %s %s:%s %s\n' "$1" "$2" "$3" "$4"
}

scan_file() {
  local f="$1"
  [ -r "$f" ] || return 0

  # Signal 1: alertmanager binary/ExecStart with --web.listen-address bound publicly
  if grep -nE '(^|[[:space:]/])alertmanager([[:space:]]|$)' "$f" >/dev/null 2>&1 \
     || grep -nE 'ExecStart=.*alertmanager' "$f" >/dev/null 2>&1; then
    grep -nE -- '--web\.listen-address[ =]+["'"'"']?(0\.0\.0\.0|\[::\]|[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+):' "$f" 2>/dev/null \
      | grep -vE '127\.|localhost|\[::1\]' \
      | while IFS=: read -r ln rest; do
          flag S1 "$f" "$ln" "$rest"
        done
  fi

  # Signal 2: docker/k8s args containing --web.listen-address=0.0.0.0
  grep -nE -- '--web\.listen-address=(0\.0\.0\.0|\[::\]):[0-9]+' "$f" 2>/dev/null \
    | while IFS=: read -r ln rest; do
        flag S2 "$f" "$ln" "$rest"
      done

  # Signal 3: --web.external-url with non-loopback host AND no --web.route-prefix
  if grep -nE -- '--web\.external-url[ =]+["'"'"']?https?://' "$f" >/dev/null 2>&1; then
    if ! grep -E -- '--web\.route-prefix' "$f" >/dev/null 2>&1; then
      grep -nE -- '--web\.external-url[ =]+["'"'"']?https?://' "$f" 2>/dev/null \
        | grep -vE '://(localhost|127\.[0-9.]+|\[::1\]|[a-zA-Z0-9_.-]+\.internal)(:|/|$)' \
        | while IFS=: read -r ln rest; do
            flag S3 "$f" "$ln" "$rest"
          done
    fi
  fi

  # Signal 4: Helm values with LoadBalancer/NodePort under alertmanager.service.type
  awk '
    /^[[:space:]]*alertmanager[[:space:]]*:/ { in_am=1; next }
    in_am && /^[[:space:]]*service[[:space:]]*:/ { in_svc=1; next }
    in_svc && /^[[:space:]]*type[[:space:]]*:[[:space:]]*(LoadBalancer|NodePort)([[:space:]]|$)/ {
      printf "%d:%s\n", NR, $0
    }
    /^[^ ]/ && !/^[[:space:]]*alertmanager[[:space:]]*:/ { in_am=0; in_svc=0 }
  ' "$f" 2>/dev/null \
    | while IFS=: read -r ln rest; do
        flag S4 "$f" "$ln" "$rest"
      done
}

for f in "$@"; do
  scan_file "$f"
done
exit 0
