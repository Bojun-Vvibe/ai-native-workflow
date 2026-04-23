# Template: Commit-message trailer pattern

A discipline for **machine-readable trailers** on every commit
produced (or assisted) by an AI agent: `Co-Authored-By:` for
attribution, plus per-commit cost trailers (`Tokens-In:`,
`Tokens-Out:`, `Cache-Hit-Rate:`, `Model:`, `Mission-Id:`).

The result: `git log` becomes a queryable cost ledger. You can ask
"how many commits in the last 30 days were >50k input tokens?" with
a one-line `git log --grep`.

## Why this exists

Without trailers:

- You cannot tell which commits an agent wrote vs you wrote.
- You cannot tell which commits were expensive.
- You cannot correlate a regression to "this is the commit where the
  agent ran out of context budget and made a bad choice."
- Your monthly token budget is a number from your provider's
  dashboard with no link back to actual code.

With trailers:

- `git log --author="agent-*" --grep "Tokens-In:"` lists every
  agent-authored commit with its cost inline.
- A weekly script aggregates `Tokens-In` across the repo and prints
  cost-per-mission-type.
- Code review can ask: "this commit cost $4.20; is the diff worth
  it?" without leaving the terminal.

## When to use

- Multiple humans + multiple agents committing to the same repo.
- You're already using
  [`token-budget-tracker`](../token-budget-tracker/) and want the
  per-commit cost story to live in `git log` instead of a separate
  database.
- You want auditability: "show me everything model X wrote last week."

## When NOT to use

- Solo repo, single human, no agents. Trailers are noise.
- Open-source upstream that doesn't accept trailers (some projects
  squash them out). Use trailers in your fork; strip on PR.
- Compliance-sensitive context where logging the model name into
  public commit history is itself a leak. Audit the trailer keys
  first.

## Anti-patterns

- **Trailer-stuffing.** Don't add 12 trailers. Five is the working
  ceiling. Anything else belongs in a separate ledger.
- **Inconsistent keys.** `Token-In:` vs `Tokens-In:` vs
  `tokens_in:` is the difference between a queryable ledger and
  garbage. Pin a key list in `TRAILERS.md` and validate.
- **Trailers that drift from the commit body.** A `Mission-Id:`
  trailer must match the mission referenced in the body. If it
  doesn't, your audit trail lies.
- **Putting prose in trailers.** Trailers are `Key: scalar-value`.
  If you want prose, write it in the commit body.
- **Co-Authored-By for the human you're pairing with.** That's the
  primary author. Co-Authored-By is for *additional* contributors
  beyond the commit author — typically the AI agent.
- **Forgetting the blank line before trailers.** `git interpret-trailers`
  only sees a block separated from the body by a blank line. Without
  it, your "trailers" are body text and unqueryable.

## Files

- `src/format-trailers.py` — produces a trailer block from a JSON
  usage record. Use in your agent's commit-message builder.
- `src/parse-trailers.sh` — reads `git log --format=%(trailers)`
  and prints a CSV: `sha,model,tokens_in,tokens_out,cache_hit_rate`.
- `hooks/commit-msg` — git hook that validates trailer keys against
  the allow-list and rejects unknown keys.
- `TRAILERS.md` — the canonical key list and value formats.
- `examples/sample-commit-message.txt` — one well-formed message.
- `examples/sample-log.txt` — the result of running
  `parse-trailers.sh` against a 5-commit fixture.

## Worked example

A commit message produced by an agent commit-builder:

```
template: oss-pr-prep-checklist

Adds a mission template that produces a contribution package for
a target OSS repo. Worked example targets cline/cline.

Co-Authored-By: agent-implementer <agent@example.invalid>
Mission-Id: M-2026-04-23-W08
Model: claude-opus-4.7
Tokens-In: 47213
Tokens-Out: 8842
Cache-Hit-Rate: 0.74
```

Then:

```
$ ./examples/run-parse.sh
sha,model,tokens_in,tokens_out,cache_hit_rate
8a3f1c2,claude-opus-4.7,47213,8842,0.74
b71e09d,claude-sonnet-4.5,12044,2199,0.91
...
```

## Adapt this section

- Edit `TRAILERS.md` to your key list. Keep it short.
- Wire `format-trailers.py` into your agent's commit builder.
  Trailers go *after* a blank line at the end of the message.
- Install `hooks/commit-msg` (`ln -s ../../templates/.../hooks/commit-msg .git/hooks/commit-msg`).
- Add `parse-trailers.sh` to your weekly cost-report cron.
