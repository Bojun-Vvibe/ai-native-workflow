#!/usr/bin/env bash
# detector.sh — flag etcd configs that disable or omit client auth.
# Usage: detector.sh <file> [<file>...]
# Output: one "FLAG <signal-id> <file>:<lineno> <text>" line per finding.
# Exit:   always 0; callers count FLAG lines.

set -u

flag() {
  # $1 signal-id, $2 file, $3 lineno, $4 text
  printf 'FLAG %s %s:%s %s\n' "$1" "$2" "$3" "$4"
}

scan_file() {
  local f="$1"
  [ -r "$f" ] || return 0

  # Signal 1: non-loopback client URL over plaintext http
  # Matches both --listen-client-urls=http://0.0.0.0:... and YAML
  # listen-client-urls: http://0.0.0.0:...
  grep -nE '(listen-client-urls|--listen-client-urls)[ =:]+["'"'"']?http://(0\.0\.0\.0|\[::\]|[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)' "$f" 2>/dev/null \
    | grep -vE 'http://(127\.|localhost|\[::1\])' \
    | while IFS=: read -r ln rest; do
        flag S1 "$f" "$ln" "$rest"
      done

  # Signal 2: explicit client-cert-auth=false (CLI or YAML)
  grep -nE '(--client-cert-auth[ =]+false|client-cert-auth:[ ]*false)' "$f" 2>/dev/null \
    | while IFS=: read -r ln rest; do
        flag S2 "$f" "$ln" "$rest"
      done

  # Signal 3: --auth-token=simple paired with non-loopback bind in same file
  if grep -qE '(--auth-token[ =]+simple|auth-token:[ ]*simple)' "$f" 2>/dev/null; then
    if grep -qE '(listen-client-urls|--listen-client-urls)[ =:]+["'"'"']?https?://(0\.0\.0\.0|\[::\]|[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)' "$f" \
       && ! grep -qE 'https?://(127\.|localhost|\[::1\])' "$f"; then
      ln=$(grep -nE '(--auth-token[ =]+simple|auth-token:[ ]*simple)' "$f" | head -1 | cut -d: -f1)
      txt=$(grep -nE '(--auth-token[ =]+simple|auth-token:[ ]*simple)' "$f" | head -1 | cut -d: -f2-)
      flag S3 "$f" "$ln" "$txt"
    fi
  fi

  # Signal 4: non-loopback client URL but no client-cert-auth flag at all
  if grep -E '(listen-client-urls|--listen-client-urls)[ =:]+["'"'"']?https?://(0\.0\.0\.0|\[::\]|[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)' "$f" 2>/dev/null \
       | grep -vqE 'https?://(127\.|localhost|\[::1\])'; then
    if ! grep -qE '(client-cert-auth|--client-cert-auth)' "$f" 2>/dev/null; then
      ln=$(grep -nE '(listen-client-urls|--listen-client-urls)' "$f" | head -1 | cut -d: -f1)
      txt=$(grep -nE '(listen-client-urls|--listen-client-urls)' "$f" | head -1 | cut -d: -f2-)
      flag S4 "$f" "$ln" "$txt"
    fi
  fi
}

for f in "$@"; do
  scan_file "$f"
done
exit 0
