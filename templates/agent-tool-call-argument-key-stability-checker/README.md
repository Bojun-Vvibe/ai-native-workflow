# agent-tool-call-argument-key-stability-checker

Pure stdlib auditor for *argument-key drift* across a sequence of
agent tool calls. The agent calls the same tool name with a
slightly different set of argument keys across calls — even when
the *intent* is identical — and the call still works because the
tool router is permissive. Then a downstream change tightens the
router and yesterday's traces stop replaying.

This template treats the **first call to each tool name as the
baseline** and reports every drift relative to that baseline. Use
it on:

- a captured agent trace (one tool call per JSONL line);
- a prompt-replay corpus, to assert the model's argument shape is
  stable across N seeds;
- the diff between yesterday's and today's trace, to catch a new
  drift introduced by a prompt change.

Five finding classes:

- **`key_added_after_baseline`** — call N introduces a key not
  present in call 0 for the same tool. Reports the baseline
  call_index in `detail`.
- **`key_dropped_after_baseline`** — call N is missing a key that
  was present in call 0. The mirror of the above.
- **`key_alias_pair`** — across the trace, two keys for the same
  tool look like aliases. Two sub-rules:
  - *Levenshtein ≤ 1* (catches typos like `path` vs `paths`,
    `limt` vs `limit`); detail = `levenshtein<=1`.
  - *Known abbreviation table* (catches `q`/`query`, `p`/`path`,
    `id`/`identifier`, `msg`/`message`, etc.); detail =
    `known_abbreviation`. Reported with `call_index = -1` so it
    sorts to the top per tool.
- **`value_type_changed`** — same tool, same key, but the JSON
  type of the value changed across calls (`str` → `list`,
  `int` → `str`). Detail records the prior type and the
  call_index where the change first appears.
- **`key_order_unstable`** — the JSON key order across calls of
  the same tool varies, restricted to the keys common to baseline
  and the current call. Strong signal that the model is
  reconstructing the argument object instead of templating it —
  correlates empirically with quality drops on the same task.

## When to use

- CI assertion on a prompt-replay corpus: "for tool `search`, the
  model must call with exactly the keys `{query, limit}` across
  all 50 fixtures." Drift surfaces immediately.
- Forensic pass on a single bad trace: was the regression
  upstream (model emitted `q` instead of `query`) or downstream
  (router stopped accepting `q`)?
- Pre-merge gate on a tool schema change: re-run the baseline
  trace through the template, confirm `key_added_after_baseline`
  matches the new field exactly and there is no
  `value_type_changed` collateral damage.

## When NOT to use

- This is **not** a JSON Schema validator. It does not know what
  the tool's *declared* argument shape is — it only knows the
  shape of call 0. If call 0 is itself wrong, every other call
  inherits the wrongness as the baseline. Pair with a real
  schema validator if you have one.
- It does **not** dedupe semantically equivalent argument
  reorderings (e.g. `{a:1,b:2}` vs `{b:2,a:1}` are reported as
  `key_order_unstable`). That's by design — see "Design choices".
- The `key_alias_pair` abbreviation table is fixed and English.
  Edit `_COMMON_ABBREV` for domain-specific aliases (`acct`/
  `account`, `req`/`request`).

## Design choices worth knowing

- **First call wins as baseline.** Cheaper than computing a
  consensus shape, and matches the operator's mental model:
  "compared to the first time I saw this tool called, what
  changed?" Re-order the input if you want a different baseline.
- **`key_order_unstable` is a separate finding from a key
  add/drop.** A call that adds a key *and* re-orders will produce
  two findings, not one. The taxonomy distinction matters because
  the *fix* lives in different layers (prompt template for order,
  tool schema clarification for keys).
- **`key_alias_pair` is per-tool, not global.** Two tools can
  legitimately use `q` and `query` for different concepts; we
  only flag when both appear under the same tool's call history.
- **Findings are sorted `(tool, call_index, kind, key)`.** Two
  runs over the same input produce byte-identical output, so
  cron-driven alerting can diff yesterday's report against
  today's without false-positive churn.

## Usage

```
python3 validator.py path/to/trace.jsonl
# or
cat trace.jsonl | python3 validator.py
```

Each input line is `{"tool": "<name>", "args": {...}}`. Exit code
`0` if no findings, `1` if any finding, `2` on usage error.
Findings are printed as a JSON array on stdout.

## Worked example

`examples/example.py` embeds 7 calls — 5 `search` calls that
exercise the alias pair `q`/`query`, a type flip on `limit`, an
extra `filter` key, and a key-order shuffle; plus 2 `fetch` calls
that are perfectly consistent (and therefore emit zero findings,
proving the validator does not noise on a stable tool).

Run:

```
$ python3 examples/example.py
```

Output:

```
[
  {
    "tool": "search",
    "call_index": -1,
    "kind": "key_alias_pair",
    "key": "q|query",
    "detail": "known_abbreviation"
  },
  {
    "tool": "search",
    "call_index": 2,
    "kind": "key_added_after_baseline",
    "key": "q",
    "detail": "baseline_call=0"
  },
  {
    "tool": "search",
    "call_index": 2,
    "kind": "key_dropped_after_baseline",
    "key": "query",
    "detail": "baseline_call=0"
  },
  {
    "tool": "search",
    "call_index": 3,
    "kind": "value_type_changed",
    "key": "limit",
    "detail": "int@call0->str"
  },
  {
    "tool": "search",
    "call_index": 4,
    "kind": "key_added_after_baseline",
    "key": "filter",
    "detail": "baseline_call=0"
  },
  {
    "tool": "search",
    "call_index": 4,
    "kind": "key_order_unstable",
    "key": "limit,query,filter",
    "detail": "baseline_order=query,limit"
  },
  {
    "tool": "search",
    "call_index": 4,
    "kind": "value_type_changed",
    "key": "limit",
    "detail": "str@call3->int"
  }
]
```

Read top-to-bottom: the `key_alias_pair` row at `call_index = -1`
is the global per-tool finding, sorted to the top. Then call 2
both adds `q` and drops `query` — two rows reporting the same
underlying flip, kept distinct because the fix may need both
columns. Call 3 quietly turns the integer `10` into the string
`"10"`. Call 4 adds `filter`, re-orders the keys, *and* flips
`limit` back to int — three independent rows. The `fetch` tool
emits nothing — it's perfectly consistent across both calls.
