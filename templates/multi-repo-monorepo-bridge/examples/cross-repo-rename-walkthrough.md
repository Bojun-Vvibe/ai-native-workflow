# Worked example: cross-repo identifier rename

Goal: rename `getCwd` to `getCurrentWorkingDirectory` across the
4-repo workspace shown in `sample-bridge-tree.txt`.

Without a bridge, an agent told to do this rename in a single repo
would silently leave callers in the other three repos broken. With
the bridge, every step is one command.

## Step 1 — find all occurrences

```bash
$ bin/bridge-search.sh '\bgetCwd\b' ~/work-bridge
webapp/src/util/path.ts:14:    export function getCwd(): string {
webapp/src/util/path.ts:42:    return getCwd();
webapp/tests/path.test.ts:9:   expect(getCwd()).toMatch(/^\//)
sdk/lib/process.ts:5:          import { getCwd } from "../path-shim"
sdk/lib/process.ts:88:         const cwd = getCwd()
backend/cli/main.go:103:       cwd := getCwd()
backend/internal/util.go:22:   func getCwd() string {
docs/api/process.md:42:        `getCwd()` — current working dir
docs/api/process.md:67:        See [getCwd](#getCwd).
```

Note: the agent now sees that `getCwd` exists *separately* in
`webapp` (TS) and `backend` (Go) and that `sdk` imports the TS one.
The Go one and the TS one happen to share a name but are different
identifiers in different languages — the rename in Go is independent.

## Step 2 — plan per-repo scope

| Repo    | Scope                              | Owner | Risk |
|---------|------------------------------------|-------|------|
| webapp  | rename function + 2 callers + 1 test | you  | low  |
| sdk     | rename import (one line)             | you  | low — will break at compile if missed |
| backend | rename Go function + 1 caller        | you  | low — separate language, no cross-repo coupling |
| docs    | rename function name + anchor        | you  | low — but anchor links elsewhere? grep external repos for `#getCwd` |

## Step 3 — edit each repo

The agent makes the edits and commits **per child repo** with a
shared `Mission-Id:` trailer:

```bash
bin/bridge-git.sh ~/work-bridge/webapp commit -am 'refactor: rename getCwd to getCurrentWorkingDirectory

Mission-Id: M-2026-04-23-rename-getCwd
'

bin/bridge-git.sh ~/work-bridge/sdk commit -am 'refactor: update import to renamed getCurrentWorkingDirectory

Mission-Id: M-2026-04-23-rename-getCwd
'
# ... repeat for backend, docs
```

## Step 4 — verify nothing missed

```bash
$ bin/bridge-search.sh '\bgetCwd\b' ~/work-bridge
(no output)
```

Empty result confirms the rename is complete. Without a bridge,
this verification step is impossible without manually entering each
repo and re-running the search.

## Step 5 — open per-repo PRs

Each PR description references the shared `Mission-Id:` so a
reviewer can locate the sibling PRs in other repos. The bridge
itself stays local; nothing about the bridge ships to upstream.
