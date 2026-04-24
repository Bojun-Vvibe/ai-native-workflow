# Template: agent-decision-log-format

A small, append-only JSONL spec for agent decision logs — one line
per agent step, with eight required fields that make post-hoc audit
and CI-gated quality checks tractable. Plus a stdlib-only validator
that returns stable, machine-readable error codes so the spec is
enforceable, not aspirational.

This is the observability counterpart to runtime-control templates
like `tool-call-circuit-breaker` and `agent-cost-budget-envelope`.
Those templates *make* decisions; this template *records* them in a
shape that downstream tooling can read without bespoke parsers.

## Why this exists

Three problems that show up the moment you have more than one agent
or one mission per day:

1. **"Why did the agent give up?" has no canonical answer.** Without
   a per-step `exit_state` enum, every replay tool invents its own
   classification. Six dashboards, six different definitions of
   "completed."
2. **Eval results are not reproducible across prompt changes.**
   Without `prompt_hash` on every step, you cannot tell whether
   today's regression is "the prompt changed" or "the model
   changed" or "the input changed." All three look the same.
3. **Post-hoc audit is impossible.** A regulator, a partner team, or
   future-you wants to know "what did the agent do at 14:32 last
   Tuesday and why was that decision allowed?" If your trace is a
   pile of provider-specific blobs, this is days of work. If every
   step is one JSON line with eight known fields, it's a `grep`.

## When to use

- You run a multi-step agent loop and want one canonical record per
  step that survives the agent's process exit.
- You want a CI gate on the trace format so a careless code change
  cannot silently break downstream consumers (eval, billing, audit).
- You want to compose with `agent-trace-redaction-rules` for export
  or with `prompt-fingerprinting` for the `prompt_hash` value.

## When NOT to use

- You have exactly one tool call per request (web request -> one
  completion). The provider's own request log is enough; you don't
  need a separate per-step format.
- You need full prompt+response capture for fine-tuning. Use a
  separate trace store for that and emit *this* log as the index.
  This format is intentionally compact (no prompt body, no model
  output) so it stays cheap to keep forever.
- Your platform already enforces a richer canonical format (e.g. a
  proprietary OpenTelemetry profile). Map onto that; do not double
  emit.

## What's in the box

| File | What it does |
|---|---|
| `SPEC.md` | The wire spec: required/optional fields, hard rules, validator exit codes, stable error-code table |
| `bin/decision_log_validate.py` | Stdlib-only validator. Reads a JSONL log; emits a JSON report; exits 0 / 1 / 2. CI-droppable. |
| `prompts/decision-log-emitter.md` | Strict-JSON prompt for an agent to emit one decision-log line per step in the canonical shape |
| `examples/01-validate-clean-log/` | Worked example: a four-step mission validates with zero errors |
| `examples/02-detect-missing-and-malformed/` | Worked example: a six-line broken input that surfaces all nine stable error codes in one report |

## Adapt this section

Wire the validator into CI:

```yaml
# .github/workflows/decision-log.yml (sketch)
- name: Validate decision logs
  run: |
    for f in artifacts/decision-logs/*.jsonl; do
      python3 templates/agent-decision-log-format/bin/decision_log_validate.py "$f"
    done
```

Pin the canonical fields in your agent emitter (one suggested layout
in `prompts/decision-log-emitter.md`):

```python
record = {
    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "mission_id": mission.id,
    "step_id": f"s_{step_index:04d}",
    "step_index": step_index,
    "prompt_hash": fingerprint(prompt_pkg),  # see prompt-fingerprinting
    "model": model_name,
    "tools_called": [
        {"name": t.name, "ok": t.ok, "duration_ms": t.dur_ms}
        for t in tool_results
    ],
    "exit_state": exit_state,  # continue|done|handoff|giveup|error
}
```

## Forward compatibility

- Unknown fields are ignored. Add optional fields freely (e.g.
  `tokens_cached`, `cost_usd`, `parent_mission_id`).
- Adding a new value to `exit_state` is a **breaking change** for
  the validator and downstream consumers. Cut a new spec version,
  update the validator, run a deprecation window before producers
  emit the new value.
- Renaming a stable error code is also breaking. Add a new code,
  keep the old one emitted in parallel for one release, then drop.
