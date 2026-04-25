# prompt-template-variable-validator

Strict, declarative validator for `str.format`-style prompt
templates. Stdlib-only (`string.Formatter`, `dataclasses`). The
class is pure: validate the template, validate the values against
a per-variable contract, then render — or raise `ValidationError`
loudly and never partially render.

## The problem

Two failure modes that ship to prod from prompt-engineering codebases
constantly, that no linter or type-checker catches, and that cost
real money in token bills and bad model outputs:

| Bug class | What `str.format` does | What this validator does |
|---|---|---|
| Caller typo (`{user_quesiton}` vs `user_question=…`) | Renders the literal text `{user_question}` into the prompt — the model sees the curly braces | `ValidationError: caller did not provide values for ['user_question']` |
| Missing variable | `KeyError` somewhere downstream, or worse, raised in production for the first time | Caught at validate time with the full list of missing keys |
| Extra variable in `values` not in template | Silently dropped — refactor that removed `{author}` leaks `author=…` for years | `ValidationError: caller passed values not in contract: ['author'] — refusing to silently drop them` |
| `None` value | Renders as the literal string `"None"` inside the system prompt | `ValidationError: expected str, got NoneType=None` |
| `""` value | Renders as empty section, model fabricates content to fill the void | `ValidationError: empty value not allowed (set allow_empty=True if intentional)` |
| 50 KB accidental document in `diff=` | Blows the context window, silent truncation by the upstream | `ValidationError: 'diff': rendered length 50000 exceeds max_len 20000` |
| Wrong type (`pr_number="1234"` as str) | Renders fine, downstream JSON-schema fails | `ValidationError: expected int, got str='1234'` |
| Template uses forbidden constructs (`{x:>10}`, `{user.name}`, `{0}`) | Works — and now your prompt is coupled to the caller's object graph and number ordering | `ValidationError` at template-parse time |

The contract is a `dict[str, VarSpec]` declared next to the template
file — a typed schema for the *prompt's input*, on the same footing
as the JSON schema for the prompt's output (sibling of
`llm-output-jsonschema-repair`).

## API

```python
from validator import VarSpec, render

TEMPLATE = "Repo: {repo_name}\nPR #{pr_number} by {author}\nDiff:\n{diff}"

CONTRACT = {
    "repo_name": VarSpec(type_=str, max_len=200),
    "pr_number": VarSpec(type_=int, max_len=10),
    "author":    VarSpec(type_=str, max_len=80),
    "diff":      VarSpec(type_=str, max_len=20_000),
}

rendered, report = render(TEMPLATE, values, CONTRACT)
# raises ValidationError on any mismatch; returns (str, ValidationReport) otherwise
```

`VarSpec.allow_empty` defaults to `False` because in practice an
empty section in a system prompt is almost always a caller bug.
Set it to `True` when an empty value really is meaningful (e.g.
"no prior turns yet").

## Forbidden in templates

* Positional placeholders (`{}`, `{0}`) — caller intent unclear,
  refactors silently break.
* Format specs (`{x:>10}`) and conversions (`{x!r}`) — moves
  rendering decisions out of the caller and into a template the
  caller may not own.
* Attribute (`{user.name}`) and index (`{items[0]}`) access —
  couples the template to the caller's object graph; a downstream
  refactor of `User` silently breaks the prompt at runtime.

If you actually need any of those, you do not want this template;
use a real template engine (Jinja, Mako) and accept its blast
radius. This template's whole value proposition is that the
contract surface is tiny enough to enforce strictly.

## Sample run

Output of `python3 worked_example.py`, verbatim:

```
============================================================
prompt-template-variable-validator worked example
============================================================

[0] parse_placeholders extracts the ordered, deduped set
  placeholders = ('repo_name', 'pr_number', 'author', 'diff')

[1] happy path: contract matches, values match, lengths OK
  rendered_length = 133
  first 80 chars  = 'You are a code reviewer.\nRepository: anomalyco/opencode\nReviewing PR #1234 by al'

[2] caller typo: passes `user_quesiton` for `user_question`
  [typo] OK ValidationError: caller did not provide values for ['user_question']

[3] caller forgot to pass a required variable
  [missing] OK ValidationError: caller did not provide values for ['diff']

[4] caller passed an extra value not in contract
  [extra] OK ValidationError: caller passed values not in contract: ['secret_token'] — refusing to silently drop them

[5] wrong type: pr_number passed as str
  [type] OK ValidationError: 'pr_number': expected int, got str='1234'

[6] None value: would silently render as the literal 'None'
  [none] OK ValidationError: 'q': expected str, got NoneType=None

[7] empty string: caught even though str.format would accept it
  [empty] OK ValidationError: 'q': empty value not allowed (set allow_empty=True if intentional)

[8] oversize value: 50 KB diff vs max_len=20_000
  [oversize] OK ValidationError: 'diff': rendered length 50000 exceeds max_len 20000

[9] forbidden constructs in the *template* itself
  ['Hello {}'] OK: positional placeholder `{}` is forbidden — name every variable
  ['Hello {0}'] OK: positional placeholder `{0}` is forbidden — name every variable
  ['Hello {user.name}'] OK: attribute / index access in placeholder is forbidden: `{user.name}`
  ['Hello {items[0]}'] OK: attribute / index access in placeholder is forbidden: `{items[0]}`
  ['Hello {x:>10}'] OK: format spec is forbidden in placeholder `{x:>10}` — render at the caller, not in the template
  ['Hello {x!r}'] OK: conversion `!r` is forbidden in placeholder `{x!r}`

============================================================
done
```

All ten failure modes are caught at validate-time with a
caller-actionable error message; the happy path renders 133
characters cleanly. No partial renders, no silent coercions, no
literal `"None"` reaching the model.

## Composes with

* `prompt-template-versioner` / `prompt-version-pinning-manifest` —
  pin the template *and* its contract together; a contract change
  is a template version bump.
* `prompt-fingerprinting` — fingerprint the rendered output, not
  the unrendered template, so a value-shape regression actually
  shows up in the fingerprint.
* `llm-output-jsonschema-repair` — this template enforces the
  *input* contract; that one enforces the *output* contract. Use
  both at every prompt boundary.
* `prompt-pii-redactor` — run redaction *before* `render`; an
  oversize-after-redaction failure is the right signal to abort,
  not to silently truncate.

## Non-goals

* No conditional sections, no loops, no inheritance. Use a real
  template engine if you need them.
* No async, no I/O, no caching. The validator runs in microseconds
  per call; caller composes with their own caching layer if a single
  template is rendered millions of times against the same contract.
