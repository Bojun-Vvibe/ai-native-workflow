# Template: opencode plugin — Pre-Commit Guardrail

An opencode plugin pattern that intercepts agent-suggested git commits and runs a guardrail check before allowing them through. Blocks commits containing likely secrets, oversized diffs, or files with forbidden extensions.

## Purpose

Coding agents will, given enough sessions, eventually try to commit something they shouldn't: an `.env` file, a private key snippet pasted into a fixture, a 5000-line auto-generated lockfile diff, or a `node_modules/` directory. Most of these are caught by code review — but only if a human notices. This plugin adds a deterministic check at the moment the agent stages a commit, so the agent itself is told "no" before the commit lands.

## What it does

The plugin registers a hook on the "agent is about to run `git commit`" event. Before the commit is allowed, the plugin runs `git diff --staged` and applies a set of rules:

1. **Secret patterns** — regex match for common secret shapes (API keys, private key headers, AWS access key IDs, bearer tokens). Configurable.
2. **Diff size cap** — total added lines exceeds a threshold (default: 1000). Configurable.
3. **Forbidden extensions** — files matching extensions like `.env`, `.pem`, `.key`, `.p12`, `.mobileprovision` are never committed. Configurable.

If any rule trips, the plugin **blocks** the commit and returns a structured refusal to the agent, listing which rule(s) tripped. The agent then either fixes the staging area or asks the human.

The example implementation is in [`plugin.example.js`](plugin.example.js) — about 80 lines.

## When to use

- Any opencode workflow where an agent has shell access and might invoke `git commit`.
- Multi-agent setups where one agent stages files and another commits — race conditions make human review unreliable.
- Public repos where an accidentally-committed secret is an immediate incident.

## When NOT to use

- Workflows where the agent has no commit authority at all (you don't need a guardrail on a thing that can't happen).
- Repos where you've already configured server-side push protection (e.g. GitHub secret scanning push protection) AND the agent never works in a long-lived feature branch — the server-side check is sufficient.

## Adapt this section

Edit the constants at the top of `plugin.example.js`:

- `SECRET_PATTERNS` — add regexes for any project-specific secret shapes (custom token formats, internal endpoint signatures).
- `MAX_ADDED_LINES` — raise or lower the diff cap. 1000 is a sane default; large refactors will need a bypass mechanism (see below).
- `FORBIDDEN_EXTENSIONS` — add file extensions that should never be committed in your project.
- `BYPASS_ENV_VAR` — name of an env var that, when set to a specific value, allows a one-shot bypass (default: `GUARDRAIL_BYPASS=i-am-sure`). Use sparingly and document any bypass in the commit message.

### Extending the rule set

To add a new rule, follow the existing shape in `plugin.example.js`:

1. Define the rule as a function: `(diffText, stagedFiles) => { violated: bool, message: string }`.
2. Push it into the `RULES` array.
3. The hook iterates `RULES` and aggregates all violations into the refusal message.

This keeps each rule independent and testable.
