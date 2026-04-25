# prompt-message-role-sequence-validator

Pure structural validator for the role sequence of a multi-turn chat prompt
(`{role, content, tool_calls?, tool_call_id?}` records). Catches the family of
bugs where the *individual* messages are well-formed JSON but the *sequence*
between them is incoherent — the failure mode that 4xx-rejects a request
upstream and that no per-message JSON-schema check will ever catch.

The validator runs **before** the prompt is sent. It is pure, stdlib-only, and
deterministic: same messages in, same `(errors, warnings)` out.

## Why this template

Most "prompt failed" investigations on multi-agent missions land on one of:

- caller forgot the `system` turn, or accidentally inserted a second one mid-stream
- two `assistant` turns in a row (state machine bug — model talked to itself)
- two `user` turns in a row (a previous `assistant` turn was dropped)
- a `tool` message whose `tool_call_id` doesn't match any open `tool_calls`
- assistant emitted `tool_calls=[a,b]` but the trace was truncated before
  `tool` replies arrived for both ids
- a no-op assistant turn (no `content`, no `tool_calls`) wasting a slot

These look obvious in hindsight but are exactly what slips past per-message
validation. This template models them as a 10-rule first-match-wins table and
returns one structured `Issue` per offence.

## Rules

| code | when |
|---|---|
| `empty_messages` | message list is empty |
| `bad_first_role` | first role is not `system` (or not `system`/`user` with `require_system=False`) |
| `duplicate_system` | more than one `system`, or `system` not at index 0 |
| `consecutive_assistant` | two assistant messages in a row |
| `consecutive_user` | two user messages in a row |
| `tool_without_call` | `tool` message whose `tool_call_id` doesn't match any open assistant `tool_calls` |
| `unanswered_tool_call` | assistant declared `tool_calls=[...]` and the next assistant or user turn arrived before all replies |
| `unknown_role` | role not in `{system, user, assistant, tool}` |
| `empty_content_non_tool_call` | assistant turn with no content AND no `tool_calls` |
| `trailing_assistant_with_open_tool_calls` | last message is an assistant with unanswered `tool_calls` |

## Usage

```python
from validator import validate

messages = [
    {"role": "system", "content": "be terse"},
    {"role": "user", "content": "ping"},
    {"role": "assistant", "content": "pong"},
]

result = validate(messages)
if not result.ok:
    for err in result.errors:
        print(f"[{err.code}] @msg{err.index}: {err.detail}")
    raise SystemExit(1)
```

`validate(messages, require_system=False)` relaxes the first-role rule for
embeddable sub-prompts that don't carry their own system turn.

## Files

- `validator.py` — pure stdlib validator, ~180 lines
- `example.py` — five worked scenarios, runnable via `python3 example.py`

## Worked example output

Verbatim from `python3 example.py`:

```
========================================================================
S1 — clean tool round-trip (expected: PASS)
========================================================================
messages:
  [0] {'role': 'system', 'content': 'You answer in one sentence.'}
  [1] {'role': 'user', 'content': 'What is 2+2?'}
  [2] {'role': 'assistant', 'tool_calls': [{'id': 'call_1', 'name': 'calc', 'args': {'expr': '2+2'}}], 'content': None}
  [3] {'role': 'tool', 'tool_call_id': 'call_1', 'content': '4'}
  [4] {'role': 'assistant', 'content': 'It is 4.'}

result:
{
  "errors": [],
  "ok": true,
  "warnings": []
}

========================================================================
S2 — missing system + duplicate system (expected: FAIL)
========================================================================
messages:
  [0] {'role': 'user', 'content': 'hi'}
  [1] {'role': 'assistant', 'content': 'hello'}
  [2] {'role': 'system', 'content': 'by the way, be terse'}
  [3] {'role': 'user', 'content': 'ok'}

result:
{
  "errors": [
    {
      "code": "bad_first_role",
      "detail": "first message must be 'system', got 'user'",
      "index": 0
    },
    {
      "code": "duplicate_system",
      "detail": "'system' message must be at position 0",
      "index": 2
    }
  ],
  "ok": false,
  "warnings": []
}

========================================================================
S3 — consecutive assistant + empty assistant (expected: FAIL)
========================================================================
messages:
  [0] {'role': 'system', 'content': 'be helpful'}
  [1] {'role': 'user', 'content': 'hi'}
  [2] {'role': 'assistant', 'content': 'first half'}
  [3] {'role': 'assistant', 'content': '   '}

result:
{
  "errors": [
    {
      "code": "consecutive_assistant",
      "detail": "two assistant messages in a row",
      "index": 3
    },
    {
      "code": "empty_content_non_tool_call",
      "detail": "assistant turn has no content and no tool_calls",
      "index": 3
    }
  ],
  "ok": false,
  "warnings": []
}

========================================================================
S4 — tool message with no matching call (expected: FAIL)
========================================================================
messages:
  [0] {'role': 'system', 'content': 'be helpful'}
  [1] {'role': 'user', 'content': 'tell me the time'}
  [2] {'role': 'assistant', 'content': 'let me check'}
  [3] {'role': 'tool', 'tool_call_id': 'call_xyz', 'content': '12:00'}
  [4] {'role': 'assistant', 'content': 'noon'}

result:
{
  "errors": [
    {
      "code": "tool_without_call",
      "detail": "tool message references id='call_xyz' but no preceding assistant declared it (open ids: [])",
      "index": 3
    }
  ],
  "ok": false,
  "warnings": []
}

========================================================================
S5 — declared tool_calls left unanswered (expected: FAIL)
========================================================================
messages:
  [0] {'role': 'system', 'content': 'be helpful'}
  [1] {'role': 'user', 'content': 'lookup user 42'}
  [2] {'role': 'assistant', 'tool_calls': [{'id': 'call_a', 'name': 'db_get', 'args': {'id': 42}}, {'id': 'call_b', 'name': 'audit_log', 'args': {'id': 42}}], 'content': None}
  [3] {'role': 'assistant', 'content': 'user 42 is bob'}

result:
{
  "errors": [
    {
      "code": "consecutive_assistant",
      "detail": "two assistant messages in a row",
      "index": 3
    },
    {
      "code": "unanswered_tool_call",
      "detail": "assistant declared tool_calls ['call_a', 'call_b'] but next assistant turn arrived before tool replies",
      "index": 2
    }
  ],
  "ok": false,
  "warnings": []
}
```

## Composes with

- `agent-handoff-message-validator` — that validates a single handoff payload
  between two agents; this validates the *chat history* fed to a model
- `prompt-template-variable-validator` — checks `{var}` substitution; this
  checks the message-list shape after substitution
- `tool-call-argument-schema-coercer` — validates the *args of one tool call*;
  this validates that the tool message *exists at all* and matches an open call
- `agent-decision-log-format` — log one line per failed validation with the
  `errors[*].code` so you can grep by failure mode across missions

## Non-goals

- Does **not** count tokens — pair with `prompt-token-budget-trimmer`
- Does **not** parse `content` for prompt-injection — pair with
  `prompt-injection-prefilter`
- Does **not** check tool-call *argument* schemas — pair with
  `tool-call-argument-schema-coercer`
- Does **not** validate that `tool_call_id` strings are globally unique across
  unrelated assistant turns; only that each open id is closed before another
  assistant or user turn
