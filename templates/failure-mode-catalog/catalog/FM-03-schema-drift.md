# FM-03 — Schema Drift

**Severity:** dangerous
**First observed:** as soon as we had ≥2 sub-agents
**Frequency in our ops:** weekly

## Diagnosis

A sub-agent's structured output silently drifts in shape between
runs. A field is renamed, a list becomes a string, an enum gains a
value, an "extra" field appears. The parent agent (or your code)
keeps consuming the output as if the schema were stable, and
either crashes on a `KeyError` 10 minutes in, or — much worse —
silently picks up the wrong data.

## Observable symptoms

- `KeyError`, `TypeError`, or "field X not found" exceptions in the
  orchestrator.
- The parent agent makes a confident but wrong claim that
  references data the sub-agent did not actually produce in this
  shape.
- A field name flips between `summary` and `description` across
  runs of the same role.
- A field that was a list of strings is now a list of objects
  (because the sub-agent decided to "enrich" it).

## Mitigations

1. **Primary** — enforce
   [`agent-output-validation`](../../agent-output-validation/) at
   every sub-agent → parent seam, with `additionalProperties:
   false` and a frozen schema version.
2. **Backstop** — version every schema. Reject outputs that don't
   declare a `_schema_version` or that declare an unsupported one.

## Related

FM-12 (Output-fence Mishandling — looks similar but is upstream of
schema validation), FM-10 (Confident Fabrication — drift can mask
a fabrication).
