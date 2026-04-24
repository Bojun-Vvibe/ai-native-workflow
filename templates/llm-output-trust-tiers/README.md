# llm-output-trust-tiers

Pure tier router for LLM outputs. Given a structured *evidence record*
(validator outcome, source class, blast radius, canary status, optional
caller override), decide which trust tier the output belongs to and
what the orchestrator should do with it.

Tiers, most to least trusted:

1. `auto_apply` — apply without human review
2. `shadow_apply` — apply but mark for sampling / async review
3. `human_review` — block until a human signs off
4. `quarantine` — never apply; store for forensics

## Why

By the time an LLM output reaches the orchestrator's "apply" step,
several signals about its trustworthiness are already on the table:
schema validity, how many repair turns it took, whether it came from a
pinned eval, what the blast radius of applying it is, and whether a
canary passed. Without a single router, every call site invents its own
ad-hoc combination of these signals — usually getting the corner cases
wrong, almost always defaulting to "apply" when in doubt.

This template makes the routing a single pure function with three
properties:

1. **Hard fails always quarantine**, no matter what the override says.
2. **Demotions stack** — independent risk signals can each push the
   output one rung toward quarantine.
3. **Caller overrides can only demote**, never promote. A bug in the
   caller cannot upgrade a `human_review` to `auto_apply`.

## What

- `bin/classify_trust_tier.py` — stdlib-only Python. Reads JSONL on
  stdin or `--in`, writes one verdict per input line, exits
  `0` (all auto/shadow) / `1` (at least one human_review) /
  `2` (at least one quarantined or malformed input).
- `SPEC.md` — tiers, evidence record fields, routing rules in order,
  exit-code table, composition.
- `prompts/explain_verdict.md` — strict-JSON prompt that turns a
  verdict into an operator-facing one-paragraph headline + next action.
- `examples/` — two end-to-end runs.

## When

- You already have validator output (`agent-output-validation`,
  `structured-output-repair-loop`) and need to decide what to *do* with
  the validated output, not just whether it parses.
- You are about to wire an "auto-apply" path and want a single bottleneck
  every output flows through, so you can audit one routing function
  rather than N call sites.
- You want the routing decision to be replayable (pure inputs → pure
  output), so you can re-run last week's verdicts under a new policy
  without re-calling any model.

## Worked example 01 — clean batch (exit 0)

Three outputs, each with at most a single mild risk signal. All land
in `auto_apply` or `shadow_apply`, so the run exits 0.

```bash
$ ./bin/classify_trust_tier.py --in examples/01-auto-apply-clean/input.jsonl
{"id": "out-1", "reasons": ["clean"], "tier": "auto_apply"}
{"id": "out-2", "reasons": ["clean"], "tier": "auto_apply"}
{"id": "out-3", "reasons": ["repair_count:1", "source_fresh"], "tier": "shadow_apply"}
$ echo $?
0
```

`out-3` had two demotion signals (one repair turn, fresh source) but
both stop at `shadow_apply` rather than escalating, because neither is
severe on its own and the blast radius is `reversible`.

## Worked example 02 — quarantine + human_review + override (exit 2)

Five outputs covering every escalation path:

- `out-A` — clean schema but `fresh` source + `irreversible` blast →
  `human_review`.
- `out-B` — `schema_ok=false` → straight to `quarantine` (the
  `repair_count=3` and failed canary are recorded but not the *reason*
  — the schema fail is the deterministic first hard-fail rule).
- `out-C` — `repair_count=4` exceeds the over-threshold guard → `quarantine`.
- `out-D` — `cached_known` + `reversible` would normally `auto_apply`,
  but `repair_count=1` plus `canary_passed=false` demotes to
  `human_review`.
- `out-E` — pristine inputs (`pinned_eval`, `read_only`, canary passed)
  but the caller passed `override_tier=human_review`. The override is
  honored because it's a demotion.

```bash
$ ./bin/classify_trust_tier.py --in examples/02-quarantine-on-low-trust/input.jsonl
{"id": "out-A", "reasons": ["source_fresh", "blast_irreversible"], "tier": "human_review"}
{"id": "out-B", "reasons": ["schema_invalid"], "tier": "quarantine"}
{"id": "out-C", "reasons": ["repair_count_over_threshold:4"], "tier": "quarantine"}
{"id": "out-D", "reasons": ["repair_count:1", "canary_failed"], "tier": "human_review"}
{"id": "out-E", "reasons": ["override_demoted_to:human_review"], "tier": "human_review"}
$ echo $?
2
```

The exit code is 2 because at least one output (`out-B`, `out-C`)
quarantined; CI / cron jobs treat exit 2 as "block the pipeline" and
exit 1 as "drain the human-review queue."

## Layout

```
llm-output-trust-tiers/
├── README.md
├── SPEC.md
├── bin/
│   └── classify_trust_tier.py
├── prompts/
│   └── explain_verdict.md
└── examples/
    ├── 01-auto-apply-clean/
    │   ├── input.jsonl
    │   ├── output.jsonl
    │   └── exit.txt
    └── 02-quarantine-on-low-trust/
        ├── input.jsonl
        ├── output.jsonl
        └── exit.txt
```

## Composes with

- [`templates/agent-output-validation`](../agent-output-validation/) and
  [`templates/structured-output-repair-loop`](../structured-output-repair-loop/)
  produce `schema_ok` / `repair_count`.
- [`templates/structured-error-taxonomy`](../structured-error-taxonomy/)
  upstream: a `tool_bad_input` error class on the model call should set
  `source_class=fresh` even if cache lookup said hit.
- [`templates/agent-trace-redaction-rules`](../agent-trace-redaction-rules/)
  — quarantined outputs are still safe to export as redacted forensic
  data.
- [`templates/agent-decision-log-format`](../agent-decision-log-format/)
  — emit one decision-log line per verdict (`tier` + `reasons`) so the
  audit trail is queryable.
