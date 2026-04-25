# prompt-template-unused-variable-detector

Detect drift between the variables a prompt template *declares* (in its
manifest/schema) and the `{{placeholder}}` references *actually used* in
the body. Pure stdlib, deterministic output, exits non-zero on any
finding so it drops straight into pre-commit / CI.

## Why this matters

Production prompt templates rot in two directions and both fail silently:

| Direction | What happens at render time |
| --- | --- |
| Variable declared in manifest, never used in body | Call site keeps computing and passing a value (often expensive: extra DB hit, extra model call to summarize) that nobody reads. No exception, no log. |
| `{{placeholder}}` in body, never declared in manifest | Most lenient renderers leave the literal `{{name}}` in the rendered prompt. The model now sees raw template syntax — degraded output, sometimes a leaked internal field name. |

Plus a soft warning class — `duplicate_declaration` — because last-wins
behavior on duplicate manifest entries is renderer-specific and not
portable.

## Finding classes

| `kind` | Meaning | Suggested action |
| --- | --- | --- |
| `declared_unused` | Manifest names it; body never references it. | Drop from manifest, or restore the reference. |
| `used_undeclared` | Body says `{{x}}`; manifest never declares `x`. | Add to manifest (and wire up the call site) or remove from body. |
| `duplicate_declaration` | Same name declared ≥2× in `manifest.vars`. | Pick one. |

Findings are sorted by `(kind, name)` so two runs over the same input
produce byte-identical output (cron-friendly diffing).

## Input shape

```json
{
  "manifest": {"vars": [{"name": "user_name", "type": "string"}, ...]},
  "body": "Hello {{user_name}}, your task: {{task_summary}}."
}
```

Placeholder grammar: `{{ name }}` with optional surrounding whitespace.
Names must start with a letter or underscore and may contain letters,
digits, `_`, and `.` (for nested addressing like `user.id`). Anything
weirder is intentionally not recognized — normalize the body first.

## Usage

```bash
python3 detect.py example_input.json
```

Exit code: `0` if `ok`, `1` if any finding, `2` on argv misuse.
Malformed input raises `ValueError` (let it crash — config bug, not
runtime input).

## Worked example

`example_input.json` declares 4 distinct vars (one twice — `user_name`)
and references 5 placeholders, with deliberate drift:

- `deprecated_priority` declared, never used
- `user_name` declared twice
- `{{reviewer_handle}}` and `{{project_root}}` used, never declared

Run:

```bash
$ python3 detect.py example_input.json
```

Output (verbatim, captured in `example_output.txt`):

```json
{
  "findings": [
    {
      "detail": "declared in manifest.vars but no matching {{placeholder}} in body",
      "kind": "declared_unused",
      "name": "deprecated_priority"
    },
    {
      "detail": "declared 2 times in manifest.vars",
      "kind": "duplicate_declaration",
      "name": "user_name"
    },
    {
      "detail": "{{project_root}} appears in body at byte offset 133 but not declared in manifest.vars",
      "kind": "used_undeclared",
      "name": "project_root"
    },
    {
      "detail": "{{reviewer_handle}} appears in body at byte offset 98 but not declared in manifest.vars",
      "kind": "used_undeclared",
      "name": "reviewer_handle"
    }
  ],
  "ok": false
}
```

All four expected findings surface; exit code `1`.

## Composes with

- `prompt-template-variable-validator` — validates *types* of values
  passed into declared vars; this template validates the *set* of vars.
  Run both: this catches "the manifest forgot a name", that one catches
  "the value passed for the name has the wrong type".
- `prompt-template-versioner` — bump the version whenever this detector
  reports a non-warning finding, since the rendered prompt surface area
  has changed.
- `prompt-section-order-canonicalizer` — run after this passes, so
  canonicalization is operating on a body whose variables actually
  resolve.
