#!/usr/bin/env bash
# llm-output-wallabag-secret-default-detector
#
# Flags Wallabag deployments where SYMFONY__ENV__SECRET (the Symfony
# application secret used to sign CSRF tokens, "remember me" cookies,
# and the password-reset URL hash) is left at the upstream placeholder
# value, an empty string, or an obviously low-entropy string.
#
# Reads ENV-style files (docker-compose env_file, .env, parameters.yml,
# Dockerfile ENV) given a path to a file or a directory (recursive).
#
# Exit codes:
#   0   PASS  no defaulted/weak SECRET observed
#   1   FAIL  at least one defaulted/weak SECRET observed
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

# Known-bad placeholder values shipped in upstream docs / docker images.
# All comparisons are case-sensitive against the literal RHS string.
bad_values='
ThisTokenIsNotSoSecretChangeIt
RandomToken
MySecretToken
ChangeThisToken
changeme
changethis
default
secret
password
your-secret-here
replace-me
'

scan_one() {
  f="$1"
  # Pull SYMFONY__ENV__SECRET assignments. Accept both `KEY=VAL` and
  # `KEY: VAL` (parameters.yml style). Skip comment lines.
  while IFS= read -r line; do
    case "$line" in
      \#*) continue ;;
    esac
    raw="$(printf '%s' "$line" | sed -E 's/^[[:space:]]*//')"
    case "$raw" in
      SYMFONY__ENV__SECRET=*|"SYMFONY__ENV__SECRET ="*)
        val="${raw#SYMFONY__ENV__SECRET}"
        val="${val# }"
        val="${val#=}"
        val="${val# }"
        # strip surrounding quotes
        val="${val%\"}"; val="${val#\"}"
        val="${val%\'}"; val="${val#\'}"
        emit_if_bad "$f" "$line" "$val"
        ;;
      secret:*|"secret :"*)
        # parameters.yml: `    secret: ThisTokenIsNotSoSecretChangeIt`
        val="${raw#secret}"
        val="${val# }"
        val="${val#:}"
        val="${val# }"
        val="${val%\"}"; val="${val#\"}"
        val="${val%\'}"; val="${val#\'}"
        emit_if_bad "$f" "$line" "$val"
        ;;
    esac
  done < "$f"
}

emit_if_bad() {
  f="$1"; line="$2"; val="$3"
  # empty value
  if [ -z "$val" ]; then
    echo "FAIL: $f: SYMFONY__ENV__SECRET is empty -> $line"
    found=1
    return
  fi
  # short / low-entropy
  vlen=${#val}
  if [ "$vlen" -lt 16 ]; then
    echo "FAIL: $f: SYMFONY__ENV__SECRET is too short ($vlen chars) -> $line"
    found=1
    return
  fi
  # explicit known-bad placeholder
  while IFS= read -r bad; do
    [ -z "$bad" ] && continue
    if [ "$val" = "$bad" ]; then
      echo "FAIL: $f: SYMFONY__ENV__SECRET matches known placeholder '$bad' -> $line"
      found=1
      return
    fi
  done <<EOF
$bad_values
EOF
}

found=0

if [ -d "$target" ]; then
  # iterate plain files; only inspect *.env, .env, parameters*.yml,
  # docker-compose*.yml, Dockerfile, and *.conf to keep scope tight.
  while IFS= read -r f; do
    case "$(basename "$f")" in
      .env|*.env|*.envtxt|parameters*.yml|parameters*.yaml|docker-compose*.yml|docker-compose*.yaml|Dockerfile|*.conf)
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
