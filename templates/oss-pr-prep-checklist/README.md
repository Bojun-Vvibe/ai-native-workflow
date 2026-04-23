# Template: OSS PR-prep checklist mission

A spec-kitty mission template that turns "I want to contribute to OSS repo
X" into a concrete contribution package: contribution-guidelines summary,
filtered list of good first issues, a chosen issue, a draft PR description,
and a list of files likely to need changing — all written to local files
for human review.

The mission **never** opens issues, never opens PRs, never pushes branches.
It produces a contribution package the human reviews and decides whether
to act on.

## Purpose

Contributing to a new OSS repo has a fixed onboarding cost: read CONTRIBUTING,
read CODE_OF_CONDUCT, find an issue you can actually do, understand the
codebase enough to scope a PR, write a description that the maintainer will
read. AI agents are well-suited to compress that onboarding into a research
report. They are not well-suited to actually opening the PR — the social
dynamics around drive-by AI PRs in OSS are bad, and rightly so.

This template does the research; you do the contribution.

## When to use

- You're considering contributing to a repo you haven't worked on before.
- You want to make sure the issue you pick is actually a fit before
  spending time on it.
- You want a sanity check on which files you'd need to touch.

## When NOT to use

- Repos you maintain or contribute to regularly. You already have the
  context this template assembles.
- Repos with a contributor-license-agreement workflow that requires
  signing on issue claim — the template won't sign it for you, and
  shouldn't.
- Any workflow where the agent would actually post the PR. **This
  template never does that.** If you fork it to add posting, gate
  it behind explicit per-PR human approval and disclose AI assistance
  in the PR description.

## Files

- `mission.example.yaml` — wires the four phases (read guidelines, filter
  issues, pick + draft, file scan).
- `prompts/onboarder.md` — the agent that summarizes contributing
  guidelines.
- `prompts/issue-filter.md` — the agent that filters issues against fit
  criteria.
- `prompts/pr-drafter.md` — the agent that writes the PR description draft.
- `examples/cline-cline-run.md` — example run targeting [cline/cline](https://github.com/cline/cline).

## Outputs

Written to `contribution-package/`:

- `guidelines-summary.md` — distilled contributing guidelines, code of
  conduct highlights, PR conventions, test/build commands.
- `filtered-issues.md` — list of candidate issues with fit notes.
- `chosen-issue.md` — the issue the user selects (or the agent
  recommends), with full context.
- `pr-draft.md` — a draft PR description: title, summary, motivation,
  test plan, screenshots-if-applicable placeholder.
- `files-likely-to-change.md` — based on a scout-style read of the repo,
  the files the change probably touches.

## Adapt this section

- `target_repo` — the OSS repo you're considering.
- `fit_criteria` in `prompts/issue-filter.md` — your skills, language
  preferences, time available. This is the most project-personal part
  of the template.
- `label_filters` in `mission.example.yaml` — by default
  `good first issue` + `help wanted`, exclude `stale` and `wontfix`.
  Tune for the target repo's label conventions.
- `disclose_ai_assistance` in `prompts/pr-drafter.md` — by default the
  PR draft includes a one-line AI-assistance disclosure block. Some
  contributors prefer to omit; some maintainers require it. Pick a
  position deliberately.

## Safety notes

- **The mission only DRAFTS to local files. It NEVER posts.** No GitHub
  write API calls, no `gh pr create`, no `git push`. The drafted PR
  description sits in `pr-draft.md` until you decide to use it.
- The agent should disclose AI assistance in the PR description. This
  is a norm in most OSS communities; ignoring it has burned contributors.
- Do not commit the `contribution-package/` directory to the target
  repo. It's a local artifact for you, not a contribution.
