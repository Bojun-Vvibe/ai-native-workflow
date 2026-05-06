#!/usr/bin/env bash
# llm-output-hedgedoc-session-secret-default-detector
#
# Flags HedgeDoc deployments where the session-signing secret
# (CMD_SESSION_SECRET / sessionSecret) is left at an upstream
# placeholder, an empty value, or an obviously low-entropy string.
#
# Reads .env-style files, docker-compose env blocks, and the
# config.json / config.json.example layout.  Accepts a path to a
# file or a directory (recursive over a small allowlist of names).
#
# Exit codes:
#   0   PASS  no defaulted/weak session secret observed
#   1   FAIL  at least one defaulted/weak session secret observed
#   2   usage error
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <config-file-or-dir>" >&2
  exit 2
fi

target="$1"
if [ ! -e "$target" ]; then
  echo "no such path: $target" >&2
  exit 2
fi

# Known-bad placeholder values shipped in upstream docs / images
# / blog posts.  Compared case-sensitively against the literal RHS.
bad_values='
secret
hedgedoc
codimd
changeme
change-me
change_me
changethis
change-this
default
session-secret
sessionsecret
your-secret-here
replace-me
replaceme
PleaseChangeMe
'

found=0

emit_if_bad() {
  f="$1"; line="$2"; key="$3"; val="$4"
  if [ -z "$val" ]; then
    echo "FAIL: $f: $key is empty -> $line"
    found=1
    return
  fi
  vlen=${#val}
  if [ "$vlen" -lt 16 ]; then
    echo "FAIL: $f: $key is too short ($vlen chars) -> $line"
    found=1
    return
  fi
  while IFS= read -r bad; do
    [ -z "$bad" ] && continue
    if [ "$val" = "$bad" ]; then
      echo "FAIL: $f: $key matches known placeholder '$bad' -> $line"
      found=1
      return
    fi
  done <<EOF
$bad_values
EOF
}

strip_quotes() {
  v="$1"
  v="${v%\"}"; v="${v#\"}"
  v="${v%\'}"; v="${v#\'}"
  v="${v%,}"
  printf '%s' "$v"
}

scan_one() {
  f="$1"
  while IFS= read -r line; do
    case "$line" in
      \#*|//*) continue ;;
    esac
    raw="$(printf '%s' "$line" | sed -E 's/^[[:space:]]*//')"
    case "$raw" in
      CMD_SESSION_SECRET=*)
        val="${raw#CMD_SESSION_SECRET=}"
        val="$(strip_quotes "$val")"
        emit_if_bad "$f" "$line" "CMD_SESSION_SECRET" "$val"
        ;;
      "CMD_SESSION_SECRET ="*)
        val="${raw#CMD_SESSION_SECRET =}"
        val="${val# }"
        val="$(strip_quotes "$val")"
        emit_if_bad "$f" "$line" "CMD_SESSION_SECRET" "$val"
        ;;
      \"sessionSecret\":*|sessionSecret:*|"sessionSecret :"*)
        # config.json: "sessionSecret": "secret"
        val="${raw#*sessionSecret}"
        val="${val#\"}"
        val="${val# }"
        val="${val#:}"
        val="${val# }"
        val="$(strip_quotes "$val")"
        emit_if_bad "$f" "$line" "sessionSecret" "$val"
        ;;
    esac
  done < "$f"
}

if [ -d "$target" ]; then
  while IFS= read -r f; do
    case "$(basename "$f")" in
      .env|*.env|*.envtxt|docker-compose*.yml|docker-compose*.yaml|Dockerfile|config.json|config.json.example|*.conf)
        scan_one "$f"
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
