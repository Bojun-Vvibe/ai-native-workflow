# Template: Prompt version pinning manifest

A lockfile for the `(system_prompt, user_template, model, temperature,
top_p, max_tokens, tool_signature)` tuple your agent depends on.
The manifest pins each tuple by SHA-256 fingerprint over a canonical
JSON encoding. A drift detector compares the live tuple against the
pin and reports exactly which fields changed.

Think of it as `package-lock.json` for prompts.

## Why this exists

Prompts and model parameters are part of your dependency graph
whether you treat them that way or not. When someone reworded the
system prompt or bumped `temperature` from `0.0` to `0.7`, you
want:

1. A **pin** that captures the exact tuple you tested against.
2. A **drift detector** that fails CI when the live tuple no longer
   matches the pin.
3. A **canonical encoding** so two semantically identical tuples
   always produce the same hash regardless of dict key order.

Without this, "we changed nothing on our side" becomes the most
expensive sentence in your incident review.

## Contract

### Pinned fields (closed allow-list)

```
system_prompt   user_template   model        temperature
top_p           max_tokens      tool_signature
```

Unknown fields **raise `ValueError` at canonicalization time**.
This is deliberate: silently absorbing new fields would let drift
sneak in by smuggling a new key past the hash. To add a field, bump
the schema and re-pin everything.

### Canonical encoding

`json.dumps(payload, sort_keys=True, separators=(",", ":"),
ensure_ascii=False).encode("utf-8")`. Stdlib only. No surprises.

### Manifest schema (v1)

```json
{
  "schema_version": 1,
  "entries": {
    "<name>": {
      "fingerprint": "<hex sha256>",
      "fields": ["system_prompt", "user_template", "model",
                 "temperature", "top_p", "max_tokens",
                 "tool_signature"],
      "tuple": { ... },
      "pinned_at": "<iso8601 — caller-injected, not wall clock>"
    }
  }
}
```

### Drift report

```python
@dataclass
class DriftReport:
    name: str
    drifted: bool
    pinned_fingerprint: str
    live_fingerprint: str
    changed_fields: list[str]
    missing_in_live: list[str]
    unknown_in_live: list[str]
```

`drifted` is the only field a CI gate needs. The other fields exist
so a human reading the failure can immediately see what changed.

## Determinism

- `pinned_at` is **injected** by the caller (`now_iso=...`) so the
  manifest is byte-identical across runs.
- The fingerprint never depends on dict iteration order.
- The drift report is a pure function of `(manifest, name,
  live_tuple)`.

## Files

- `pinmanifest.py` — the implementation. Stdlib only.
- `examples/example_pin_and_verify.py` — build a manifest, persist,
  reload, confirm no drift.
- `examples/example_drift_detected.py` — live tuple has drifted;
  detector pinpoints exact fields and exits non-zero.

## Worked example 1 — pin and verify (no drift)

```
$ python3 examples/example_pin_and_verify.py
manifest schema_version: 1
pinned entries        : ['classifier', 'summarizer']
summarizer fp         : c7ef6a9fefd904b3...
classifier fp         : a2b3aaaff6de8714...

drift report for 'summarizer':
  drifted: False
  pinned : c7ef6a9fefd904b3...
  live   : c7ef6a9fefd904b3...
```

## Worked example 2 — drift detected (CI gate fires)

```
$ python3 examples/example_drift_detected.py
drift report for 'summarizer':
  drifted: True
  pinned : c7ef6a9fefd904b3...
  live   : c66d632ab1441e04...
  changed_fields: ['system_prompt', 'temperature']

ACTION: refuse to deploy until pin is updated.
$ echo $?
2
```

The detector identified the two drifted fields (`system_prompt` was
reworded, `temperature` went from `0.0` to `0.7`) without needing
any manual diff. Exit code `2` is suitable for a CI gate.

## When to use this

- You ship an agent whose behavior depends on a specific prompt and
  whose evals were measured against a specific `(model, temperature)`.
- You have multiple environments (dev / staging / prod) and need to
  prove they're running the same tuple.
- A platform team rotates default model versions and you need a
  fail-loud signal when your pinned model gets silently rerouted.

## When not to use this

- You're prototyping and the prompt changes hourly. Pin once you
  have an eval you trust.
- Your agent's tuple is generated dynamically per request. Pin the
  *generator* config instead.
