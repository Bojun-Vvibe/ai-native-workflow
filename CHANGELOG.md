# Changelog

All notable changes to this repository are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## 0.2.0 — 2026-04-23 — Five new templates; worked examples for the seed three.

### Added — new templates

- `templates/multi-agent-implement-review-loop/` — parallel implement-review pattern with arbiter escalation. README, mission YAML, three role prompts (implementer / reviewer / arbiter), and a sample end-to-end loop transcript.
- `templates/prompt-cache-discipline-system-prompt/` — system-prompt template encoding stable-prefix / append-only / cache-aware-tools discipline, plus a per-MTok pricing reference and a worked savings example.
- `templates/scout-then-act-mission/` — two-agent pattern: read-only scout produces a structured findings report, then a separate actor performs the change. Includes mission YAML, both role prompts, and a sample run on a representative bug-hunt task.
- `templates/oss-pr-prep-checklist/` — mission template that produces a contribution package for a target OSS repo (guidelines summary, filtered issues, draft PR description, files-likely-to-change). Worked example targets [cline/cline](https://github.com/cline/cline).
- `templates/llm-eval-harness-minimal/` — ~150-line Python eval harness (YAML manifest + runner + markdown report). Five sample test cases for a "summarize a code change" task. Sample report included.

### Added — worked examples for the seed templates

- `templates/spec-kitty-mission-pr-triage/examples/` — full worked example against [anomalyco/opencode](https://github.com/anomalyco/opencode): mission inputs, transcript, three drafted reviews of real recent open PRs (clearly marked DRAFT — not posted), and the aggregated `_queue.md`.
- `templates/agent-profile-conservative-implementer/examples/` — synthetic-but-realistic transcript showing the profile preventing a 600-line drive-by refactor on a feature-flag request, plus a `compare.md` contrasting outputs from this profile vs an aggressive profile on the same task.
- `templates/opencode-plugin-pre-commit-guardrail/examples/` — runnable end-to-end test (`test-guardrail.sh`) that asserts the guardrail blocks a fake-leaky commit, plus an `integration-with-opencode.md` for wiring into opencode's plugin system.

### Changed

- `templates/opencode-plugin-pre-commit-guardrail/plugin.example.js` — added an OpenAI-style `sk-` API-key pattern to `SECRET_PATTERNS`.
- `README.md` — catalog reorganized into five groups: mission templates, orchestration patterns, agent profiles, prompt engineering, tooling.
- `docs/ROADMAP.md` — v0.2 deliverables marked done; v0.3 scope sketched.

## 0.1.0 — 2026-04-23 — Initial release; 3 seed templates.

- `templates/spec-kitty-mission-pr-triage/` — spec-kitty mission for triaging open PRs in a public OSS repo, drafting reviewer comments to local files only.
- `templates/agent-profile-conservative-implementer/` — drop-in agent profile codifying small-diff, no-surprise-refactor behavior.
- `templates/opencode-plugin-pre-commit-guardrail/` — opencode plugin pattern that blocks agent-suggested commits containing secrets, oversized diffs, or forbidden file extensions.
- `docs/PHILOSOPHY.md`, `docs/ROADMAP.md`, `CONTRIBUTING.md`, `LICENSE` (MIT + CC-BY-4.0).
