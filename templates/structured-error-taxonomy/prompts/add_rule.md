# Prompt — propose a new rule for an unknown error

You are triaging a batch of error records that the classifier in
`structured-error-taxonomy` matched against the catch-all `default`
rule (i.e. they came back as `class=unknown`).

For each cluster of similar records, return a single JSON object:

```json
{
  "rule_id": "short_snake_case_id",
  "rationale": "one sentence: why these belong together and why the verdict is correct",
  "predicate_sketch": "plain-English description of the predicate (e.g. 'source==model AND vendor_code contains \"overloaded\"')",
  "verdict": {
    "class": "<one of CLASSES from SPEC.md>",
    "retryability": "<one of RETRYABILITY from SPEC.md>",
    "attribution": "<one of ATTRIBUTION from SPEC.md>"
  },
  "sample_record_ids": ["<id1>", "<id2>"]
}
```

Hard constraints:

1. Do **not** invent new enum values. If no existing class fits, return
   `{"class": "unknown", ...}` and explain in `rationale` what new
   class would be needed; a human will extend `SPEC.md` first.
2. Pick `retryability` conservatively: if you cannot prove a class is
   safe to retry, choose `do_not_retry`.
3. Place the new rule *above* the `default` catch-all but *below* any
   more specific existing rule that overlaps; note the desired ordering
   in `rationale`.
4. Output **only** the JSON object(s), one per line, no prose, no
   markdown fences.
