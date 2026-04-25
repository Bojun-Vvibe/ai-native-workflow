# agent-handoff-message-validator

Validate the JSON envelope one agent passes to another at a handoff
boundary (scout → actor, planner → implementer, implementer → reviewer)
*before* the downstream agent ever sees it. Catches structural and
semantic problems that would otherwise silently corrupt the next
agent's context window.

## How this differs from `agent-handoff-protocol`

`agent-handoff-protocol` defines the **transport** envelope
(`done` / `partial` / `unrecoverable`). This template validates the
**payload** sitting inside that envelope: required fields, type shape,
length budgets, enum values, internal reference integrity, and
banned-token leaks.

Use both: protocol decides routing; this validator decides whether the
content is safe to forward.

## Problem

Bad handoffs corrupt downstream agents quietly:

- Missing `next_action` → downstream agent invents one.
- `from_agent == to_agent` → infinite loop.
- `summary` references `artifact:foo` but `foo` isn't in the artifacts
  list → downstream agent hallucinates content.
- 8 KB summary blows the next prompt's cache budget.
- An internal codename leaks across an agent boundary you didn't intend
  to cross.

## Solution

`validate_handoff(msg, banned_tokens=...)` returns a `ValidationResult`
with separate `errors` and `warnings`. Pure stdlib, never raises.

Checks:

| Check                                   | Severity |
|-----------------------------------------|----------|
| Required fields present + correct type  | error    |
| `from_agent != to_agent`                | error    |
| `task_id` matches `^[A-Za-z0-9_\-]{4,64}$` | error |
| `next_action` ∈ allowed enum            | error    |
| Summary non-empty, ≤ hard char cap      | error    |
| Summary above soft char cap             | warning  |
| Each open question non-empty string     | error    |
| Long open question                      | warning  |
| Each artifact has non-empty kind + ref  | error    |
| Duplicate artifact ref                  | warning  |
| `artifact:<ref>` in summary resolves    | error    |
| Banned token substring in any text      | error    |

## Files

- `template.py` — `validate_handoff(...)`, `ValidationResult`,
  `REQUIRED_FIELDS`, `ALLOWED_NEXT_ACTIONS`. Pure stdlib.
- `example.py` — four scenarios: one good handoff and three flavors
  of broken (missing fields, bad refs / same agent / bad enum,
  banned-token leak with a custom blocklist).

## Worked example

```
$ python3 templates/agent-handoff-message-validator/example.py
agent-handoff-message-validator :: worked example
================================================================
[PASS] good_handoff
  (clean)

[FAIL] missing_fields_and_short_task_id
  ERROR  : missing required field: next_action
  ERROR  : missing required field: artifacts
  ERROR  : missing required field: open_questions

[FAIL] bad_refs_same_agent_bad_enum
  ERROR  : from_agent and to_agent are identical: 'reviewer'
  ERROR  : next_action 'merge_now' not in ['ask_human', 'implement', 'investigate', 'review', 'stop']
  ERROR  : open_questions[0]: empty / whitespace only
  ERROR  : artifacts[1].kind: must be non-empty string
  ERROR  : summary references unknown artifact:does-not-exist
  warn   : artifacts[1]: duplicate ref 'diff-aaa'

[FAIL] banned_token_leak
  ERROR  : banned token 'super-secret-codename' found in summary

================================================================
scenarios=4 pass=1 fail=3
sample_result_shape = {"errors": [], "ok": true, "warnings": []}
```

4 scenarios: 1 clean pass, 3 surfaced their distinct failure modes
(structural, semantic, security/leak) without crashing on any of them.

## Wire-up sketch

```python
from template import validate_handoff

def forward(msg, banned):
    r = validate_handoff(msg, banned_tokens=banned)
    if not r.ok:
        log.error("handoff_rejected", errors=r.errors)
        return  # or quarantine, or escalate to human
    for w in r.warnings:
        log.warning("handoff_warning", w=w)
    downstream_agent.receive(msg)
```

## Where this fits

Pair with `agent-handoff-protocol` (transport envelope),
`agent-output-validation` (schema-checking sub-agent JSON outputs), and
`agent-trace-redaction-rules` (scrub before persistence). This template
is the *gate* between two agents' context windows.
