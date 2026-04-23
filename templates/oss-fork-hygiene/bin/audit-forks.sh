#!/usr/bin/env bash
# audit-forks.sh — list every fork on a GitHub account and flag
# stale, diverged, or unprotected ones. Read-only.
#
# Requires: gh, jq.
# Usage:    bin/audit-forks.sh [--user <handle>] [--stale-days N]
set -eu

USER_HANDLE="${GH_USER:-}"
STALE_DAYS=90

while [ $# -gt 0 ]; do
  case "$1" in
    --user) USER_HANDLE="$2"; shift 2 ;;
    --stale-days) STALE_DAYS="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$USER_HANDLE" ]; then
  USER_HANDLE="$(gh api user --jq .login)"
fi

# Header
printf "%-40s %-30s %8s %7s %6s %10s %s\n" \
  "fork" "upstream" "branches" "behind" "ahead" "protected" "flags"

flagged=0
total=0
now_epoch="$(date +%s)"

# List forks owned by USER_HANDLE.
gh api "users/$USER_HANDLE/repos?per_page=100&type=owner" \
  --paginate \
  --jq '.[] | select(.fork) | {name: .full_name, parent_url: .url, pushed_at}' \
| jq -c '.' \
| while read -r line; do
    fork="$(echo "$line" | jq -r .name)"
    pushed_at="$(echo "$line" | jq -r .pushed_at)"
    total=$((total + 1))

    parent_full="$(gh api "repos/$fork" --jq '.parent.full_name // "?"')"
    branch_count="$(gh api "repos/$fork/branches?per_page=100" --jq 'length' 2>/dev/null || echo 0)"

    # ahead/behind on default branch.
    default_branch="$(gh api "repos/$fork" --jq '.default_branch')"
    parent_default="$(gh api "repos/$parent_full" --jq '.default_branch' 2>/dev/null || echo "$default_branch")"
    cmp="$(gh api "repos/$parent_full/compare/$parent_default...$USER_HANDLE:$default_branch" \
            --jq '{ahead: .ahead_by, behind: .behind_by}' 2>/dev/null || echo '{"ahead":0,"behind":0}')"
    ahead="$(echo "$cmp" | jq -r .ahead)"
    behind="$(echo "$cmp" | jq -r .behind)"

    # Protection on default branch (best-effort).
    protected="no"
    if gh api "repos/$fork/branches/$default_branch/protection" >/dev/null 2>&1; then
      protected="yes"
    fi

    # Compute flags.
    flags=""
    pushed_epoch="$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$pushed_at" +%s 2>/dev/null || date -d "$pushed_at" +%s)"
    age_days=$(( (now_epoch - pushed_epoch) / 86400 ))
    if [ "$age_days" -gt "$STALE_DAYS" ]; then flags="${flags}STALE,"; fi
    if [ "$ahead" -gt 0 ]; then flags="${flags}DIVERGED,"; fi
    if [ "$protected" = "no" ]; then flags="${flags}UNPROTECTED,"; fi
    if [ -z "$flags" ]; then flags="ok"; else flags="${flags%,}"; flagged=$((flagged + 1)); fi

    printf "%-40s %-30s %8s %7s %6s %10s %s\n" \
      "$fork" "$parent_full" "$branch_count" "$behind" "$ahead" "$protected" "$flags"
  done

echo
echo "(audit done; STALE threshold = ${STALE_DAYS}d)"
