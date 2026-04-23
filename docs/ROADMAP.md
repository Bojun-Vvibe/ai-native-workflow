# Roadmap

## v0.1 — Initial release

Three seed templates establishing the core shape:

- `templates/spec-kitty-mission-pr-triage/` — mission template, local-draft-only PR triage.
- `templates/agent-profile-conservative-implementer/` — drop-in agent profile.
- `templates/opencode-plugin-pre-commit-guardrail/` — plugin pattern for deterministic pre-commit checks.

## v0.2 — Orchestration patterns

Multi-agent coordination templates:

- Parallel implement-review pattern (N implementers, 1 reviewer, with backpressure).
- Arbiter escalation pattern (when implementer and reviewer disagree N times, a third "arbiter" agent decides — with explicit human override).
- Dependency-aware WP sequencing template (DAG-driven, not list-driven).

## v0.3 — Prompt-cache discipline

Templates that codify cache-friendly prompt construction:

- Stable-prefix pattern for long-running missions.
- Cache-warming pre-flight template.
- Cost-accounting wrapper template (per-WP token + dollar attribution).

## v0.4 — Cross-tool patterns

Templates for handing off work between different agent toolchains:

- claude-code ↔ opencode handoff template (shared state via filesystem contracts).
- spec-kitty mission ↔ external CI handoff template (mission produces machine-readable artifacts a CI workflow consumes).
- LiteLLM-routed multi-model template (different WPs targeting different models for cost/quality tradeoffs).

---

Versions are aspirational, not committed. Templates ship when they're useful, not when a milestone says so.
