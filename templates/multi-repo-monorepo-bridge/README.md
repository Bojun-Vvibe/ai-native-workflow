# Template: Multi-repo monorepo bridge

A pattern for treating **N independent repos as one logical
workspace** for an AI agent, without actually merging them into a
monorepo. You get the agent ergonomics of a monorepo (one search
surface, one `cd`-less workflow, one mental model) while keeping
the deployment-and-ownership benefits of separate repos.

## Why this exists

Real projects span repos:

- A web app, an iOS app, a backend, a shared SDK, a docs site, an
  infra repo. Five to ten repos that change together half the time.
- Agents asked "where is `LoginButton` defined?" need to grep across
  all of them. Without a bridge, the agent picks one, finds nothing,
  declares the function doesn't exist, and writes a duplicate.
- Cross-repo refactors ("rename `getCwd` to `getCurrentWorkingDirectory`")
  silently miss half the call sites because the agent never opened
  the consumer repo.

A bridge directory + a small index gives the agent a single root to
search and a manifest of which repo owns which path — without the
monorepo migration nobody has time for.

## When to use

- ≥3 closely-coupled repos under your daily edit cadence.
- You routinely run agents that need "find all callers of X" across
  repo boundaries.
- The repos won't merge into a real monorepo any time in the next
  6–12 months (otherwise just do the monorepo).

## When NOT to use

- One repo. Or repos owned by entirely separate teams that don't
  cross-edit. Bridges add friction with no payoff.
- The repos genuinely *should* be a monorepo and you're avoiding it
  for political reasons. Fix the underlying problem.
- Strict access control: some agents/users may see repo A but not
  repo B. A bridge directory will leak the shape of B (file names,
  structure) even if file contents are inaccessible. Use separate
  workspaces.

## Anti-patterns

- **Symlinking the whole repo into one parent dir without an
  index.** The agent doesn't know which paths are which repo's; a
  shared file name (`README.md`, `package.json`) shows up N times
  with no way to tell what owns it.
- **Forgetting to scope `git` operations to the right child repo.**
  Running `git status` at the bridge root touches nothing useful
  (the bridge itself has no `.git`). Wrap commands in a helper that
  resolves the right child repo from a path.
- **Cross-repo edits in a single agent turn without a per-repo
  commit.** One commit that spans repos cannot be reverted
  atomically. Per-repo commits, with a shared `Mission-Id:` trailer
  (see [`commit-message-trailer-pattern`](../commit-message-trailer-pattern/)).
- **Bridge becomes the source of truth.** The agent edits the
  bridge symlink target, not the actual repo. If your bridge uses
  symlinks, edits flow through correctly. If it uses copies, the
  copies drift. Symlinks only.
- **Hardcoding absolute paths in the index.** Bridges should be
  portable across machines (laptop, dev VM, CI). Use repo-root
  variables, not `/Users/yourname/...`.
- **One giant `find` across the bridge root that excludes nothing.**
  `node_modules`, `target/`, `.venv/`, `dist/` will dominate every
  search. Pre-filter at index time.

## Files

- `bin/bridge-init.sh` — creates a bridge directory at a chosen
  root, symlinks the listed repos into it, writes a `MANIFEST.toml`
  recording which symlink points where.
- `bin/bridge-search.sh` — wraps `rg` (ripgrep) with the bridge's
  ignore rules pre-applied (skip `node_modules`, etc).
- `bin/bridge-git.sh` — runs a git command against the right child
  repo, resolved from a path inside the bridge.
- `MANIFEST.toml.example` — example bridge manifest.
- `examples/sample-bridge-tree.txt` — what the bridge looks like
  on disk for a realistic 4-repo workspace.
- `examples/cross-repo-rename-walkthrough.md` — a worked example
  of a cross-repo identifier rename, end-to-end.

## Worked example

```
$ bin/bridge-init.sh ~/work-bridge \
    ~/code/webapp \
    ~/code/sdk \
    ~/code/backend \
    ~/code/docs

[bridge-init] created ~/work-bridge with 4 repos
[bridge-init] wrote ~/work-bridge/MANIFEST.toml

$ tree -L 2 ~/work-bridge
~/work-bridge/
├── MANIFEST.toml
├── webapp -> /Users/you/code/webapp
├── sdk    -> /Users/you/code/sdk
├── backend -> /Users/you/code/backend
└── docs   -> /Users/you/code/docs

$ bin/bridge-search.sh "getCwd" ~/work-bridge
webapp/src/util/path.ts:14: export function getCwd(): string {
sdk/lib/process.ts:88:        const cwd = getCwd();
backend/cli/main.go:103:    cwd := getCwd()
docs/api/process.md:42:     `getCwd()` — current working dir
```

The agent now has a single root to search, with results clearly
labeled by repo.

## Adapt this section

- Pick a stable bridge root (`~/work-bridge` is fine).
- Re-run `bridge-init.sh` whenever you add or remove a repo from
  the working set.
- Wire the bridge root into your agent config as the working
  directory.
- For each cross-repo task, instruct the agent to search via
  `bridge-search.sh` and commit per child repo with a shared
  `Mission-Id:` trailer.
