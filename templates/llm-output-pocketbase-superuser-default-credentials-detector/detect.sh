#!/usr/bin/env bash
# llm-output-pocketbase-superuser-default-credentials-detector
#
# Flags PocketBase deployments where the initial superuser is created
# (via `pocketbase superuser create|upsert`, `pocketbase admin create`,
# the legacy --encryptionEnv bootstrap, or a programmatic
# `app.OnBootstrap` hook) using a literal placeholder email/password
# pair such as `admin@example.com` / `1234567890`, `test@test.com` /
# `password`, etc.
#
# Inspects shell scripts, Dockerfiles, docker-compose files, systemd
# units, Go bootstrap snippets, and Markdown install guides given a
# path to a file or a directory (recursive).
#
# Exit codes:
#   0   PASS  no defaulted superuser bootstrap observed
#   1   FAIL  at least one defaulted superuser bootstrap observed
#   2   usage error
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <file-or-dir>" >&2
  exit 2
fi

target="$1"
if [ ! -e "$target" ]; then
  echo "no such path: $target" >&2
  exit 2
fi

# Known-bad placeholder passwords shipped in upstream docs, blog posts,
# and "deploy PocketBase in 2 minutes" guides.
bad_passwords='
1234567890
12345678
password
password123
admin
admin123
changeme
changethis
default
secret
test1234
qwerty12
PocketBase
pocketbase
'

# Known-bad placeholder emails.
bad_emails='
admin@example.com
admin@example.org
admin@admin.com
admin@localhost
test@test.com
test@example.com
user@example.com
root@localhost
'

found=0

is_bad_password() {
  v="$1"
  [ -z "$v" ] && return 0
  # PocketBase requires >=10 chars; flag anything shorter.
  if [ "${#v}" -lt 10 ]; then
    return 0
  fi
  while IFS= read -r bad; do
    [ -z "$bad" ] && continue
    [ "$v" = "$bad" ] && return 0
  done <<EOF
$bad_passwords
EOF
  return 1
}

is_bad_email() {
  v="$1"
  [ -z "$v" ] && return 1
  while IFS= read -r bad; do
    [ -z "$bad" ] && continue
    [ "$v" = "$bad" ] && return 0
  done <<EOF
$bad_emails
EOF
  return 1
}

strip_quotes() {
  s="$1"
  s="${s%\"}"; s="${s#\"}"
  s="${s%\'}"; s="${s#\'}"
  printf '%s' "$s"
}

scan_one() {
  f="$1"
  # Look for any line that mentions a pocketbase superuser/admin bootstrap
  # command and capture the trailing two positional args (email, password).
  while IFS= read -r line; do
    case "$line" in
      \#*) continue ;;
    esac
    raw="$line"
    case "$raw" in
      *pocketbase*superuser*create*|*pocketbase*superuser*upsert*|\
      *pocketbase*admin*create*|*pocketbase*admin*upsert*|\
      *./pocketbase\ superuser*|*./pocketbase\ admin*)
        # Tokenise by whitespace; pull last two non-flag tokens.
        toks="$(printf '%s' "$raw" | tr '\t' ' ' | tr -s ' ')"
        # shellcheck disable=SC2086
        set -- $toks
        email=""; pw=""
        for t in "$@"; do
          case "$t" in
            -*|*=*) continue ;;
          esac
          # heuristic: an email contains '@'
          if printf '%s' "$t" | grep -q '@'; then
            email="$(strip_quotes "$t")"
          else
            pw="$(strip_quotes "$t")"
          fi
        done
        if [ -n "$email" ] || [ -n "$pw" ]; then
          bad_email_hit=0; bad_pw_hit=0
          if is_bad_email "$email"; then bad_email_hit=1; fi
          if is_bad_password "$pw"; then bad_pw_hit=1; fi
          if [ "$bad_email_hit" -eq 1 ] || [ "$bad_pw_hit" -eq 1 ]; then
            reason=""
            [ "$bad_email_hit" -eq 1 ] && reason="default email '$email'"
            if [ "$bad_pw_hit" -eq 1 ]; then
              if [ -n "$reason" ]; then reason="$reason + "; fi
              reason="${reason}weak/default password"
            fi
            echo "FAIL: $f: pocketbase superuser bootstrap with $reason -> $line"
            found=1
          fi
        fi
        ;;
      *SetPassword\(\"*\"\)*)
        # Programmatic bootstrap: any line of the form
        #   admin.SetPassword("password123")
        # in a Go bootstrap file. Pair-with-email correlation is
        # left to a stricter checker; a literal weak password in a
        # SetPassword call is already a finding on its own.
        pw_lit="$(printf '%s' "$raw" | sed -n 's/.*SetPassword(\"\([^\"]*\)\").*/\1/p')"
        if [ -n "$pw_lit" ] && is_bad_password "$pw_lit"; then
          echo "FAIL: $f: programmatic admin bootstrap with weak/default password '$pw_lit' -> $line"
          found=1
        fi
        ;;
    esac
  done < "$f"
}

if [ -d "$target" ]; then
  while IFS= read -r f; do
    case "$(basename "$f")" in
      *.sh|*.bash|Dockerfile|docker-compose*.yml|docker-compose*.yaml|\
      *.service|*.go|*.md|*.markdown|entrypoint*|bootstrap*|init*)
        [ -f "$f" ] && scan_one "$f"
        ;;
    esac
  done <<EOF
$(find "$target" -type f 2>/dev/null)
EOF
else
  scan_one "$target"
fi

if [ "$found" -eq 0 ]; then
  echo "PASS: $target"
  exit 0
fi
exit 1
