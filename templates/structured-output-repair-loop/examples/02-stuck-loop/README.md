# Example 02 — model wraps JSON in markdown fences, stuck-detection fires

## What goes wrong

Every attempt wraps the JSON in ` ```json ` fences. `json.loads`
fails identically each time (`JSONDecodeError` at `/`).

Attempt 1: fails, fingerprint *X* recorded.
Attempt 2: fails, fingerprint *X* again → **stuck**, exit
immediately.

The loop saves attempts 3 and 4 from being burned on a mistake
the model is clearly never going to fix on its own.

## Run it

```sh
python3 ../../bin/repair_loop.py scenario.json
```

## Expected exit state

```json
{
  "status": "stuck",
  "attempts": 2,
  "fingerprints_seen": ["<one fingerprint, the JSONDecodeError hash>"],
  "parsed_value": null,
  "last_error": {
    "error_class": "JSONDecodeError",
    "json_pointer": "/",
    "expected": "valid JSON",
    "got": "<json.JSONDecodeError message>"
  },
  "last_raw_output": "```json\n{\"status\": \"ok\"}\n```"
}
```

## What this example demonstrates

- Stuck-detection saves 50% of the worst-case cost
  (2 attempts instead of 4) when the model is in a deterministic
  failure mode.
- The right caller response is **not** to retry. Either:
  - Strip the fences in code (`re.sub(r'^```\\w*\\n|\\n```$',
    '', raw)`) and re-validate. The fences are a known model
    artefact, not a semantic error.
  - Hard-fail and surface to a human. The system prompt clearly
    forbade fences; the model is non-compliant.
- Compare to a naive loop without stuck-detection: same scenario,
  same outcome (failure), but 4 model calls instead of 2.
