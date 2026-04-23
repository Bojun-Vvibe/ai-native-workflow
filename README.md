# AI-Native Workflow Templates

Opinionated, reusable templates and patterns for running AI coding agents at scale — focused on spec-kitty missions, multi-agent orchestration, prompt-cache discipline, and review-loop patterns. Each template is self-contained, documented, and ships with a runnable example you can copy into your own repo and adapt.

## Catalog

| Template | What it does |
|---|---|
| [`templates/spec-kitty-mission-pr-triage`](templates/spec-kitty-mission-pr-triage/) | Triage open PRs in a public OSS repo via a spec-kitty mission; produce a prioritized review queue and AI-drafted reviewer comments (local-only, never posts). |
| [`templates/agent-profile-conservative-implementer`](templates/agent-profile-conservative-implementer/) | A drop-in agent profile for spec-kitty / opencode / claude-code that codifies "conservative implementer" behavior — small diffs, explicit assumptions, no surprise refactors. |
| [`templates/opencode-plugin-pre-commit-guardrail`](templates/opencode-plugin-pre-commit-guardrail/) | An opencode plugin pattern that injects a pre-commit guardrail check before any agent-suggested git commit, blocking commits with secrets, oversized diffs, or forbidden file extensions. |

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
