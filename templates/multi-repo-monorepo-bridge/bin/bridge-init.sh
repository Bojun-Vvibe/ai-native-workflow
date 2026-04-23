#!/usr/bin/env bash
# bridge-init.sh — create a multi-repo bridge directory.
# Usage: bridge-init.sh <bridge-root> <repo-path> [<repo-path> ...]
set -eu

if [ $# -lt 2 ]; then
  echo "usage: bridge-init.sh <bridge-root> <repo-path> [<repo-path> ...]" >&2
  exit 2
fi

bridge="$1"; shift
mkdir -p "$bridge"

manifest="$bridge/MANIFEST.toml"
{
  echo "# Bridge manifest. Auto-generated; safe to edit."
  echo "# Re-run bridge-init.sh to regenerate."
  echo
  echo "bridge_root = \"$bridge\""
  echo "created = \"$(date -Iseconds)\""
  echo
  echo "[ignore]"
  echo "globs = ["
  echo "  \"node_modules/\","
  echo "  \"target/\","
  echo "  \"dist/\","
  echo "  \".venv/\","
  echo "  \"__pycache__/\","
  echo "  \".tox/\","
  echo "  \".gradle/\","
  echo "  \".next/\","
  echo "  \"build/\","
  echo "  \"Pods/\""
  echo "]"
  echo
  echo "[[repo]]"
} >"$manifest"

count=0
for repo in "$@"; do
  if [ ! -d "$repo/.git" ]; then
    echo "[bridge-init] skipping (not a git repo): $repo" >&2
    continue
  fi
  name="$(basename "$repo")"
  link="$bridge/$name"
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    echo "[bridge-init] refuse: $link exists and is not a symlink" >&2
    exit 3
  fi
  ln -sfn "$repo" "$link"
  count=$((count + 1))
  {
    [ "$count" -eq 1 ] || echo "[[repo]]"
    echo "name = \"$name\""
    echo "path = \"$repo\""
    echo "link = \"$link\""
  } >>"$manifest"
done

echo "[bridge-init] created $bridge with $count repos"
echo "[bridge-init] wrote $manifest"
