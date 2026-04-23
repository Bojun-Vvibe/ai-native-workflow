# Per-contribution flow

The minimum-friction loop for landing one PR against an upstream
project, assuming you have a fork already cloned with the standard
remote layout (`origin` = your fork, `upstream` = the project).

## 1. Sync first

```bash
cd ~/code/the-fork
bin/sync-fork.sh
```

If `sync-fork.sh` refuses with `DIVERGED`, you committed to `main`
when you shouldn't have. Recover with:

```bash
git switch -c topic/recover-$(date +%s)
git switch main
git reset --hard upstream/main
git push --force-with-lease origin main   # only if you control the fork's main
```

## 2. Make a topic branch

```bash
bin/new-topic.sh fix-cache-eviction-race
```

This always branches from `upstream/main`, never from local `main`,
so your topic never inherits a stale base.

## 3. Hand the work to your agent

The agent works only on this topic branch. The `commit-msg` hook
from
[`commit-message-trailer-pattern`](../../commit-message-trailer-pattern/)
records cost trailers on each commit.

## 4. Push and open a PR

```bash
git push -u origin topic/fix-cache-eviction-race
gh pr create --repo upstream-owner/upstream-repo --base main \
  --head your-account:topic/fix-cache-eviction-race
```

## 5. Once merged (or rejected): clean up

```bash
git switch main
bin/sync-fork.sh                    # main now contains your merged commit
git branch -d topic/fix-cache-eviction-race
git push origin --delete topic/fix-cache-eviction-race
```

## 6. Periodically (monthly)

```bash
bin/audit-forks.sh
```

Triage the flagged forks per the rubric in the README.
