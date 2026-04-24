# Example 01 — typo field, one repair fixes it

## What goes wrong

Attempt 1 emits `userId` (camelCase JS-idiom). The schema requires
snake_case `user_id`. Validator raises `MissingField at /user_id`
*and* `ExtraField at /userId` (the validator returns the first
error it hits — `MissingField`).

The repair-hint block tells the model:

```
=== REPAIR REQUIRED ===
Previous attempt failed validation:
  path:     /user_id
  error:    present
  got:      null
  fix:      Add the required field /user_id (expected: present).
=== END REPAIR ===
```

Attempt 2 fixes the field name. Validator passes.

## Run it

```sh
python3 ../../bin/repair_loop.py scenario.json
```

## Expected exit state

```json
{
  "status": "parsed",
  "attempts": 2,
  "fingerprints_seen": ["<one fingerprint, the MissingField hash>"],
  "parsed_value": {
    "user_id": 42,
    "name": "Alice",
    "email": "alice@example.com"
  },
  "last_error": null,
  "last_raw_output": "{\"user_id\": 42, \"name\": \"Alice\", \"email\": \"alice@example.com\"}"
}
```

## What this example demonstrates

- A single, well-scoped error → a single, well-scoped fix.
- Cost: 2 model calls instead of 1. The repair turn carries the
  previous attempt's output (~80 tokens) and the hint block (~80
  tokens), so worst case ~2.5× the single-call cost. For a
  field-typo failure rate of 5%, the amortised overhead is
  `0.05 * 1.5 = 7.5%` — usually worth it.
