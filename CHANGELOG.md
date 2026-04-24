# Changelog

All notable changes to this repository are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## 0.4.10 — 2026-04-24 — One new template: canonical (class, retryability, attribution) classifier for raw error records.

### Added — new template

- `templates/structured-error-taxonomy/` — pure first-match-wins classifier that turns a raw error record (`source`, `vendor_code`, `http_status`, `message`) into a canonical `(class, retryability, attribution)` triple drawn from a small stable enum, so retry / circuit-breaker / fallback-ladder / cost layers all branch on the same `class` instead of fragile vendor-message substring matching. `CLASSES` covers the eleven classes downstream templates already implicitly switch on (`rate_limited`, `content_filter`, `auth`, `quota_exhausted`, `context_length`, `tool_timeout`, `tool_unavailable`, `tool_bad_input`, `host_io`, `transient_network`, `unknown`); `RETRYABILITY` and `ATTRIBUTION` are the two orthogonal axes the classifier preserves so the retry envelope and the circuit breaker can stay decoupled. Stdlib-only `bin/classify_error.py` reads JSONL, emits one verdict per line with the `matched_rule` id so triage can audit the rule that fired; CLI exits 0 when every input matched a non-default rule, 1 if any input fell through to the catch-all `unknown` (so a CI gate / triage cron can surface new vendor codes), 2 on malformed input. `SPEC.md` pins the three enums and the rule-evaluation contract (top-to-bottom, first match wins, deterministic catch-all, no side effects). `prompts/add_rule.md` is a strict-JSON prompt for proposing new rules from clusters of `default`-matched records; rule must place above the catch-all and conservative `retryability`. Two worked examples — `01-classify-clean-batch` (six records covering `rate_limited` via 429, `content_filter` via vendor code, `tool_timeout`, `host_io`, `auth`, `context_length`) all match named rules and exit 0, and `02-detect-unknown-class` (3 records, one with an unknown `weird_new_provider_code`) returns three correct verdicts including `class=unknown, matched_rule=default, retryability=do_not_retry` and exits 1 — both with paired `output.jsonl` and `exit.txt`. Composes with `model-fallback-ladder` (`class` is its `skip_on_reason_classes` value), `tool-call-retry-envelope` (`retryability` is its `retry_class_hint`), `tool-call-circuit-breaker` (only `attribution=tool` failures count toward a tool's failure rate), and `agent-cost-budget-envelope` (`quota_exhausted` means degrade, don't climb).

### Changed

- `README.md` — catalog grew from 40 to 41 templates; added the `structured-error-taxonomy` entry under Orchestration patterns, after `model-fallback-ladder`, with cross-references to all four runtime-control templates that consume its enums.

## 0.4.9 — 2026-04-24 — One new template: per-call/session/day cost cap envelope with degrade tiers and kill switch.

### Added — new template

- `templates/agent-cost-budget-envelope/` — small envelope that wraps every model call with three hard caps (`per_call`, `per_session`, `per_day`) plus a graceful-degrade tier the caller can opt into and a kill switch for the case where degrade is not safe. Stdlib-only reference: `bin/budget_envelope.py` (`Request`, `Decision`, `Ledger`, `check()` + `record()` with deterministic evaluation order — kill switch first, then projection, then per-call → per-session → per-day, each cap's `on_trip` either `degrade` (re-projects at `degrade_to` tier) or `kill` (deny)), JSONL ledger backend with session and day rollups, `bin/policy_lint.py` (validates `default` tier exists, every `degrade_to` resolves, `per_day >= per_session >= per_call`, kill switch ≥ 0), `prompts/degrade-explainer.md` (strict-JSON prompt that turns a `Decision(decision=allow_degraded, reason=…)` into a one-paragraph user-facing explanation), `ENVELOPE.md` (policy schema + request/decision shapes + `reason` code table + ledger schema + anti-patterns including "do not catch BudgetExceeded and retry"), and two worked examples that all run end-to-end with the documented stdout and ledger state — `01-per-call-cap-trips-degrade` (100k/4k tokens at default = $0.36 > $0.20 cap → re-projected at cheap tier = $0.056, allow_degraded with reason carried into the ledger row so reports can distinguish "ran cheap because it was correct" from "ran cheap because cap forced it") and `02-session-cap-trips-killswitch` (5 prior calls totalling $1.92, 6th call projected $0.18 → 1.92 + 0.18 = $2.10 > $2.00 → deny with headroom_usd 0.08; 7th call also denies with same reason; ledger never appended on deny because denies are caller-side exceptions not spend). Companion to `token-budget-tracker` (post-hoc reporting) and `alert-noise-budget` (alert-rate budgeting); the per-call/session pre-flight that those two presume already exists.

### Changed

- `README.md` — catalog grew from 33 to 34 templates; added the `agent-cost-budget-envelope` entry under Orchestration patterns, after `structured-output-repair-loop`. Cross-references `token-budget-tracker` (writes the same JSONL row shape so a single tracker can read both), `tool-call-retry-envelope` (a retry of a degraded call replays the degraded result rather than re-promoting tier — `idempotency_key` is not recomputed), `alert-noise-budget` (shared budget/trip/back-off vocabulary, different resource), and `failure-mode-catalog` (operational fix for "Runaway Session" and "Slow-Drip Daily Spend").

## 0.4.8 — 2026-04-24 — One new template: allowlist-driven trace redaction with pointer-anchored rules.

### Added — new template

- `templates/agent-trace-redaction-rules/` — deterministic, allowlist-driven rule engine for redacting agent traces, tool-call logs, and curated datasets before they leave the agent's trust boundary. Rules say *what is allowed to escape* (by RFC 6901 JSON pointer + value class), not what to block — anything not in the allowlist becomes `[REDACTED:not_in_allowlist]`; values that match a rule but fail the value class become `[REDACTED:value_class_mismatch]`. Value classes: `int`, `float`, `bool`, `string_short` (≤64 chars, no whitespace runs), `string_enum:A|B|C`, `iso8601`, `sha256`, `passthrough`. Stdlib-only reference: `bin/redact.py` (loads rules, walks document top-down depth-first, emits redacted copy + JSONL report, `--strict` flag exits 2 on any redaction for CI gating), `bin/check_rules.py` (lints duplicates, root-passthrough disablement, wildcard-leaf-with-passthrough over-permissiveness, missing reasons), `prompts/rule-author.md` (strict-JSON prompt that proposes new rules from a sample trace; never proposes rules for fields named `email`/`phone`/`name`/`secret`/etc — those go to `needs_human_review`), `RULES.md` (pointer syntax with single-segment `*` wildcard, value class table, sentinel format guarantees, walk semantics), and two worked examples that all run end-to-end with the documented stdout, output.json, report.jsonl, and exit code — `01-allowlist-blocks-leak` (tool-call envelope with four allowed fields plus an unlisted `internal_note` → 1 redaction) and `02-nested-fields-with-pointer` (dataset record with `meta.cost.{tokens_in, tokens_out, user_id}` and three messages, allowlist via pointer-anchored rules → `user_id` redacted as `not_in_allowlist`, off-enum `role: "tool"` redacted as `value_class_mismatch`, exit 2 under `--strict`). The trace/dataset-export counterpart to `tool-call-retry-envelope`'s `IDENTITY_FIELDS` allowlist; both templates fail closed.

### Changed

- `README.md` — catalog grew from 32 to 33 templates; added the `agent-trace-redaction-rules` entry under Tooling, after `anomaly-alert-cron`. Cross-references `tool-call-retry-envelope` (shares the allowlist-shape pattern), `agent-output-validation` (validates *before* the agent acts; this runs *after*, on the trail), `prompt-fingerprinting` (the `cache_hash` and `semantic_hash` fields are typically allowlisted at `passthrough` in trace exports because they are by construction non-identifying), and `failure-mode-catalog` (operational fix for "Trace Leak" and "Dataset Poisoning by Tool Output").

## 0.4.7 — 2026-04-24 — One new template: prompt regression snapshots with three-state verdict and CI gate.

### Added — new template

- `templates/prompt-regression-snapshot/` — snapshot-test pattern for prompts: when you tweak a system prompt, an agent profile, or a tool-call schema, you want to know **exactly which existing eval cases changed output** — and whether each change is intentional or a silent regression. Companion to `llm-eval-harness-minimal` (which scores quality); this one tracks change. Stdlib-only reference: `bin/snapshot.py` (subcommands `run`, `diff`, `approve`, `rebless`) with three-state verdict (`MATCH` / `CHANGED` / `NEW` / `MISSING`), per-format canonicalisation (JSON: sort_keys + tight separators; prose: line-by-line equality after rstrip), `--strict` flag for CI gating, `--write-new` for bootstrap, and a `rebless` subcommand that bumps `prompt_sha` on MATCH cases without touching output (so a prompt change that produces unchanged output doesn't require explicit human approval); `bin/approve.py` thin convenience wrapper; `SNAPSHOTS.md` (snapshot file schema, three-state verdict table, approval workflow, what snapshots do NOT replace — eval rubrics, live monitoring, schema validation); and two worked examples that all run end-to-end against a deterministic mock model — `01-clean-diff` (v1→v2 prompt change that affects only whitespace and key order; 3/3 MATCH; exit 0) and `02-flagged-regression` (v1→v2 prompt change that rewords one summary; 2/3 MATCH + 1 CHANGED with full unified diff in the report; exit 1; reviewer-decision walkthrough showing the approve-vs-rollback branches).

### Changed

- `README.md` — catalog grew from 31 to 32 templates; added the `prompt-regression-snapshot` entry under Prompt engineering, after `prompt-fingerprinting`. Cross-references `llm-eval-harness-minimal` (same fixture format; snapshots catch change, eval harness catches quality), `prompt-fingerprinting` (feeds the `prompt_sha` field), `commit-message-trailer-pattern` (the `Snapshots-Updated:` trailer makes behavioural changes visible in PR review without re-running the harness), and `failure-mode-catalog` (silent-regression failure mode).

## 0.4.6 — 2026-04-24 — One new template: structured-output repair loop with stuck-detection.

### Added — new template

- `templates/structured-output-repair-loop/` — bounded repair loop for LLM calls that must return structured output (JSON, YAML, strict prose). Generalises the `repair_once` policy from `agent-output-validation` into a real loop with four exit states (`parsed`, `stuck`, `exhausted`, `expired`), per-attempt validator-error feedback rendered as a structured hint block (`json_pointer`, expected, got, suggested fix), error fingerprinting that collapses array-index noise (`/users/0/email` and `/users/1/email` → same fingerprint) so "same mistake twice" triggers early bail-out, hard caps via `max_attempts` and `deadline_ms`, and an explicit "reproduce all fields except" instruction in the repair-turn template that prevents the bounce-between-fingerprints failure mode. Stdlib-only reference implementation: `bin/repair_loop.py` (reference loop + mini schema validator + mock model), `bin/error_fingerprint.py` (canonical hash with self-test), `bin/render_hint.py` (validator error → repair hint block with per-error-class fix suggestions), `prompts/system.md` (system-prompt fragment that opts the model into the contract), `prompts/repair-turn.md` (user-turn template), `LOOP.md` (state machine, defaults, anti-patterns: no temperature manipulation, no system-prompt mutation, no backoff between attempts), and three worked examples that all run end-to-end against the mock model and produce the documented exit states — `01-typo-field` (camelCase `userId` → snake_case `user_id` fixed in one repair turn, `status=parsed, attempts=2`), `02-stuck-loop` (markdown ```json fences four times in a row → `status=stuck, attempts=2`, saving 2 wasted attempts vs naive loop), `03-degraded-fallback` (extra `notes` field with varying values across 4 attempts → loop bails on attempt 2 via fingerprint collapse, hands off to caller-side stripper for recovery).

### Changed

- `README.md` — catalog grew from 30 to 31 templates; added the `structured-output-repair-loop` entry under Orchestration patterns, after `tool-call-retry-envelope`. Cross-references `agent-output-validation` (the policy upgrade path), `tool-call-retry-envelope` (when structured output is a tool argument the dedup envelope guarantees side effects fire only on the validated final attempt), `failure-mode-catalog` (operational fix for Schema Drift and Premature Convergence), and `token-budget-tracker` (log each attempt with `phase=repair_loop` so reports surface loop-as-budget-hog missions).

## 0.4.5 — 2026-04-24 — One new template: tool-call retry envelope and host-side dedup contract.

### Added — new template

- `templates/tool-call-retry-envelope/` — wire-format and host-side dedup contract that makes agent tool calls safely retryable without re-executing side effects, and without each tool-host having to reverse-engineer "is this a retry?" from headers or timing. Operationalizes the morning post on host-derived semantic-hash idempotency keys as a concrete five-field envelope (`idempotency_key`, `attempt_number`, `max_attempts`, `deadline`, `retry_class_hint`) plus a five-state response envelope (`executed_now` / `replayed_from_cache` / `expired` / `rejected_max_attempts` / `rejected_key_collision`). Ships with `ENVELOPE.md` (the wire spec — required/optional/forbidden fields, key-derivation rule, version prefix discipline, backwards-compat with envelope-unaware tools), JSON Schemas for both request and response envelopes, a reference SQLite dedup-table SQL with the same-transaction guarantee that prevents the "row committed but dedup missed" failure mode, three stdlib-only Python tools (`bin/derive-key.py` with per-tool `IDENTITY_FIELDS` allowlist for `email.send`/`stripe.charges.create`/`git.push`/`db.execute`/`slack.send`; `bin/classify-retry.py` with deterministic decision tables for HTTP statuses, transport exceptions, and dedup-status responses; `bin/dedup-replay.py` deterministic simulator), a strict-JSON `prompts/retry-decision.md`, and four worked examples that all run end-to-end against the simulator and produce the documented outcomes — `01-network-blip` (SSE drop after side effect → attempt 2 replays cached charge ID, dedup table size 1), `02-host-crash-mid-call` (SIGKILL between DB commit and HTTP reply → post-restart retry replays cached row ID, table size 1), `03-agent-loop-retry` (model gives up waiting and recalls with same args → same key, replays original message ID, table size 1), `04-edited-payload-retry` (agent edits `to` from Alice to Bob → different `IDENTITY_FIELDS` → different key → both sends execute, table size 2 with both keys verified by sha256 of canonical JSON). Companion to the morning's `ai-native-notes` post on idempotency-key derivation; the operational counterpart to its derivation-strategy argument.

### Changed

- `README.md` — catalog grew from 29 to 30 templates; added the `tool-call-retry-envelope` entry under Orchestration patterns, after `multi-repo-monorepo-bridge`. Cross-references `agent-handoff-protocol` (the `done` envelope can carry `dedup_status`), `agent-output-validation` (validate envelope responses against `response.schema.json`), and `failure-mode-catalog` (the prevented modes — Phantom Effect and Edited-Payload Silent Dedup).

## 0.4.4 — 2026-04-24 — One new template: alert-noise budget calibration and OR-merge projection.

### Added — new template

- `templates/alert-noise-budget/` — methodology + stdlib-only Python reference for the missing third leg of the `metric-baseline-rolling-window` (math) + `anomaly-alert-cron` (scheduling) pair: how to set per-detector thresholds against a target alert rate (not a target z-score), how to project the OR-merged alert rate of N detectors sharing one channel before adding a new detector to it, and how to apply a two-strikes back-off rule to detectors that blow budget two consecutive windows running. Ships with `BUDGET.md` (the methodology — calibration windows, empirical-quantile thresholds, OR-merge inflation, two-strikes back-off, anti-patterns), `bin/calibrate.py` (translate metric history + budget → recommended threshold), `bin/merge-budget.py` (project naive-sum vs actual OR-merged rate + pairwise correlations of fire-day indicators), `bin/back-off.py` (walk a fire log week-by-week applying the two-strikes rule), `prompts/tune.md` (strict-JSON tuner that emits keep/retune/mute decisions), and three worked examples — single detector with weekly budget = 1 (28-day synthetic stationary metric), OR-merge of two correlated detectors (cache-hit ratio + token volume; r = +0.63; merged 4/28 vs naive sum 6/28), and frozen-baseline detector encountering a regime shift (mean drifts up, variance triples, two-strikes triggers mute + recalibrate). Companion to `pew-insights` 0.4.4 dashboard's OR-merge alerting model (`token-high OR ratio-high/low`).

### Changed

- `README.md` — catalog grew from 28 to 29 templates; added the `alert-noise-budget` entry under Methodology, between `metric-baseline-rolling-window` and `failure-mode-catalog`. Cross-references both adjacent entries plus `anomaly-alert-cron` (scheduling layer).

## 0.4.3 — 2026-04-24 — One new template: AI-CLI substrate selection decision rule.

### Added — new template

- `templates/agent-cli-substrate-selection/` — decision template for picking which AI-CLI substrate (pre-agency LLM CLI such as `llm`/`aichat` vs agent CLI such as `claude`/`codex`/`opencode`) fits a given task, *before* you start. Operationalizes the pre-agency-vs-agent taxonomy as a five-clause decision rule (file discovery → iterative refinement → one-shot transform → batch shape → default to pre-agency) with explicit tiebreakers for the two clause-collision cases. Ships with a `RUBRIC.md` (one diagnostic question per clause), a strict-JSON `prompts/classify.md` that takes a task description plus an installed-CLI inventory and emits a structured class+CLI+evidence recommendation, a `bin/classify.sh` wrapper that pipes a task through the prompt against any agent CLI (dry-run safe with no `AGENT_CMD` set), and three worked examples — one per non-default clause that fires (Clause 3 PR-summary one-shot, Clause 2 fix-failing-tests agent loop, Clause 4 200-email batch extraction). Companion to the morning's `ai-native-notes` synthesis post on pre-agency-vs-agent as a taxonomic split, and to the `ai-cli-zoo` 20-entry CLI inventory it draws on.

### Changed

- `README.md` — catalog grew from 27 to 28 templates; added the `agent-cli-substrate-selection` entry under Methodology, adjacent to `reverse-engineer-cli`.

## 0.4.2 — 2026-04-24 — One new template: structural four-question PR-review checklist.

### Added — new template

- `templates/pr-review-four-question-checklist/` — short, opinionated structural checklist for reviewing PRs against agent infrastructure (and other glue code: brokers, ETL pipelines, webhook fan-outs). Four questions, each tied to a recurring bug shape that produces a *missing* output rather than a wrong one: early-return loop, wrong-sync event, non-portable enum default-passthrough, drifted second constructor. Ships with a canonical `CHECKLIST.md`, an LLM agent prompt that emits per-question structured findings, a `bin/run-checklist.sh` wrapper that pipes a `git diff` into a configurable agent CLI (dry-run safe with no agent configured) and exits non-zero when any question fires at high risk, and three worked examples — one per applicable question — with synthetic-but-realistic diffs and the full structured finding the prompt would emit. Companion to the existing long-form `oss-pr-review-template` (this is the 5-minute triage; that is the 2–4 page synthesis); derived from the bug-shapes synthesis post in `ai-native-notes`.

### Changed

- `README.md` — catalog grew from 26 to 27 templates; added the `pr-review-four-question-checklist` entry under Mission templates, adjacent to `oss-pr-review-template`.

## 0.4.1 — 2026-04-24 — Two new templates: anomaly-alert scheduling and rolling-window baseline math.

### Added — new templates

- `templates/anomaly-alert-cron/` — daily anomaly + budget check on a macOS `LaunchAgent`, with per-day deduplication of repeated alerts, a tiny audit log, pluggable notifiers (`mac` via `osascript`, `webhook` via `curl`), and a webhook-file permission check that refuses world-readable credential files. Composes naturally with the `pew anomalies` / `pew budget --check` exit-code convention.
- `templates/metric-baseline-rolling-window/` — methodology + stdlib-only Python reference for "is today's number weird?" against a rolling baseline. Three scorers (`score_zscore`, `score_mad`, `score_ewma`) plus a zero-aware variant for count metrics that are often zero. 21-test `unittest` suite (all passing). Includes a decision rubric, a seasonal-baseline extension recipe for metrics with a weekly cycle, and three worked examples showing where each scorer wins (stationary → z-score; bursty with a baseline-internal spike → MAD; slowly drifting → EWMA).

### Changed

- `README.md` — catalog grew from 24 to 26 templates; added an `anomaly-alert-cron` entry under tooling and a `metric-baseline-rolling-window` entry under methodology.

## 0.4.0 — 2026-04-23 — Eight new templates: validation, attribution, scheduling, fork hygiene, fingerprinting, multi-repo, handoff contracts, failure taxonomy.

### Added — new templates

- `templates/agent-output-validation/` — schema-checking layer for sub-agent JSON outputs. Three policies (`reject`, `repair_once`, `quarantine`), one-shot repair prompt, runnable fixtures (good / malformed / drifted).
- `templates/commit-message-trailer-pattern/` — discipline + tooling for machine-readable commit trailers (`Co-Authored-By`, `Mission-Id`, `Model`, `Tokens-In`, `Tokens-Out`, `Cache-Hit-Rate`). Includes `commit-msg` validation hook and a CSV-emitting `parse-trailers.sh` for cost reports.
- `templates/token-budget-launchd/` — macOS `LaunchAgent` plist + wrapper script that runs the daily token-budget report at a fixed time, writes markdown to `~/Reports/`, and rotates files older than 90 days.
- `templates/oss-fork-hygiene/` — convention + scripts for managing OSS forks safely: standard remote layout, `audit-forks.sh` (flags STALE/DIVERGED/UNPROTECTED), `sync-fork.sh` (refuses to sync when `main` has diverged), `new-topic.sh`, and a keep/archive/delete decision rubric.
- `templates/prompt-fingerprinting/` — deterministic fingerprint of every prompt package (system + tools + decoding + convo prefix). Diff two fingerprints to see what drifted; emits both `cache_hash` and `semantic_hash` to distinguish silent cache breaks from intentional changes.
- `templates/multi-repo-monorepo-bridge/` — pattern for treating N independent repos as one logical workspace via a symlinked bridge directory + `MANIFEST.toml`. `bridge-search` (rg with shared ignores) and `bridge-git` (resolves the right child repo from a path) helpers; cross-repo identifier-rename walkthrough.
- `templates/agent-handoff-protocol/` — typed worker → orchestrator state contract: `done`/`partial`/`unrecoverable` envelope with `artifacts`, optional `continuation`, and `diagnostics`. Includes JSON Schema, canonical orchestrator routing table, three example handoffs, and an end-to-end orchestrator trace.
- `templates/failure-mode-catalog/` — taxonomized catalog of 12 common LLM-agent failure modes (Context Rot, Tool-call Storm, Schema Drift, Premature Convergence, Cache Prefix Thrash, Cross-repo Blindness, Stale Fork, Continuation Loop, Silent Retry Multiplication, Confident Fabrication, Lost Diff, Output-fence Mishandling) with severity, observable symptoms, mitigations linked to other templates, plus a three-case triage walkthrough and a log-symptoms grep reference.

### Changed

- `README.md` — catalog grew from 16 to 24 templates; added orchestration entries for handoff/validation/bridge, a new fingerprinting prompt-engineering entry, three new tooling entries (launchd, trailers, fork hygiene), and a methodology entry for the failure-mode catalog.

## 0.3.0 — 2026-04-23 — Eight new templates: parallelism, OSS workflows, guardrails, observability, and methodology.

### Added — new templates

- `templates/parallel-dispatch-mission/` — mission shape for fanning N independent investigations to N agents in parallel, with a join step. Worked example dispatches 5 concurrent OSS repo audits.
- `templates/cache-aware-prompt/` — per-request, SDK-tactical companion to the prompt-cache discipline template. Anthropic / OpenAI / Gemini snippets for cache breakpoints + a measurement script.
- `templates/guardrail-pre-push/` — repo-local `pre-push` git hook blocking secrets, internal-string blacklist matches, oversized blobs, and attack-payload references. Includes a 7-case test harness (all passing).
- `templates/oss-pr-review-template/` — reusable structure for high-signal OSS PR reviews. Two complete sample reviews against real public PRs.
- `templates/daily-oss-digest/` — daily digest workflow with mission YAML, per-repo template, and a fully populated sample digest day.
- `templates/token-budget-tracker/` — stdlib-only Python module + JSONL log + CLI report for tracking agent token usage by model / phase / tool / cache bucket. Cost computed at report time from a pinnable `prices.json`.
- `templates/sub-agent-context-isolation/` — pattern + prompts for delegating exploratory work to sub-agents whose context never enters the parent's window. Worked example shows a 14k-token investigation collapsing to a 280-token answer in the parent context.
- `templates/reverse-engineer-cli/` — five-pass methodology for producing a behavior spec of an undocumented CLI. Per-command probe checklist, spec template, an excerpt from the real `pew-insights` spec, and a 90-minute methodology trace.

### Changed

- `README.md` — catalog grew from 8 to 16 templates; added a "Methodology" group.
- `.gitignore` — added `__pycache__/`.

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
