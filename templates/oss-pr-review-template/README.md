# Template: OSS PR review (long-form, learning-oriented)

A markdown template plus prompt for writing **long-form, deeply
contextualized PR reviews** of someone else's open-source
contribution — the kind you would publish on your blog or keep as a
personal learning archive, not the kind you would post as a
review-with-changes-requested on the PR itself.

This is **not** a "drive-by reviewer" template. The output is a
~2–4 page document per PR that captures:

- the upstream context the PR fits into,
- a hunk-by-hunk walkthrough of the substantive change,
- the test strategy and what it actually exercises,
- risks and edge cases,
- specific clarifying questions for the author,
- a verdict, and
- **a "what I learned" synthesis** — the durable takeaway that
  generalizes beyond this PR.

## Why this exists

Most review tooling optimizes for the **author's** flow: inline
comments, change-requested gates, suggestion blocks. Those formats
are fine for the half-page of feedback the author needs to act on.
They are useless for **your own learning** six months later, because
the comments are scattered across the PR conversation and you can't
re-read them as one document.

This template optimizes for **you, the reviewer**. The artifact is
structured so that:

1. You can re-read it standalone in a year and still understand the
   PR's significance without re-loading the entire codebase.
2. The "what I learned" section lifts the durable lesson out so it's
   searchable across your archive.
3. The structured front-matter makes the corpus indexable later
   (you can grep all your reviews of `repo:foo/bar` or all your
   reviews where `risk: high`).

The format is also a **forcing function for actually understanding
the PR**. You cannot write a good "what I learned" paragraph without
having understood the change at the level a senior reviewer would.

## When to use

- You are studying a codebase by reading its PRs (the single best
  way to onboard quickly).
- You want to leave a high-quality review on a hard PR but the inline
  comment surface is too cramped for the context you need to convey.
- You're building a **personal learning archive** of OSS work you've
  studied.
- You're triaging a stream of OSS PRs and want one consistent format
  per PR.

## When NOT to use

- The PR is a **trivial change** (typo, dep bump, lint fix) — the
  template is overkill.
- You only want to leave a one-sentence comment on the PR — write
  the comment, skip this.
- You're reviewing your **own team's** PR with full context already
  in your head — this format's strength is "rebuilding context for a
  PR you're encountering cold."
- The PR is **closed/merged** and you're never going to interact with
  the author — fine to use, but adjust tone (the questions become
  rhetorical / for your own future-self).

## Anti-patterns

- **Skipping the front-matter.** The structured fields are how you
  index the corpus later. If you don't fill them in, you lose the
  searchability that justifies the format.
- **Writing the "what I learned" section first.** It will warp every
  other section to defend that lesson. Write it last.
- **Padding the diff walkthrough.** If a hunk is mechanical
  (renaming, formatting), say so in one line and move on. The
  walkthrough is for the substantive hunks, not all of them.
- **Copy-pasting large code blocks without editing.** Quote the
  smallest snippet that makes the point. If you find yourself
  pasting >40 lines from one file, you're using this template as a
  notepad, not as a review.
- **Reviewing the author, not the code.** No "X always does Y" or
  speculation about the author's intent. Stick to what the diff
  shows.
- **Verdicts without conditions.** "Looks good" is useless. Either
  say "ready to merge" with the conditions you'd want addressed, or
  "not ready" with the specific blockers. Wishy-washy verdicts mean
  you skipped the hard part.

## Files

- `review.template.md` — the markdown skeleton. Drop in a new file
  named `PR-<number>.md`, fill the front-matter, write each section.
- `prompts/reviewer.md` — agent prompt that takes a PR URL and emits
  a draft review in this format. Designed for "draft for me to edit,"
  not "post unattended."
- `examples/sample-PR-review.md` — a fully-worked review of a
  hypothetical (but realistic) refactor PR, demonstrating depth +
  tone. Synthetic data; no real PR is invoked.

## The format at a glance

```markdown
---
pr_number: <int>
pr_title: "<title>"
repo: <owner>/<name>
author: <github-handle>
url: <pr url>
fetched_at: <yyyy-mm-dd>
files_changed: <int>
additions: <int>
deletions: <int>
focus_files:
  - path/to/the/substantive/file.ts
note: "<one-line: which subset of the diff this review focuses on, if not all>"
---

# Context
<2–4 paragraphs: what subsystem is this, what constraint or invariant
is at play, what would break if this PR landed wrong>

# Diff walkthrough
<hunk by hunk on the substantive files only — quote small snippets,
explain what changed and why>

# Test coverage
<what the new/changed tests actually exercise, what they don't, and
whether that gap matters>

# Risks
<numbered list — concrete failure modes if this lands as-is>

# Clarifying questions for the author
<numbered list — specific, answerable, non-rhetorical>

# Verdict
**<Ready to merge | Ready after Q&A | Not ready>**: <one paragraph
of justification with the conditions>

# What I learned
<one durable paragraph — the generalizable lesson, not a recap>
```

## Adapt this section

- Front-matter fields — `risk`, `category`, `reviewer_confidence` are
  common additions if you want to slice your corpus more finely.
- Section order — some reviewers prefer "Verdict" first as a TL;DR.
  Just be consistent across your archive.
- "What I learned" — if you publish the corpus, consider gating this
  section behind a `## Public` / `## Private` split so you can keep
  speculative or unflattering takes out of the published version.
- Tone — defaults to "respectful peer." Soften further (more
  questions, fewer assertions) when reviewing senior maintainers'
  work; tighten when reviewing your own juniors'.
