# agent-tool-call-argument-key-typo-detector

Catch the common LLM failure where an agent calls a tool with a near-miss
argument key (`file_path` instead of `path`, `queryString` instead of
`query`, `max_token` instead of `max_tokens`) by comparing emitted argument
keys against the tool's expected schema.

## What it is

A standalone Python script that reads a JSON document describing tool
schemas plus a list of attempted tool calls, and emits a per-call report of
suspect argument keys with suggested corrections. Stdlib only.

## When to use it

Tool-calling agents fail in three characteristic ways on argument keys:

1. **Casing/punctuation drift** — `maxTokens` vs `max_tokens`,
   `file.path` vs `file_path`.
2. **Substring drift** — the model wraps an extra concept around the real
   key (`file_path` for `path`, `queryString` for `query`).
3. **Single-character typos** — `pat` for `path`, `max_result` for
   `max_results`.

Use this detector:

- As a post-hoc analyzer over tool-call traces to quantify typo rates per
  prompt/model
- Inline (before dispatching the call) to auto-correct or to raise a
  structured "did you mean X?" error back to the model
- In eval harnesses to gate "agent quality" on argument-fidelity, not just
  outcome

## How to invoke

```
python3 detect.py < calls.json
```

- Reads JSON from stdin (see schema below)
- Writes a JSON report to stdout
- Exits `0` if every call uses only known keys, `2` otherwise

## Input schema

```json
{
  "tools": {
    "<tool_name>": {
      "expected": ["key1", "key2"],
      "required": ["key1"]
    }
  },
  "calls": [
    {"tool": "<tool_name>", "args": {"key": "value"}}
  ]
}
```

## Detection layers (in order)

1. **Normalization** — strip case + non-alphanumerics; if the unknown key
   normalizes to an expected key, suggest it.
2. **Substring** — if an expected key (≥3 chars) is contained in the
   unknown key, suggest it. Catches `file_path → path`,
   `queryString → query`.
3. **Edit distance** — Levenshtein ≤ `max(1, len(key)//4)`. Catches
   `pat → path`, `max_result → max_results`.

When a suspect's suggestion matches a missing required key, it's tagged
`likely_typo_of_required: true` — the highest-signal flag.

## Worked example

Input (`example_input.json`):

```json
{
  "tools": {
    "read_file": {
      "expected": ["path", "offset", "limit"],
      "required": ["path"]
    },
    "search": {
      "expected": ["query", "max_results", "include"],
      "required": ["query"]
    },
    "edit": {
      "expected": ["path", "old_string", "new_string"],
      "required": ["path", "old_string", "new_string"]
    }
  },
  "calls": [
    {"tool": "read_file", "args": {"file_path": "/tmp/x", "limit": 50}},
    {"tool": "search", "args": {"queryString": "needle", "max_result": 10}},
    {"tool": "edit", "args": {"path": "/a", "old_string": "x", "new_string": "y"}},
    {"tool": "read_file", "args": {"pat": "/tmp/y"}},
    {"tool": "unknown_tool", "args": {"foo": 1}}
  ]
}
```

Run:

```
$ python3 detect.py < example_input.json; echo "EXIT=$?"
```

Verbatim output:

```
{
  "calls_analyzed": 5,
  "calls_with_issues": 4,
  "findings": [
    {
      "tool": "read_file",
      "suspects": [
        {
          "key": "file_path",
          "suggested": "path",
          "reason": "substring",
          "distance": 4,
          "likely_typo_of_required": true
        }
      ],
      "missing_required": [
        "path"
      ]
    },
    {
      "tool": "search",
      "suspects": [
        {
          "key": "queryString",
          "suggested": "query",
          "reason": "substring",
          "distance": 6,
          "likely_typo_of_required": true
        },
        {
          "key": "max_result",
          "suggested": "max_results",
          "reason": "edit-distance",
          "distance": 1
        }
      ],
      "missing_required": [
        "query"
      ]
    },
    {
      "tool": "edit",
      "suspects": [],
      "missing_required": []
    },
    {
      "tool": "read_file",
      "suspects": [
        {
          "key": "pat",
          "suggested": "path",
          "reason": "edit-distance",
          "distance": 1,
          "likely_typo_of_required": true
        }
      ],
      "missing_required": [
        "path"
      ]
    },
    {
      "tool": "unknown_tool",
      "error": "unknown-tool",
      "args": [
        "foo"
      ]
    }
  ]
}
EXIT=2
```

The four interesting cases — substring drift on `file_path` and
`queryString`, single-edit typo on `max_result` and `pat`, plus the
unknown tool — all surface with actionable suggestions, and the
`likely_typo_of_required` flag tells you which suspects are blocking
required arguments versus merely typo'd optionals.
