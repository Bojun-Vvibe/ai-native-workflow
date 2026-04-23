# Template: Failure-mode catalog for LLM agents

A taxonomized catalog of the most common ways LLM coding agents
fail in production, with **mitigations** linked to other templates
in this repo. The catalog is short on purpose — every entry has a
named pattern, a one-paragraph diagnosis, observable symptoms, and
1–3 mitigations you can apply.

The point: when an agent run goes wrong, you triage by *naming the
failure mode* before debugging the prompt. Naming is the difference
between "the agent is broken" (a feeling) and "this is a Premature
Convergence (FM-04) and the mitigation is to add a scout pass" (a
plan).

## Why this exists

Most "the agent is bad" complaints are actually one of fifteen
recurring patterns. Without a catalog, every team rediscovers them
the hard way and invents ad-hoc fixes. With a catalog:

- Triage is a lookup: "this looks like FM-07 (Schema Drift)" →
  apply the documented mitigation.
- Post-mortems become tractable: "FM-09 happened twice this month
  in mission type X; we should add the FM-09 mitigation to the X
  template."
- Onboarding accelerates: a new operator reads the catalog and
  recognizes patterns instead of starting from zero.

## When to use

- You operate ≥3 different mission types and have logs from
  multiple weeks of runs.
- Your team includes anyone who isn't the original author of every
  prompt — they need a shared vocabulary.
- You want to make agent ops a discipline, not a vibe.

## When NOT to use

- You have a single one-shot prompt. Nothing to taxonomize.
- You haven't yet shipped two missions; you have no data. Build
  the catalog from your *own* observed failures, not from a generic
  template. (This catalog is a starting structure, not a
  pre-filled answer for your specific stack.)

## Anti-patterns

- **One catalog with 70 entries.** Nobody reads it. Cap at ~20.
  Merge near-duplicates aggressively.
- **Failure modes that aren't observable.** "The model didn't
  understand the spec" is not a failure mode; it's a guess. Every
  entry must list **observable symptoms** the operator can check
  in logs or output.
- **Mitigations that say 'write a better prompt'.** That's not a
  mitigation; it's an aspiration. Mitigations name a concrete
  template, hook, or process change.
- **No examples.** Without an example log snippet per failure
  mode, operators can't recognize the pattern in the wild.
- **Catalog drifts from reality.** Schedule a quarterly review.
  Add new failure modes you observed; remove entries that haven't
  triggered in 6 months.

## Files

- `catalog/index.md` — table of contents with severity rating and
  mitigation pointer for each entry.
- `catalog/FM-01-context-rot.md` through `catalog/FM-12-prompt-cache-thrash.md`
  — one failure mode per file, full write-up.
- `examples/triage-walkthrough.md` — operator triages three real
  failed runs by walking the catalog.
- `examples/log-symptoms-reference.md` — the canonical log
  patterns to grep for when triaging.

## Catalog schema

Every failure mode write-up follows this structure:

```
# FM-NN — <Short Name>

**Severity:** <annoying | costly | dangerous>
**First observed:** <YYYY-MM>
**Frequency in our ops:** <rare | occasional | weekly>

## Diagnosis
One paragraph: what's actually happening inside the agent loop.

## Observable symptoms
- Bullet 1 (a thing you'd see in a log or in the output)
- Bullet 2
- Bullet 3

## Mitigations
1. **Primary** — concrete change, often a link to another template.
2. **Backstop** — what to do if the primary doesn't apply.

## Related
- FM-NN, FM-NN — adjacent or commonly co-occurring modes.
```

## Worked example

`examples/triage-walkthrough.md` walks through three failed
mission runs. Each is named (FM-04, FM-07, FM-11) within five
minutes of opening the log, and the documented mitigation is
applied. The point is not the specific entries — it's the speed of
triage when failure modes have names.

## Adapt this section

- Read the seed catalog (12 entries). Delete any that don't apply
  to your stack. Add entries for failure modes you've observed
  that aren't here.
- Quarterly: review which entries triggered, update frequency
  ratings, retire stale entries.
- Wire `examples/log-symptoms-reference.md` into your operator
  runbook as the first step of any failed-mission triage.
