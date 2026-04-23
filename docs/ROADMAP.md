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

## v0.3 — Eight new templates (shipped)

Done:

- [x] `templates/parallel-dispatch-mission/`
- [x] `templates/cache-aware-prompt/`
- [x] `templates/guardrail-pre-push/`
- [x] `templates/oss-pr-review-template/`
- [x] `templates/daily-oss-digest/`
- [x] `templates/token-budget-tracker/`
- [x] `templates/sub-agent-context-isolation/`
- [x] `templates/reverse-engineer-cli/`

The cost / routing / DAG ideas originally sketched in this slot
were re-scoped — `token-budget-tracker` covered the cost-accounting
need; routing and DAG sequencing are deferred to a future milestone
when there's a real mission demanding them.

## v0.4 — Validation, attribution, observability, multi-repo, taxonomy (shipped)

Eight new templates landed in 0.4. Theme: making agent operations
**queryable** — every commit, every prompt, every handoff, every
fork, every failure has a name and a record.

- [x] `templates/agent-output-validation/` — schema-checking sub-agent outputs.
- [x] `templates/commit-message-trailer-pattern/` — `Co-Authored-By` + token-budget trailers.
- [x] `templates/token-budget-launchd/` — daily budget reports via macOS launchd.
- [x] `templates/oss-fork-hygiene/` — managing forks safely (audit, sync, decision rubric).
- [x] `templates/prompt-fingerprinting/` — detect prompt drift across runs.
- [x] `templates/multi-repo-monorepo-bridge/` — N repos as one logical workspace.
- [x] `templates/agent-handoff-protocol/` — typed worker → orchestrator state contracts.
- [x] `templates/failure-mode-catalog/` — taxonomized failure modes for LLM agents with mitigations.

## v0.4.1 — Anomaly alerting + baseline math (shipped)

Two paired templates extending the observability work from 0.4.
Theme: a metric being **abnormal** is half the work; getting it
to a human at the right moment with the right signal-to-noise is
the other half.

- [x] `templates/anomaly-alert-cron/` — daily anomaly+budget check on a macOS LaunchAgent with per-day dedup, audit log, and pluggable notifiers.
- [x] `templates/metric-baseline-rolling-window/` — stdlib-only Python reference for z-score / MAD / EWMA scorers, with a zero-aware variant for count metrics. 21-test unittest suite. Decision rubric for picking the right scorer per metric.

## v0.5 — Cross-tool & routing (sketch)

Tentative scope; aspirational, not committed.

- Cross-toolchain handoff template (shared state via filesystem contracts).
- Mission ↔ external CI handoff template (mission produces machine-readable artifacts a CI workflow consumes).
- Multi-model routing template (different WP classes targeting different models for cost/quality tradeoffs).
- Dependency-aware WP sequencing (DAG-driven), deferred from v0.2.

---

Versions are aspirational, not committed. Templates ship when they're useful, not when a milestone says so.
