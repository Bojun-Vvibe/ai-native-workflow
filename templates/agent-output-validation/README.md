# Template: Agent output validation

A schema-checking layer that sits between a sub-agent and its caller.
The sub-agent is **prompted to return JSON**; this layer validates
that JSON against a JSON Schema **before** the parent agent (or your
code) consumes it. Invalid outputs are either rejected, repaired
in-place by a single repair turn, or quarantined for human review —
based on a per-field policy.

## Why this exists

Sub-agents that "return JSON" do not actually return JSON. They
return:

- JSON wrapped in ```` ```json ```` fences.
- JSON with a chatty preamble ("Here is the JSON you asked for:").
- JSON with trailing commentary.
- JSON that parses but is missing required fields.
- JSON whose `priority` field is `"high"` instead of the enum
  `"P0" | "P1" | "P2"` you specified.
- JSON where a field that should be a list is a single string.

If your parent agent loops over `result["findings"]` and the schema
silently drifted to `result["items"]`, you get a `KeyError` ten
minutes into a long mission, after burning a non-trivial amount of
tokens. A validator at the seam catches this in milliseconds, with a
useful error message, and (optionally) one repair attempt.

## When to use

- You have **>1 sub-agent** producing structured outputs that another
  agent or your code consumes.
- You're paying for a long mission and a malformed sub-agent output
  would waste a recoverable amount of work.
- You have a contract you can write down (a JSON Schema, a Pydantic
  model, a TypeScript type). If you can't write it down, you don't
  have a contract.

## When NOT to use

- The sub-agent's output is consumed only by a human reading
  markdown. Validation has no value there; just write a good prompt.
- You have one sub-agent and one consumer, both of which you control
  in the same process. A `try/except` around `json.loads` is enough.
- The output is genuinely free-form (a draft PR description, a
  changelog summary). Don't force schema on free prose.

## Anti-patterns

- **Validate, then ignore the validation result.** If the schema
  fails and you log a warning and proceed, you've added latency for
  no benefit. Either the validator is a gate or it's noise.
- **One mega-schema for all sub-agents.** Each sub-agent has its own
  contract. Keep schemas small, named, and per-role.
- **No `additionalProperties: false`.** Without this, a sub-agent
  that returns extra noise fields (e.g., `notes`, `confidence`,
  `_internal`) silently passes — and your downstream code may pick
  up a stale field name from a previous version.
- **Auto-repair without bound.** "Ask the sub-agent to fix it" is
  fine *once*. Looping that until it passes is how you spend $40 on
  a 200-token output.
- **Schema drift across consumers.** If three different parent
  agents read the same sub-agent's output, all three must validate
  against the same versioned schema. Otherwise schema changes break
  consumers silently.
- **Stripping markdown fences with regex but not validating
  structure.** You parse `{"foo": 1, "extras": "..."}` and assume
  `foo` is a list because the docs said so. Parsing is not
  validation.

## Files

- `src/validate.py` — stdlib + optional `jsonschema` validator with
  three policies: `reject`, `repair_once`, `quarantine`.
- `src/repair_prompt.py` — the one-shot repair prompt template.
- `schemas/finding.schema.json` — example schema: a single
  "investigation finding" record.
- `schemas/triage_report.schema.json` — example schema: a triage
  report wrapping a list of findings.
- `examples/run-validate.sh` — runs the validator against three
  fixture outputs (good, malformed, repairable).
- `examples/fixtures/` — three sub-agent output fixtures (one
  passing, one structurally broken, one schema-violating but
  repairable).
- `examples/sample-output.md` — what the validator prints for each
  fixture.

## Worked example

```bash
cd templates/agent-output-validation/examples
./run-validate.sh
```

Expected output (excerpt):

```
fixture: good.json           → PASS
fixture: malformed.json      → FAIL (json parse error at line 3 col 18)
fixture: drifted.json        → FAIL (schema: required field 'priority' missing) → REPAIR? yes
```

## Adapt this section

- Replace `schemas/*.json` with the contracts your sub-agents
  actually emit.
- Set `MAX_REPAIR_ATTEMPTS=1` in `validate.py`. Resist raising it.
- Wire `validate(output, schema, policy="reject")` at every
  sub-agent boundary in your orchestrator.
- Pin schema versions: include a `_schema_version` field and refuse
  outputs that don't declare one.
