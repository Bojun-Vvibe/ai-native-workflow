# reverse-engineer-cli

A methodology for **figuring out how a closed-or-undocumented CLI
actually behaves** — its commands, flags, exit codes, output shapes,
config files, environment variables, side effects, and failure
modes — without source access. The output is a written behavior
spec you (or an agent) can rely on for automation, wrapping,
mirroring, or building a compatible re-implementation.

This is the methodology I used when building [`pew`][pew] (a
shell-pipeable insights tool) and reused later when reverse-
engineering several developer CLIs whose `--help` was, charitably,
aspirational.

[pew]: https://github.com/Bojun-Vvibe/pew-insights

## When to use this

- You need to script around a CLI but its docs are stale, missing,
  or contradicted by behavior.
- You're building a wrapper, mirror, or compatible alternative
  and need to match the original's contract precisely.
- You're going to let an AI agent drive the CLI, and the agent
  needs a stable behavior spec — `--help` is not enough.
- The CLI is ours to use but not ours to read (third-party,
  closed-source, or deeply nested through wrappers).

## When NOT to use this

- The CLI has good first-party docs that match observed behavior.
  Read those instead; don't burn budget rediscovering.
- You only need one or two commands, one-shot. Just probe the
  ones you need; don't build the full spec.
- The CLI is a thin wrapper over an HTTP API and the API is
  documented. Spec the API, not the CLI.
- Reverse-engineering would violate a license or ToS you've
  agreed to. This methodology is for **observing externally
  legitimate behavior**, not for bypassing protections.

## The methodology, in five passes

### Pass 1 — Surface enumeration
Goal: enumerate the command tree, every flag, every subcommand.

1. `the-cli --help`, `the-cli -h`, `the-cli help` (try all three;
   they sometimes disagree).
2. For every subcommand listed: `the-cli <sub> --help`. Recurse
   to leaves.
3. Look for hidden flags: `--debug`, `--verbose`, `--json`,
   `--no-color`, `--config`, `--version`. Many CLIs hide these
   from `--help`. Try them.
4. Diff `--help` output against any binary strings you can
   legitimately extract (`strings $(which the-cli) | grep -E '^--'`
   on macOS/Linux). This often reveals undocumented flags.

Output: `surface.md` — the full command/flag tree.

### Pass 2 — Output-shape probing
Goal: know exactly what each command writes to stdout, stderr,
and the filesystem.

1. Run each leaf command on a representative input.
2. Capture stdout, stderr, exit code, and any files created/modified
   (use `lsof` or a snapshot of the working dir).
3. If the CLI has `--json` or similar, run with and without it and
   diff. Note which fields are present only in JSON vs human mode.
4. Identify deterministic vs non-deterministic fields (timestamps,
   request IDs, ordering). Mark them in your spec.

Output: per-command shape table — stdout schema, stderr triggers,
exit code map, side effects.

### Pass 3 — Failure-mode probing
Goal: know how the CLI fails. This is what most docs lie about.

1. Empty input, missing required flag, wrong type, nonexistent
   path, no permissions, network down, invalid auth.
2. Capture the exit code and the stderr message for each.
3. Note which failures write to stdout (bad CLIs do this) and
   which write to stderr (good CLIs).
4. Probe race conditions if relevant: two concurrent invocations
   on the same target.

Output: failure-mode table. This is the section future-you and
agents will reference most.

### Pass 4 — Configuration & environment
Goal: every input source the CLI reads beyond CLI flags.

1. Config files: try `~/.<name>rc`, `~/.config/<name>/`,
   `./.<name>.toml`, `./<name>.config.json`, etc. Use `strace`
   (Linux) or `dtruss` (macOS) on a single invocation to log
   every `open()` — this reveals config file lookups
   exhaustively.
2. Environment variables: `strings $(which the-cli) | grep -E
   '^[A-Z][A-Z0-9_]+$'` is a starting point; many env vars are
   referenced as bare strings.
3. Precedence: when both a flag and an env var are set, which
   wins? Document it.
4. State / cache directories: where does it persist between runs?

Output: config + env reference. Mark which inputs are required vs
optional vs only-in-edge-cases.

### Pass 5 — Behavior spec assembly
Goal: turn the four probe outputs into a single document an
agent or another developer can rely on.

Sections:
1. Surface (command tree)
2. Per-command behavior (input → output, side effects, exit code)
3. Failure modes (what triggers each non-zero exit)
4. Configuration (files, env vars, precedence)
5. Known quirks / non-obvious behaviors
6. Things you tested but couldn't determine (be honest)

This document is the deliverable. It should be diffable — when
the CLI updates, you re-run the probes and diff the spec.

## Files

- `checklists/probe-checklist.md` — printable per-command checklist
  for Passes 1–4. Walk through it for each leaf command.
- `checklists/spec-template.md` — skeleton for the Pass 5
  behavior spec. Copy and fill.
- `examples/pew-cli-spec-excerpt.md` — partial worked example:
  the actual behavior spec I produced for one command of `pew`,
  showing the level of detail Pass 5 should reach.
- `examples/methodology-trace.md` — narrative of how I applied
  the 5 passes to a small unfamiliar CLI in ~90 minutes, including
  what each pass discovered that the previous one missed.

## Anti-patterns

- **Stopping after Pass 1.** Knowing the flags is not knowing the
  CLI. Failure-mode and config passes find the things that break
  your automation in production.
- **Trusting `--help` over observed behavior.** Help text and
  behavior diverge surprisingly often. Always probe.
- **Probing in production.** Side-effects might be irreversible.
  Use a sacrificial environment; snapshot before each probe.
- **Letting an agent do the probing without a checklist.** It
  will skip the boring failure-mode cases. That's exactly where
  your automation will later break. Use the checklist; have the
  agent fill it.
- **Calling the spec "done" without the "things I couldn't
  determine" section.** Acknowledged unknowns are signal; pretend-
  knowing is risk.
- **Re-spec from scratch on every CLI update.** Keep the spec in
  git, re-run probes, diff. Most updates are additive.

## Related

- `scout-then-act-mission` — the per-pass discipline mirrors
  scout-then-act applied to a CLI instead of a codebase.
- `sub-agent-context-isolation` — Passes 1–4 are perfect
  delegations to sub-agents (each pass returns a structured table).
- `llm-eval-harness-minimal` — once you have the spec, you can
  build a harness that asserts the spec is still true on each
  CLI release.
