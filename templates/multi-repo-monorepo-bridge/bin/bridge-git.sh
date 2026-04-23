#!/usr/bin/env bash
# bridge-git.sh — run a git command against the right child repo,
# resolved from a path inside the bridge. Examples:
#   bridge-git.sh ~/work-bridge/webapp/src/foo.ts status
#   bridge-git.sh ~/work-bridge/sdk diff --stat
set -eu

if [ $# -lt 2 ]; then
  echo "usage: bridge-git.sh <path-inside-bridge> <git-args...>" >&2
  exit 2
fi

target="$1"; shift

# Resolve to an absolute path even if input is a symlink.
abs="$(cd "$(dirname "$target")" 2>/dev/null && pwd)/$(basename "$target")" || true
[ -e "$abs" ] || abs="$target"

# Walk upward until we find a .git or hit /.
dir="$abs"
[ -d "$dir" ] || dir="$(dirname "$dir")"
while [ "$dir" != "/" ]; do
  if [ -e "$dir/.git" ]; then
    break
  fi
  # Resolve symlink once: the bridge link points at the real repo.
  if [ -L "$dir" ]; then
    dir="$(readlink "$dir")"
    continue
  fi
  dir="$(dirname "$dir")"
done

if [ "$dir" = "/" ]; then
  echo "[bridge-git] no git repo found above $target" >&2
  exit 3
fi

echo "[bridge-git] in $dir: git $*" >&2
( cd "$dir" && exec git "$@" )
