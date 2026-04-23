# Roadmap

## v0.1 — Initial release (shipped)

Three seed templates establishing the core shape:

- `templates/spec-kitty-mission-pr-triage/` — mission template, local-draft-only PR triage.
- `templates/agent-profile-conservative-implementer/` — drop-in agent profile.
- `templates/opencode-plugin-pre-commit-guardrail/` — plugin pattern for deterministic pre-commit checks.

## v0.2 — Orchestration patterns + worked examples (shipped)

Five new templates plus complete worked examples for the v0.1 three.

Done:

- [x] `templates/multi-agent-implement-review-loop/` — parallel implement-review with arbiter escalation.
- [x] `templates/scout-then-act-mission/` — read-only scout then actor pattern.
- [x] `templates/oss-pr-prep-checklist/` — OSS contribution prep mission.
- [x] `templates/prompt-cache-discipline-system-prompt/` — cache-aware system-prompt template.
- [x] `templates/llm-eval-harness-minimal/` — minimal eval harness pattern.
- [x] Worked examples for all three v0.1 templates (PR triage against anomalyco/opencode, conservative-implementer comparison, guardrail runnable test).

Originally scoped for v0.2 and not shipped (deferred to v0.3 or later):

- Dependency-aware WP sequencing template (DAG-driven). Deferred — needs more real-world DAG mission examples to be usefully opinionated.

## v0.3 — Cost & model-routing patterns (sketch)

Tentative scope; aspirational, not committed.

- `templates/cache-warming-preflight/` — pre-flight mission step that warms the prompt cache before the main mission begins, so the first WP is not the cache-miss WP.
- `templates/cost-accounting-wrapper/` — per-WP token + dollar attribution wrapper. Outputs a CSV the user can join against billing data.
- `templates/model-routing-by-wp-class/` — manifest pattern for routing different WP classes (research / implement / review / synthesis) to different models, with an explicit cost / quality table per class.
- `templates/dependency-aware-wp-sequencing/` — DAG-driven WP execution, deferred from v0.2.

## v0.4 — Cross-tool patterns (sketch)

Templates for handing off work between different agent toolchains:

- claude-code ↔ opencode handoff template (shared state via filesystem contracts).
- spec-kitty mission ↔ external CI handoff template (mission produces machine-readable artifacts a CI workflow consumes).
- LiteLLM-routed multi-model template (different WPs targeting different models for cost/quality tradeoffs).

---

Versions are aspirational, not committed. Templates ship when they're useful, not when a milestone says so.
