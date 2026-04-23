# Template: Daily OSS digest

A directory layout, file format, and generator pattern for producing
**one digest per day** across a fixed set of upstream OSS repos. Each
day's digest is a folder containing:

- one `INDEX.md` (the dashboard),
- one `<owner>-<repo>.md` per tracked repo (the per-repo summary).

The format is optimized for **read-once-then-archive**: you skim the
INDEX in 30 seconds, click into the 1–2 repos that had something
interesting, and the rest of the directory becomes a searchable
archive of what happened in your tracked ecosystem.

## Why this exists

If you track 5–15 OSS repos that move daily (LLM tooling, agent
frameworks, dev tools), keeping up via GitHub notifications is
hopeless: too noisy, no aggregation, no LLM-summarized "is anything
in here worth my time today?" Most "OSS digest" SaaS products
optimize for newsletter-style discovery, not for an engineer who
wants a structured record of what each tracked project actually did
in the last 24h.

This template gives you that record. It's a file format + an agent
prompt; the generator can be any script you write (or an LLM) that
fills the schema. The format itself is the contribution — once you
have hundreds of these directories, they become a corpus you can
grep ("when did `repo:foo/bar` last ship a release?"), train on, or
feed back into a weekly synthesis pass.

## When to use

- You track ≥3 OSS repos closely enough to want daily coverage.
- You want a **searchable archive**, not just an inbox.
- You want a consistent shape across repos so you can scan diagonally.
- You're willing to run a generator daily (cron, GitHub Actions, or a
  morning manual invocation).

## When NOT to use

- You track ≤2 repos — RSS or GitHub email notifications are fine.
- You only care about **releases** — a release-only feed is simpler
  than this template.
- You don't read the digests. (Be honest. If you generate but don't
  read, the value is zero. Cut tracked repos until the digest is
  short enough to actually read.)
- The repos you track are private — most of the format assumes
  public github.com URLs in the link sections.

## Anti-patterns

- **Tracking too many repos.** A digest covering 20 repos is a
  digest you'll skim once and stop reading. Cap at ~10. Rotate
  repos in/out quarterly based on what you actually click through to.
- **Skipping the LLM summary.** The raw "X commits, Y PRs merged"
  table is barely better than GitHub's own UI. The summary paragraph
  — "today is a Schema-migration day; if you import from MessageV2,
  read these in this order" — is where the value is. If you skip it,
  you've built a worse GitHub.
- **Embedding generated artifacts in the repo.** `chore: generate`
  bot commits, formatter passes, dep-bumps — the summary should
  call them out and tell the reader to skip, not list them as if
  they're substantive.
- **Per-repo length unbounded.** If `BerriAI/litellm` had 50 PRs
  merged today, do not list all 50 verbatim. Group by theme, link
  the labels view, name the 3 most notable. Or rotate to a weekly
  digest for that repo.
- **No window discipline.** "Last 24h" must be a precise UTC window
  in the file, otherwise your archive is unreproducible. Two
  generations of the "same day" should produce identical files.
- **Posting digests publicly without scrubbing.** If you track repos
  for work reasons, the *fact* that you track them can leak signal.
  Default to a private repo for the digest archive.

## Files

- `INDEX.template.md` — the dashboard skeleton.
- `repo-digest.template.md` — the per-repo skeleton.
- `targets.example.json` — the tracked-repos manifest. Each entry has
  a `full_name`, the focus signals to collect, the default branch,
  and a one-line `why` so future-you remembers why you added it.
- `prompts/repo-summarizer.md` — agent prompt that takes a day of
  raw events for one repo and emits the 1–3-paragraph daily summary.
- `prompts/index-summarizer.md` — agent prompt that takes the
  per-repo summaries and emits the index dashboard.
- `schemas/digest.schema.json` — JSON schema for a parsed digest
  (useful if you want a `digest --validate` step in your generator).
- `examples/sample-digest-day/` — a fully-worked synthetic day with
  INDEX + 3 per-repo files, demonstrating the format on a quiet day,
  a busy day, and a release day.

## The directory layout

```
digests/
  YYYY-MM-DD/
    INDEX.md
    <owner>-<repo>.md
    <owner>-<repo>.md
    ...
  YYYY-MM-DD/
    ...
  _weekly/
    YYYY-Www.md          # optional weekly synthesis
```

Filename convention: `<owner>-<repo>.md` with `/` replaced by `-`
(GitHub doesn't allow `-` in owner names so this is unambiguous).

## Adapt this section

- Window — defaults to the prior 24h UTC. Some users prefer "since
  last digest" so a missed day is still covered. Either is fine;
  pick one and document it.
- Focus signals — defaults to `[releases, prs, issues, commits]`.
  Drop `commits` for repos with high commit volume (it's noise);
  drop `issues` for repos where the issue tracker isn't where work
  happens.
- Per-repo length cap — defaults to ~600 words. Tighten if you find
  yourself skipping repos because they're too long.
- Weekly synthesis — optional. Run on Sundays from the prior 7
  daily digests. Same format minus the per-repo files; one big
  thematic INDEX.
