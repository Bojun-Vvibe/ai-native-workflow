# Template: OSS fork hygiene

A small, opinionated set of conventions and scripts for **managing
forks of upstream OSS projects** when you contribute to them
regularly with the help of AI agents. Covers remote layout, branch
naming, sync cadence, divergence detection, and the "is this fork
worth keeping?" decision.

## Why this exists

A fork left alone for six months is a security and trust liability:

- It diverges from upstream silently. Your CI passes against a
  9-month-old base; the upstream test suite tells a different story.
- Agents, asked to "fix the bug," edit the fork — but the upstream
  has already fixed it three different ways. You waste a mission
  reproducing work.
- The fork accumulates personal commits (config, debugging,
  half-finished experiments) that are embarrassing when someone
  visits the repo.
- A stale fork on your account can be a supply-chain risk if it's
  ever published as a package or pulled by automation.

This template gives you a **default fork shape** and a script that
audits all your forks in one pass.

## When to use

- You contribute to ≥3 OSS projects you don't own.
- You let agents run against a local clone of a fork (so the fork's
  state is the basis for any PR they propose).
- You publish from a personal account that also hosts your own
  projects — a stale fork there is more visible than on a throwaway.

## When NOT to use

- One-time contribution. Make a fork, send the PR, delete the fork.
  No hygiene needed.
- You contribute via patch email (Linux kernel style). No forks
  involved.
- The "fork" is actually a hard-fork (you're a maintainer of a
  divergent project). Different rules — you're now upstream.

## Anti-patterns

- **`origin` points at upstream.** When you `git push`, you push to
  the project you don't own and you'll fail. Convention:
  `origin` = your fork, `upstream` = the project. Reverse causes
  daily friction and mistakes.
- **Working on `main` of the fork.** `main` should mirror upstream
  exactly. All work happens on topic branches. If `main` diverges,
  every future sync becomes a merge conflict.
- **Force-pushing to `main`.** Eventually rewrites a commit a
  contributor referenced in a discussion thread, and the link 404s.
  Branch-protect `main` on your fork too.
- **Letting forks rot for 6+ months without an audit.** The script
  in this template lists every fork on your account and flags
  staleness, divergence, and missing branch protection.
- **Carrying private config in the fork.** A `.env.local` or
  personal `prices.json` that lands in a fork can leak when you
  open a PR against upstream from the wrong branch. Keep them in a
  sibling **non-fork** repo, or `.gitignore`d.
- **Publishing the fork as a package** under your name when
  upstream already publishes it. Causes namespace squatting
  problems and confused users.

## Files

- `bin/audit-forks.sh` — uses `gh` to list every fork on your
  account and prints: parent, last-sync date, ahead/behind counts,
  branch protection on `main`, presence of personal-only files
  (`.env*`, `prices.json`, etc).
- `bin/sync-fork.sh` — fetches upstream, fast-forwards `main`,
  pushes. Refuses if `main` has commits not in upstream (you
  diverged).
- `bin/new-topic.sh` — creates a topic branch from a freshly
  fetched upstream/main, naming it `topic/<slug>`.
- `examples/sample-audit-output.txt` — what the audit looks like
  on a realistic 7-fork account.
- `examples/contribution-flow.md` — the full per-contribution
  workflow, end-to-end, with commands.

## Worked example

```
$ bin/audit-forks.sh
fork                                upstream                 branches  behind  ahead  protected  flags
your-account/cline                  cline/cline              1         12      0      yes        ok
your-account/awesome-foo            owner-x/awesome-foo      4         412     3      no         STALE,UNPROTECTED
your-account/cool-tool              owner-y/cool-tool        2         3       0      yes        ok
your-account/abandoned-fork         owner-z/abandoned-fork   8         2200    47     no         STALE,DIVERGED,UNPROTECTED
your-account/ephemeral-experiment   owner-w/ephemeral        1         9       1      yes        ok

5 forks · 2 flagged
```

## Adapt this section

- Set `GH_USER` in your shell before running `audit-forks.sh`, or
  pass `--user`.
- Edit the `STALE_DAYS=90` constant if you want different
  thresholds.
- Decide your default branch convention (`topic/<slug>` vs
  `feat/<slug>`) and edit `new-topic.sh` accordingly.
- For each flagged fork, decide: **sync, archive, or delete**.
  Archived forks stop showing up in audits.

## Decision rubric: keep, archive, or delete a fork

| Symptom                                                         | Action |
|-----------------------------------------------------------------|--------|
| `behind: 0–50`, `ahead: 0`, no recent topic branches            | keep, no action |
| `behind: large`, `ahead: 0`, you contribute monthly             | sync now |
| `behind: large`, `ahead: 0`, no contribution in >6 months       | archive |
| `ahead: >0` on `main` (you diverged on the wrong branch)        | move work to a topic branch, then archive or hard-reset `main` to upstream |
| Fork was for a one-time PR that has since merged or been closed | delete |
| Upstream is itself archived/abandoned                           | delete (or hard-fork with a new name and a clear notice) |
