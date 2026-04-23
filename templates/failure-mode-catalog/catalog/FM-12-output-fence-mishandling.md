# FM-12 — Output-fence Mishandling

**Severity:** annoying
**First observed:** every model, every release
**Frequency in our ops:** weekly

## Diagnosis

The sub-agent is asked to return JSON. It returns JSON wrapped in
```` ```json ```` fences, or with a chatty preamble ("Here is the
JSON you asked for:"), or with a trailing "Let me know if you
need more!" The naive consumer (`json.loads(raw)`) raises
`JSONDecodeError`. This is annoying, not dangerous, but if it
happens 30 times a week it looks like a system reliability problem
when it's actually a parsing problem.

## Observable symptoms

- `JSONDecodeError: Expecting value: line 1 column 1` in
  orchestrator logs.
- Sub-agent outputs that look like valid JSON but begin with a
  non-`{`/`[` character.
- Trailing prose after the closing brace.
- Markdown fences around the JSON body.

## Mitigations

1. **Primary** — strip fences and parse defensively. See
   [`agent-output-validation`](../../agent-output-validation/)'s
   `_strip_fences` + `_try_parse` helpers.
2. **Secondary** — prompt the sub-agent with explicit "no prose,
   no fences, no explanation, JSON only" — but treat this as a
   recommendation, not a guarantee. Always parse defensively.

## Related

FM-03 (Schema Drift — distinct, but both surface at the
sub-agent → parent seam).
