# Sample run output

```
$ ./run-validate.sh
--- fixture: good.json
  reject:        PASS  (213 bytes)
  repair_once:   PASS
--- fixture: malformed.json
  reject:        FAIL  json parse error at line 1 col 1: Expecting value
  repair_once:   needs repair  (json parse error at line 1 col 1: Expecting value...)
--- fixture: drifted.json
  reject:        FAIL  schema: $: Additional properties are not allowed ('confidence' was unexpected)
  repair_once:   needs repair  (schema: $: Additional properties are not allowed ('confidenc...)
```

Notes:

- `good.json` — passes both policies cleanly.
- `malformed.json` — sub-agent wrapped JSON in markdown, added prose,
  and put a stray comma. The fence-stripper handles the prose;
  the trailing `,` and unterminated string break the parse.
  `repair_once` would feed this back to the model with the parse
  error.
- `drifted.json` — parses fine, but the sub-agent dropped the
  required `priority` field and added an unexpected `confidence`.
  Schema with `additionalProperties: false` catches both. This is
  the failure mode you most want a validator for: silent drift in a
  field name or shape.
