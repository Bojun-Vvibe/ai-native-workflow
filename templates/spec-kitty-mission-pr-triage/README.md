# Template: spec-kitty mission — PR triage

A spec-kitty mission template that triages open PRs in a public OSS repository, producing a prioritized review queue and AI-drafted reviewer comments — written to local files for human review.

## Purpose

Maintainers of fast-moving open-source repositories often have more open PRs than reviewer-hours. This template runs a structured spec-kitty mission that:

1. Pulls the open PR list for a target repo.
2. Classifies each PR by risk (touched paths, diff size, test coverage delta, author history).
3. Drafts a per-PR review note: summary, risk areas, suggested clarifying questions, and a recommended action (approve / request-changes / comment).
4. Writes one markdown file per PR to `reviews/PR-<n>.md`.

The maintainer then reads the queue in priority order and **manually** posts whichever drafts they endorse.

## When to use

- You maintain a public OSS repo with steady incoming PR volume.
- You want consistent triage hygiene without paying full attention-cost on every PR.
- You're comfortable with AI-drafted text as a *starting point* for review, not a substitute.

## When NOT to use

- Closed-source / proprietary code where you don't want LLM ingestion of your diffs. Use a local-only model setup instead.
- Repos where every PR already gets prompt human review — the overhead isn't worth it.
- Any workflow where you want the agent to actually post comments. **This template never does that.**

## Inputs

| Variable | Type | Description |
|---|---|---|
| `target_repo` | string | GitHub `owner/name`, e.g. `octocat/hello-world`. |
| `max_prs` | int | Cap on PRs to triage in one run. Recommended: 10–25. |
| `maintainer_handle` | string | GitHub handle of the human reviewer the drafts are addressed to. |

## Outputs

- `reviews/PR-<n>.md` — one file per PR. Each contains:
  - One-paragraph summary of the change
  - Risk areas (files touched, blast radius, test coverage delta)
  - Suggested clarifying questions for the author
  - Recommended action: `approve` / `request-changes` / `comment`
  - Confidence: `high` / `medium` / `low`
- `reviews/_queue.md` — index file listing all triaged PRs sorted by recommended priority.

## Steps (mission walk-through)

This template uses the standard spec-kitty four-phase loop. Only public artifacts are referenced.

### 1. `specify`
Author runs `spec-kitty specify` and provides the inputs above. The specify phase writes a brief charter scoping what "triage" means for this repo (e.g. which labels to skip, which paths require security-focused review).

### 2. `plan`
The architect agent (see `prompts/architect.md`) reads the charter and produces a plan: one work package (WP) per PR, plus a final aggregation WP that builds `_queue.md`.

### 3. `tasks`
The plan is decomposed into per-WP task lists. Each PR's WP has the same shape: fetch PR metadata → fetch diff → classify risk → draft review note → write file.

### 4. `implement-review-loop`
The reviewer agent (see `prompts/reviewer.md`) implements each WP. A second agent reviews each draft for tone, accuracy, and refusal-of-posting compliance. Rejected drafts re-enter the loop with feedback.

See [`mission.example.yaml`](mission.example.yaml) for a worked configuration.

## Adapt this section

Edit these to fit your repo:

- `target_repo` in `mission.example.yaml`
- `max_prs` in `mission.example.yaml`
- `maintainer_handle` in `mission.example.yaml` and in `prompts/reviewer.md`
- Path-based risk rules in `prompts/reviewer.md` (currently generic; add your hot paths)
- Skip-labels list in `mission.example.yaml` (e.g. `wip`, `do-not-merge`)

## Estimated token cost

Per PR, roughly:

- **Input**: 50K–200K tokens (PR diff + repo context + prompt + cached system context)
- **Output**: 20K–50K tokens (draft review + reasoning trace)

For a 20-PR run, budget ≈ 1M–5M input tokens and 400K–1M output tokens. Prompt cache reuse is critical — see `docs/PHILOSOPHY.md` in the repo root.

## Safety notes

- **This template only DRAFTS comments to local files. It NEVER posts to GitHub.** The reviewer agent prompt explicitly refuses any instruction to call the GitHub API in write mode.
- Submitting comments is a manual step. The human reviewer reads `reviews/PR-<n>.md`, edits if needed, and posts via their normal flow.
- If you fork this template and add posting capability, add an explicit per-PR human gate. Do not let an agent post unattended.
