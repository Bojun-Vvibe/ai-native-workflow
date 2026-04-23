# AI-Native Workflow Templates

Opinionated, reusable templates and patterns for running AI coding agents at scale — focused on spec-kitty missions, multi-agent orchestration, prompt-cache discipline, and review-loop patterns. Each template is self-contained, documented, and ships with a runnable example you can copy into your own repo and adapt.

## Catalog

Twenty-seven templates, grouped by what they do.

### Mission templates (spec-kitty workflows)

| Template | What it does |
|---|---|
| [`templates/spec-kitty-mission-pr-triage`](templates/spec-kitty-mission-pr-triage/) | Triage open PRs in a public OSS repo; produce a prioritized review queue and AI-drafted reviewer comments. Local-only, never posts. Worked example against [anomalyco/opencode](https://github.com/anomalyco/opencode). |
| [`templates/scout-then-act-mission`](templates/scout-then-act-mission/) | Two-agent pattern: a read-only scout researches first, then a separate actor performs the change from the scout's structured findings. Reduces premature writing on unfamiliar codebases. |
| [`templates/oss-pr-prep-checklist`](templates/oss-pr-prep-checklist/) | Turns "I want to contribute to OSS repo X" into a contribution package: distilled guidelines, filtered good-first-issues, draft PR description, files-likely-to-change. Worked example against [cline/cline](https://github.com/cline/cline). |
| [`templates/parallel-dispatch-mission`](templates/parallel-dispatch-mission/) | Mission shape for fanning N independent investigations to N agents in parallel, with a join step that aggregates structured per-worker outputs. Worked example dispatches 5 concurrent OSS repo audits. |
| [`templates/oss-pr-review-template`](templates/oss-pr-review-template/) | Reusable structure for writing a high-signal OSS PR review (verdict, summary, line-anchored notes, follow-up questions). Two complete sample reviews against real public PRs. |
| [`templates/pr-review-four-question-checklist`](templates/pr-review-four-question-checklist/) | Four structural questions to run against any glue-code diff (early-return loop, wrong-sync event, default-passthrough translator, drifted second constructor). Includes a `CHECKLIST.md`, an LLM prompt, a wrapper script, and three worked examples (one per question). The 5-minute counterpart to the long-form review template. |
| [`templates/daily-oss-digest`](templates/daily-oss-digest/) | Daily digest workflow: per-repo "what changed yesterday" summaries plus a top-level INDEX. Mission YAML, per-repo template, and a fully populated sample digest day. |

### Orchestration patterns

| Template | What it does |
|---|---|
| [`templates/multi-agent-implement-review-loop`](templates/multi-agent-implement-review-loop/) | Parallel implement-review with arbiter escalation. Implementer and reviewer are different agents; an arbiter rules when they cannot converge in K rounds, otherwise defers to a human. |
| [`templates/sub-agent-context-isolation`](templates/sub-agent-context-isolation/) | Pattern + prompts for delegating exploratory work to sub-agents whose intermediate context never enters the parent's window. Side-by-side example shows compounding cache-hit-rate and latency benefit across a multi-investigation mission. |
| [`templates/agent-handoff-protocol`](templates/agent-handoff-protocol/) | Typed worker → orchestrator state contract: `done`/`partial`/`unrecoverable` envelope + canonical orchestrator routing table. Includes JSON Schema, three example handoffs, and an end-to-end orchestrator trace. |
| [`templates/agent-output-validation`](templates/agent-output-validation/) | Schema-checking layer for sub-agent JSON outputs. Three policies (`reject`, `repair_once`, `quarantine`) plus a one-shot repair prompt. Includes runnable fixtures (good / malformed / drifted). |
| [`templates/multi-repo-monorepo-bridge`](templates/multi-repo-monorepo-bridge/) | Treats N independent repos as one logical workspace via a symlinked bridge directory + manifest. `bridge-search` and `bridge-git` helpers; cross-repo rename walkthrough. |

### Agent profiles

| Template | What it does |
|---|---|
| [`templates/agent-profile-conservative-implementer`](templates/agent-profile-conservative-implementer/) | Drop-in profile that codifies smallest-diff, no-surprise-refactor behavior. Includes a side-by-side comparison vs an aggressive profile. |

### Prompt engineering

| Template | What it does |
|---|---|
| [`templates/prompt-cache-discipline-system-prompt`](templates/prompt-cache-discipline-system-prompt/) | System-prompt template plus the principles (stable prefix, append-only history, cache-aware tool definitions) that get high prompt-cache hit rates on long-running missions. Includes a cost-per-MTok reference table. |
| [`templates/cache-aware-prompt`](templates/cache-aware-prompt/) | Per-request, SDK-tactical companion to the discipline template. Provider-specific snippets (Anthropic, OpenAI, Gemini) for marking cache breakpoints, plus a measurement script that proves the hit rate. |
| [`templates/prompt-fingerprinting`](templates/prompt-fingerprinting/) | Deterministic fingerprint of every prompt package (system + tools + decoding + convo prefix). Diff two fingerprints to see what drifted; emits both `cache_hash` and `semantic_hash` to distinguish silent cache breaks from intentional changes. |

### Tooling

| Template | What it does |
|---|---|
| [`templates/opencode-plugin-pre-commit-guardrail`](templates/opencode-plugin-pre-commit-guardrail/) | Opencode plugin pattern that injects a pre-commit guardrail before any agent-suggested git commit — blocks secrets, oversized diffs, forbidden file extensions. Ships with a runnable end-to-end test. |
| [`templates/guardrail-pre-push`](templates/guardrail-pre-push/) | Repo-local `pre-push` git hook that blocks pushes containing secrets, internal-string blacklist matches, oversized blobs, or attack-payload references. Includes a 7-case test harness. |
| [`templates/llm-eval-harness-minimal`](templates/llm-eval-harness-minimal/) | ~150-line Python eval harness: YAML manifest of test cases, a runner, a markdown report. The first eval harness in a project, before you graduate to a heavier framework. |
| [`templates/token-budget-tracker`](templates/token-budget-tracker/) | Stdlib-only Python module + JSONL log + CLI report for tracking agent token usage by model, phase, tool, and cache bucket. Cost computed at report time from a pinnable `prices.json` so old logs re-cost when prices change. |
| [`templates/token-budget-launchd`](templates/token-budget-launchd/) | macOS `LaunchAgent` plist + wrapper script that runs your daily token-budget report at a fixed time, writes markdown to `~/Reports/`, and rotates files older than 90 days. |
| [`templates/anomaly-alert-cron`](templates/anomaly-alert-cron/) | Daily anomaly + budget check on a `LaunchAgent`, with per-day deduplication, a tiny audit log, and pluggable notifiers (macOS banner, webhook). Composes with `pew anomalies` / `pew budget --check`. |
| [`templates/commit-message-trailer-pattern`](templates/commit-message-trailer-pattern/) | Discipline + tooling for machine-readable commit trailers (`Co-Authored-By`, `Mission-Id`, `Model`, `Tokens-In`, `Tokens-Out`, `Cache-Hit-Rate`). `commit-msg` hook validates the key allow-list. |
| [`templates/oss-fork-hygiene`](templates/oss-fork-hygiene/) | Convention + scripts for managing OSS forks safely: standard remote layout, `audit-forks.sh`, `sync-fork.sh`, `new-topic.sh`, and a keep/archive/delete decision rubric. |

### Methodology

| Template | What it does |
|---|---|
| [`templates/reverse-engineer-cli`](templates/reverse-engineer-cli/) | Five-pass methodology for producing a behavior spec of an undocumented CLI without source access. Includes per-command probe checklist, spec template, an excerpt from the real `pew-insights` spec, and a 90-minute methodology trace. |
| [`templates/metric-baseline-rolling-window`](templates/metric-baseline-rolling-window/) | Methodology + stdlib-only Python reference for "is today's number weird?" against a rolling baseline. Three scorers (z-score, MAD, EWMA) plus a zero-aware variant for count metrics. 21-test unittest suite, decision rubric, seasonal-baseline extension, three worked examples showing where each scorer wins. |
| [`templates/failure-mode-catalog`](templates/failure-mode-catalog/) | Taxonomized catalog of 12 common LLM-agent failure modes (Context Rot, Premature Convergence, Schema Drift, …) with severity, observable symptoms, mitigations linked to other templates, and a triage walkthrough. |

## How to use a template

1. Browse the catalog above and open the template directory.
2. Read its `README.md` end-to-end — every template includes a "When to use" / "When NOT to use" section.
3. Copy the directory contents into your own repo (or fork this repo).
4. Find the **Adapt this section** block in the template README and edit the listed variables for your project.
5. Run the worked example. Each template ships with one.

## License

Dual-licensed:

- **Code, configs, plugins, mission YAML, profile YAML** — [MIT](LICENSE)
- **Documentation, READMEs, prose** — [CC-BY-4.0](LICENSE)

See [`LICENSE`](LICENSE) for the full text.

## Contributing

PRs welcome for new templates. Rules:

- **One template per PR.** Keeps review tractable.
- Must include a working example (runnable or copy-pasteable).
- Must include a README following the structure in [`CONTRIBUTING.md`](CONTRIBUTING.md).
- No employer-specific names, internal codenames, or private endpoints. Templates must be portable to any project.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full checklist and [`docs/PHILOSOPHY.md`](docs/PHILOSOPHY.md) for the stance behind these templates.
