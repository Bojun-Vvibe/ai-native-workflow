# Example run — oss-pr-prep against cline/cline

Target: [cline/cline](https://github.com/cline/cline). The mission ran with
the default `label_filters` and the fit criteria as shipped in
`prompts/issue-filter.md`.

Outputs are paraphrased and trimmed; the structural shape mirrors what the
mission produces.

---

## Phase 1 — `read-guidelines` → `guidelines-summary.md`

Distilled from the live CONTRIBUTING and related docs:

```
## Project type and license
TypeScript-based VS Code extension that adds an autonomous coding agent
inside the editor. Apache-2.0 licensed.

## How to build and test locally
1. npm install
2. npm run package — produces a .vsix
3. F5 in VS Code with the workspace open — launches an extension dev host
4. npm test — unit tests
5. npm run lint — required before PR

## PR conventions
- Title format: free-form; conventional-ish ("fix:", "feat:") prefixes
  common but not enforced
- Branch naming: free-form
- Required PR description fields: pulled from .github/PULL_REQUEST_TEMPLATE.md
  (description, type of change, testing performed)
- CI: lint, unit tests, type check

## Code of conduct highlights
Standard Contributor Covenant; harassment-free, inclusive language, no
spam.

## CLA / DCO
No CLA at time of read; standard inbound=outbound under Apache-2.0.

## Communication norms
- Discord linked in README for real-time
- GitHub Discussions for design proposals
- Issues for bugs and feature requests

## Things easy to miss
- The repo has multiple packages; many issues are scoped to webview-ui
  or to the core extension only — check labels.
- "Bot Responded" label is automated and does not mean a human is
  engaged.
- Issues with only the "stale" label have been auto-flagged; engaging
  on them is fine but expect to nudge the maintainer.
```

---

## Phase 2 — `filter-issues` → `filtered-issues.md`

Excerpt:

```
## Top picks

### #9668: Add API Key field to LM Studio provider for authenticated servers
- Why it fits: TypeScript, size:S label (10–29 LoC), self-contained
  provider config change, has "Help Wanted" + "Good First Issue".
- Estimated effort: small
- Risk: low — clear scope, isolated to one provider's settings UI.
- Maintainer engagement: yes — labeled by maintainer March 2026.
- Files probably involved: src/providers/lm-studio/*, webview-ui
  settings panel for LM Studio.
- Open questions before starting: should the API key field be optional
  (default: yes, since LM Studio servers usually don't require it)?

### #7793: VSCode Terminal Profile environment variables are not respected
- Why it fits: TypeScript, "Help Wanted" + "Good First Issue", touches
  terminal integration which is a well-isolated module.
- Estimated effort: medium
- Risk: medium — terminal env handling has cross-platform quirks.
- Maintainer engagement: bot-only ("Bot Responded" label).
- Files probably involved: src/integrations/terminal/*
- Open questions before starting: which VS Code API surface for terminal
  profile env vars; behavior on Windows vs macOS vs Linux.

## Ruled out

- #8635: Image Support toggle in model configuration is ignored when
  pasting image in chat — has "stale" label, last activity Jan 2026.
- #7876: Claude Sonnet 4.5 Thinking is on a single line — UI rendering
  bug with no clear repro; high scope-creep risk.
- #7635: MCP Server Timeout Issue — touches MCP protocol layer, larger
  than fit criteria allows for a first contribution.
```

(Human picks #9668.)

---

## Phase 3 — `pick-and-deep-read` (scout)

Scout produces `chosen-issue.md` (the issue body + scout's read of it) and
`files-likely-to-change.md`:

```
## Files likely to change

- src/providers/lm-studio/index.ts — provider definition; add apiKey
  field to the config schema and pass to the request headers.
- src/providers/lm-studio/types.ts — extend the LMStudioConfig type
  with optional apiKey.
- webview-ui/src/components/settings/providers/LMStudioSettings.tsx —
  add the input field (mirror the OpenAI-compatible provider's apiKey
  field which already exists).
- webview-ui/src/i18n/en.json — add string for the apiKey label and
  helper text.
- src/providers/lm-studio/__tests__/index.test.ts — add a test that
  the apiKey is forwarded as a Bearer header when set, and absent
  when not set.

## Out of scope (looked at, not changing)

- src/providers/openai-compatible/* — the apiKey pattern is borrowed
  from here, but no edits needed there.
- docs/providers/lm-studio.md — documentation update may be desired
  but is a separate concern; flag for the PR description.
- Other locale files in webview-ui/src/i18n/ — i18n updates for non-en
  locales are typically done in a separate sweep by the i18n
  maintainers.
```

---

## Phase 4 — `draft-pr` → `pr-draft.md`

```
## Title
feat(providers): add optional API key to LM Studio provider

## Description

### Summary
Adds an optional `apiKey` field to the LM Studio provider configuration,
forwarded as a `Bearer` Authorization header when set. Mirrors the
existing OpenAI-compatible provider's API-key handling.

### Closes
Closes #9668

### Motivation
Some LM Studio deployments are exposed behind authenticated reverse
proxies. The current LM Studio provider has no way to attach
credentials to outgoing requests, forcing users to either run an
unauthenticated server or to maintain a fork.

### Approach
1. Extend `LMStudioConfig` with an optional `apiKey` string.
2. In the request builder, attach `Authorization: Bearer <apiKey>`
   when the field is set; omit otherwise.
3. Add the field to the LM Studio settings UI as an optional input,
   labeled "API key (optional — for authenticated servers)".
4. Add a unit test covering both the with-key and without-key paths.

### Test plan
- [ ] New unit test in src/providers/lm-studio/__tests__/index.test.ts
- [ ] Manual: launch dev host, configure LM Studio provider with and
      without an apiKey, verify request headers via a local proxy
- [ ] All existing tests pass
- [ ] npm run lint passes

### Screenshots / recordings
<placeholder — settings UI screenshot before/after>

### Checklist
- [ ] Description completed
- [ ] Tests added or updated
- [ ] Type checks pass
- [ ] Lint passes

### AI assistance disclosure
This PR description and an initial scope analysis were drafted with
the assistance of an AI agent. The implementation, testing, and final
review are by the human contributor.
```

---

## What the human does next

1. Read `pr-draft.md` and decide whether to use it.
2. Implement the change (the agent did NOT write any code — that's
   intentional).
3. Open the PR via the human's normal flow, pasting an edited version
   of `pr-draft.md` as the description.
4. Delete `contribution-package/` once the PR is open (it's not for
   the upstream repo).

The mission's value is in the 30 minutes of triage and onboarding it
saved before the human wrote line one of code, not in any code itself.
