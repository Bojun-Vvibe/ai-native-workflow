# Example 01 — allowlist-blocks-leak

## What this shows

A tool-call envelope contains four fields. Three are explicitly
allowlisted (`idempotency_key`, `attempt_number`, `args.to`,
`args.body`). A fourth — `args.internal_note` — is **not** in the
allowlist. The redactor replaces it with the sentinel and emits a
report line.

## Run

```bash
python3 ../../bin/redact.py rules.json input.json output.json --report report.jsonl
```

## Expected stdout

```
redactions: 1
```

## Expected output.json (excerpt)

```json
{
  "args": {
    "body": "Heads up: deploy at 4pm.",
    "internal_note": "[REDACTED:not_in_allowlist]",
    "to": "alice@example.test"
  },
  "attempt_number": 2,
  "idempotency_key": "a3f1d8b6c2e94075a3f1d8b6c2e94075a3f1d8b6c2e94075a3f1d8b6c2e94075"
}
```

## Expected report.jsonl

```jsonl
{"observed_class": "string_short", "pointer": "/args/internal_note", "reason": "not_in_allowlist"}
```

## What to do next

The `internal_note` field is operator-authored prose about a
customer. It is **not** safe to expose in a trace. Don't add a rule.
Instead, fix the upstream tool to stop emitting the field — the
report line is the receipt that the field exists in production.
