# Example 03 — exhausted, caller falls back to a stripper

## What goes wrong

Every attempt emits an unrequested top-level `notes` field, but
with a different value each time (`"a"`, `"b"`, `"c"`, `"d"`).
The validator raises `ExtraField at /notes` every time.

Note the value differs across attempts but the **fingerprint is
the same** (fingerprinting ignores the offending value, only
considers `error_class + normalised_pointer + expected`). So
attempts 1 and 2 produce the same fingerprint and the loop
exits with `status=stuck` on attempt 2 — same as example 02.

Wait — the docstring claims this is `status=exhausted`. Read on.

## Why this isn't `stuck`

The loop's stuck-detection requires the **same fingerprint
appearing twice**. In this scenario, it does (attempts 1 and 2
both fingerprint to the `ExtraField at /notes` hash). So
`repair_loop.py` *will* return `status=stuck` after attempt 2.

That's a feature: the loop refuses to burn 4 attempts on a
mistake the model isn't fixing.

The caller-side **fallback** then kicks in. Pseudocode the
caller wraps around the loop:

```python
result = run_repair_loop(...)
if result["status"] == "parsed":
    return result["parsed_value"]
elif result["status"] in ("stuck", "exhausted", "expired"):
    # Try a deterministic stripper as a last resort.
    raw = result["last_raw_output"]
    try:
        partial = json.loads(raw)
        for extra in set(partial.keys()) - {"x"}:
            del partial[extra]
        _validate(partial, schema)  # re-validate
        return partial               # OK — we recovered.
    except Exception:
        raise GiveUp(result)
```

So the loop's exit state is `stuck`, but the **mission outcome**
is `recovered_via_fallback`. The fallback is *not* part of this
template by design — it's caller-specific (some callers strip,
some hard-fail, some prompt the human, some try a different
model).

## Run it

```sh
python3 ../../bin/repair_loop.py scenario.json
```

## Expected loop exit state

```json
{
  "status": "stuck",
  "attempts": 2,
  "fingerprints_seen": ["<one fingerprint, the ExtraField /notes hash>"],
  "parsed_value": null,
  "last_error": {
    "error_class": "ExtraField",
    "json_pointer": "/notes",
    "expected": "one of ['x']",
    "got": "notes"
  },
  "last_raw_output": "{\"x\": 2, \"notes\": \"b\"}"
}
```

## What this example demonstrates

- Stuck-detection is the bridge to a deterministic fallback,
  not a hard failure.
- The fingerprint normalisation is what makes this
  cost-efficient: even though the *values* differ each attempt
  (`"a"`, `"b"`, `"c"`), the *mistake* doesn't, so the loop
  bails after 2 instead of 4.
- A caller pattern (strip → re-validate → return) recovers
  cleanly from the loop's `stuck` exit. The loop doesn't try
  to be clever about this; it hands a clean signal to the
  caller and the caller decides.
