# Worked example: triaging anomalyco/opencode

This directory contains a worked example of the PR-triage mission run against a real public OSS repo: [anomalyco/opencode](https://github.com/anomalyco/opencode).

## What's in here

- `mission-inputs.yaml` — the exact inputs used for this example run.
- `transcript.md` — a representative runtime transcript of the mission. The actual token-by-token output is paraphrased; the structural shape (phase boundaries, gates, WP outcomes) reflects what a real spec-kitty run produces.
- `reviews/PR-23965.md`, `reviews/PR-23927.md`, `reviews/PR-23910.md` — three drafted reviews of real recent open PRs in anomalyco/opencode.
- `reviews/_queue.md` — the priority-sorted index produced by the aggregation step.

## Important: drafts are NOT posted

Every drafted review is marked at the top with:

```
<!-- DRAFT — not posted to upstream -->
```

These are local artifacts only. The mission template explicitly forbids the agent from calling the GitHub API in write mode. To act on a draft, a human reviewer reads it, edits if needed, and posts manually.

## Reproducing this example

The transcript and drafts are checked into the repo for reference. To reproduce against the live repo state (which will have moved on):

1. Copy `mission-inputs.yaml` over the inputs section of the parent template's `mission.example.yaml`.
2. Run the mission via your spec-kitty CLI.
3. Compare your output to the drafts here. Differences are expected — the underlying PRs change, the model version changes, and the maintainer voice tuning is project-specific.

## Why these three PRs

Out of roughly 20 open PRs at the time of capture, these three were chosen to illustrate three different shapes of triage output:

- **PR #23965** — small, well-scoped feature. The drafted review is short and recommends approve-with-questions.
- **PR #23927** — small bugfix touching a hot code path (provider integration). The drafted review focuses on regression risk and asks for a test.
- **PR #23910** — documentation-heavy change with a large file count. The drafted review focuses on cross-file consistency and recommends a comment-only review.

The intent is to show the template handles different PR shapes without producing same-shaped output.
