# Methodology trace: applying the 5 passes to an unfamiliar CLI

This is a narrative of how I (or an agent driving the methodology)
work through a fresh CLI in ~90 minutes for a small one and ~4
hours for a medium one. The CLI in this trace is fictional
(`fooctl`, ~6 commands) but the timing and pass-by-pass discoveries
mirror real sessions.

## Setup (5 min)

- Sacrificial environment: a Docker container with the CLI
  installed, a clean `$HOME`, no real credentials.
- Snapshot the working dir before each probe (`tar` it).
- Open three terminals: probe, log, spec-being-written.

## Pass 1 — Surface (15 min)

Ran `fooctl --help`, `fooctl -h`, `fooctl help`. Two of the three
agreed; `fooctl help` listed an extra subcommand `fooctl debug`
that the others didn't.

For each subcommand, ran `fooctl <sub> --help`. Found 6 leaves:
`init`, `sync`, `pull`, `push`, `status`, `debug`.

`strings $(which fooctl) | grep -E '^--' | sort -u` produced 23
flag-shaped strings. `--help` documented 18. The 5 undocumented
candidates: `--profile`, `--no-cache`, `--dry-run`, `--strict`,
`--trace`. Tested each: 4 of 5 were real flags. `--strict` was a
binary string but produced "unknown flag" — turned out to be a
substring of an error message template, not a flag. Note this
in the spec.

**Pass 1 deliverable:** command tree + 22 confirmed flags.

## Pass 2 — Output shape (25 min)

For each leaf, ran a representative invocation and captured stdout,
stderr, exit code, and a `find $HOME -newer <snapshot>` to detect
file changes.

Discoveries:

- `fooctl sync` writes a progress bar to stderr (good — keeps
  stdout clean for piping). But the final summary line goes to
  **stdout**, mixing data and chrome. Note for spec.
- `fooctl pull --json` and `fooctl pull` produce structurally
  different content, not just formatting. The JSON form includes
  a `request_id` field absent from the human form. Worth a quirk
  entry.
- `fooctl status` exit code is 0 when "nothing to sync" and **1**
  when "things to sync" — not an error, just a status convention
  (à la `git status --porcelain` patterns). Caller scripts that
  treat non-zero as failure will misbehave. Critical to flag.

**Pass 2 deliverable:** per-command shape table.

## Pass 3 — Failure modes (25 min)

Walked the failure-modes section of the probe checklist for each
leaf. Highlights:

- `fooctl init` on an already-initialized directory returns 0
  silently. Idempotent — fine, but undocumented.
- `fooctl push` with no network returns exit code 7 and writes
  `error: network unreachable` to stderr. Reasonable. But with
  intermittent network (loss mid-push), it returns exit code 0
  and writes a partial state file. **This is a real footgun**:
  scripts will think the push succeeded. Top quirk entry.
- `fooctl sync` interrupted by SIGINT cleanly removes its
  partial `.tmp` file. Good citizen.
- Two concurrent `fooctl sync` invocations on the same target:
  one wins, one fails with exit code 11 and `error: lock held`.
  Documented behavior: lock file is at `~/.fooctl/sync.lock`.

**Pass 3 deliverable:** failure-mode table + the partial-push
quirk that justified the whole exercise.

## Pass 4 — Configuration & environment (15 min)

`dtruss -f -t open fooctl status 2>&1 | grep -E 'fooctl|\.toml|\.rc'`
revealed config file lookup order:

1. `--config` flag
2. `$FOOCTL_CONFIG`
3. `./.fooctl.toml`
4. `~/.config/fooctl/config.toml`
5. `~/.fooctlrc`

`--help` documented only #1 and #4. Two undocumented config
paths.

`strings` revealed env vars: `FOOCTL_CONFIG`, `FOOCTL_TOKEN`,
`FOOCTL_PROFILE`, `FOOCTL_DEBUG`, `NO_COLOR`. Tested each:
all real, all functional.

Precedence: flag > env > config > default. Confirmed by setting
all four for the same key and observing which value won.

State directory: `~/.fooctl/`. Contains `cache.db` (SQLite) and
`sync.lock`. Cache has no TTL — grows forever. Worth a quirk
entry: "long-running users should periodically `rm cache.db`."

**Pass 4 deliverable:** config + env reference + the
"cache grows forever" gotcha.

## Pass 5 — Spec assembly (5 min)

Filled the `spec-template.md` skeleton from Passes 1–4. Most of
the time at this point is just transcription, since the four
passes already produced structured data.

Things that ended up in "tested but couldn't fully determine":
- Whether `fooctl push` retries on transient HTTP 5xx (couldn't
  reproduce reliably without controlling the server).

Things that ended up in "deliberately not tested":
- `fooctl debug --reset-all` — too destructive to probe in any
  environment that mattered.

## Total: ~90 min for a 6-command CLI

The single most valuable discovery was the **partial-push silent
success** in Pass 3. That bug would have eaten weeks of debugging
if I'd built automation on top of `fooctl push` based on
`--help` alone. Pass 3 is the pass people skip and the pass that
pays for the methodology.

## Lessons that generalize

1. **`--help` and binary `strings` disagree more than you'd think.**
   Always cross-check.
2. **Status-style exit codes (`git status --porcelain` pattern) are
   common and undocumented.** Always test the "nothing to do" case
   and the "things to do" case separately.
3. **Network failure modes are where CLIs lie most.** Probe with
   intermittent network, not just no network.
4. **Config file lookup order is almost never fully documented.**
   `strace`/`dtruss` is the only reliable way to find them all.
5. **The methodology is parallelizable.** Passes 1, 2, 3, 4 for
   different leaf commands can be dispatched to sub-agents (see
   `sub-agent-context-isolation`). Each returns a structured table;
   parent assembles the spec.
