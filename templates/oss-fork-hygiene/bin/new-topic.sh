#!/usr/bin/env bash
# new-topic.sh — create a fresh topic branch from upstream/main.
# Always starts from upstream, not from the local fork's main.
set -eu

slug="${1:-}"
if [ -z "$slug" ]; then
  echo "usage: new-topic.sh <slug>" >&2
  echo "  example: new-topic.sh fix-cache-eviction-race" >&2
  exit 2
fi

# Sanity-check slug.
case "$slug" in
  *[!a-z0-9-]*) echo "[new-topic] slug must be lowercase a-z0-9 and -" >&2; exit 2 ;;
esac

if ! git remote get-url upstream >/dev/null 2>&1; then
  echo "[new-topic] no 'upstream' remote configured." >&2
  exit 2
fi

default_branch="$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@' || echo main)"

echo "[new-topic] fetching upstream/$default_branch"
git fetch upstream "$default_branch"

branch="topic/$slug"
if git rev-parse --verify "$branch" >/dev/null 2>&1; then
  echo "[new-topic] branch $branch already exists." >&2
  exit 3
fi

git switch -c "$branch" "upstream/$default_branch"
echo "[new-topic] on $branch (from upstream/$default_branch)"
