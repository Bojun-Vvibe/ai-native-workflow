#!/usr/bin/env bash
# sync-fork.sh — fast-forward the fork's main branch to upstream/main.
# Refuses if `main` has commits not in upstream (i.e. you diverged on
# the wrong branch). Run inside a working copy of the fork.
set -eu

if ! git remote get-url upstream >/dev/null 2>&1; then
  echo "[sync-fork] no 'upstream' remote configured." >&2
  echo "  hint: git remote add upstream <upstream-url>" >&2
  exit 2
fi

current_branch="$(git symbolic-ref --short HEAD)"
default_branch="$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's@^origin/@@' || echo main)"

if [ "$current_branch" != "$default_branch" ]; then
  echo "[sync-fork] not on default branch ($default_branch); on $current_branch. switching." >&2
  git checkout "$default_branch"
fi

echo "[sync-fork] fetch upstream"
git fetch upstream "$default_branch"

ahead="$(git rev-list --count "upstream/$default_branch..$default_branch")"
behind="$(git rev-list --count "$default_branch..upstream/$default_branch")"

echo "[sync-fork] $default_branch is ahead $ahead, behind $behind"

if [ "$ahead" -gt 0 ]; then
  echo "[sync-fork] REFUSE: your $default_branch has $ahead commits not in upstream." >&2
  echo "  This means you committed directly to $default_branch instead of a topic branch." >&2
  echo "  Move those commits to a topic branch first:" >&2
  echo "    git switch -c topic/recover-$(date +%s)" >&2
  echo "    git switch $default_branch && git reset --hard upstream/$default_branch" >&2
  exit 3
fi

if [ "$behind" -eq 0 ]; then
  echo "[sync-fork] already up to date."
  exit 0
fi

git merge --ff-only "upstream/$default_branch"
git push origin "$default_branch"
echo "[sync-fork] done."
