# AI-Native Workflow Templates

Opinionated, reusable templates and patterns for running AI coding agents at scale — focused on spec-kitty missions, multi-agent orchestration, prompt-cache discipline, and review-loop patterns. Each template is self-contained, documented, and ships with a runnable example you can copy into your own repo and adapt.

## Catalog

Eight templates, grouped by what they do.

### Mission templates (spec-kitty workflows)

| Template | What it does |
|---|---|
| [`templates/spec-kitty-mission-pr-triage`](templates/spec-kitty-mission-pr-triage/) | Triage open PRs in a public OSS repo; produce a prioritized review queue and AI-drafted reviewer comments. Local-only, never posts. Worked example against [anomalyco/opencode](https://github.com/anomalyco/opencode). |
| [`templates/scout-then-act-mission`](templates/scout-then-act-mission/) | Two-agent pattern: a read-only scout researches first, then a separate actor performs the change from the scout's structured findings. Reduces premature writing on unfamiliar codebases. |
| [`templates/oss-pr-prep-checklist`](templates/oss-pr-prep-checklist/) | Turns "I want to contribute to OSS repo X" into a contribution package: distilled guidelines, filtered good-first-issues, draft PR description, files-likely-to-change. Worked example against [cline/cline](https://github.com/cline/cline). |

### Orchestration patterns

| Template | What it does |
|---|---|
| [`templates/multi-agent-implement-review-loop`](templates/multi-agent-implement-review-loop/) | Parallel implement-review with arbiter escalation. Implementer and reviewer are different agents; an arbiter rules when they cannot converge in K rounds, otherwise defers to a human. |

### Agent profiles

| Template | What it does |
|---|---|
| [`templates/agent-profile-conservative-implementer`](templates/agent-profile-conservative-implementer/) | Drop-in profile that codifies smallest-diff, no-surprise-refactor behavior. Includes a side-by-side comparison vs an aggressive profile. |

### Prompt engineering

| Template | What it does |
|---|---|
| [`templates/prompt-cache-discipline-system-prompt`](templates/prompt-cache-discipline-system-prompt/) | System-prompt template plus the principles (stable prefix, append-only history, cache-aware tool definitions) that get high prompt-cache hit rates on long-running missions. Includes a cost-per-MTok reference table. |

### Tooling

| Template | What it does |
|---|---|
| [`templates/opencode-plugin-pre-commit-guardrail`](templates/opencode-plugin-pre-commit-guardrail/) | Opencode plugin pattern that injects a pre-commit guardrail before any agent-suggested git commit — blocks secrets, oversized diffs, forbidden file extensions. Ships with a runnable end-to-end test. |
| [`templates/llm-eval-harness-minimal`](templates/llm-eval-harness-minimal/) | ~150-line Python eval harness: YAML manifest of test cases, a runner, a markdown report. The first eval harness in a project, before you graduate to a heavier framework. |

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
