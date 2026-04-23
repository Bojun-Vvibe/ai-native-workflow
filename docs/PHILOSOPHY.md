# Philosophy

## Why these templates exist

AI coding agents are useful. They are also unsupervised by default. The gap between "useful" and "safely useful" is filled, today, almost entirely by improvisation: each team invents its own conventions, each developer remembers (or forgets) their own guardrails, and each agent session starts from zero. This repository exists to close that gap with reusable, shareable, opinionated templates — so the supervision is encoded in artifacts, not in tribal memory.

## The core stance

Agents are useful but unsupervised. Templates encode the supervision.

**Slop is the failure mode; templates are the antidote.** "Slop" here means the predictable failure pattern of AI-assisted work: drive-by refactors, surprise dependency additions, oversized diffs, plausible-looking code that doesn't quite do the thing, comments posted to the wrong issue, secrets accidentally committed, prompt-cache thrashing that turns a $2 task into a $200 one. None of these are intelligence failures. They are *process* failures. Templates are how we install the process before the agent runs, not after it goes wrong.

## Three principles

1. **Every agent action has an explicit reviewer.** Either a human, or another agent operating under a different profile, or a deterministic check (lint, test, guardrail plugin). No action — code edit, comment draft, commit, file write — flows downstream without a named reviewer. "Trust the agent" is not a review.

2. **No agent ever pushes to a remote without a human gate or a deterministic guardrail.** Local changes are reversible. Remote pushes, posted comments, merged PRs, deployed builds, sent messages — these are not. The asymmetry deserves an explicit boundary, encoded in the template, not in a Slack reminder.

3. **Prompt cache is a first-class economic concern.** Stable prefixes, stable WP IDs, no timestamps in prompts, no random ordering of tool definitions. A workflow that costs 10x more than it should because of cache thrash is not a cheaper workflow than the human one — it's just a worse one with extra latency.

These three principles are the lens. Every template in this repo should be readable as an answer to: *which principle does this template uphold, and how?*
