# agent-retry-argument-drift-detector

Pure-stdlib detector that catches when **a tool call's arguments drift across retry attempts**. A retry is supposed to be byte-identical to the original attempt; anything else is *not* a retry — it is a different call wearing a stolen idempotency key.

## The bug class this catches

When an agent retries a failed tool call, the orchestrator usually reuses the original `idempotency_key` (or derives one from the canonical-args hash). That contract holds **only if the args are actually identical**. In production, three failure modes silently break the contract:

1. **Ghost edits.** Between the first throw and the catch, the planner runs one more reasoning step. The retry's `args` reflect the *new* plan, not the original one. Result: `write_file(path="/a", content="v1")` becomes `write_file(path="/a", content="v2")` on attempt 2 — and the user sees `v2` even though the audit log says "we just retried `v1`".

2. **Type drift.** Caller emits `amount=100` (int) on attempt 1 and `amount=100.0` (float) on attempt 2. Same numeric value, but the canonical JSON differs (`100` vs `100.0`), so the idempotency-key hash differs, so the payment processor charges twice.

3. **Tool swap mid-call.** A model-fallback ladder kicks in between attempts. Attempt 1 calls `embed_v1`; attempt 2 calls `embed_v2` under the same `call_id`. The cache, the idempotency layer, and the audit log all assume one tool per call_id. Now they all lie.

This template is the **read** side of `tool-call-idempotency-key`: that template guarantees *if* the args match *then* the call is deduped; this template *verifies* the args actually match.

## What it does

`detect(attempts)` groups attempts by `call_id`, walks each group in `attempt_no` order, and emits one `DriftFinding` per drift event. Findings are sorted `(call_id, kind, detail)` so two runs over identical input produce byte-identical output (cron-friendly diffing).

Finding kinds:

| kind                     | meaning                                                                 |
| ------------------------ | ----------------------------------------------------------------------- |
| `tool_changed`           | attempt N's `tool` differs from attempt 1's `tool`                      |
| `key_added`              | attempt N has an arg key that attempt 1 did not                         |
| `key_removed`            | attempt 1 had an arg key that attempt N does not                        |
| `value_changed`          | same key, same type, different canonical-JSON value                     |
| `type_changed`           | same key, different Python type (int↔float, str↔int, bool↔int, etc.)    |
| `duplicate_attempt_no`   | two attempts share the same `attempt_no` within one `call_id`           |
| `non_dense_attempt_no`   | `attempt_no` jumps (e.g. 1, 3 with no 2) — caller lost an attempt record |

`fingerprint_attempt(a)` returns a 12-hex-char hash of `(tool, canonical_args)`. Two attempts with the same fingerprint are byte-identical retries; different fingerprints inside one `call_id` is the bug this template catches. Useful as a one-line operator probe in a log pipeline.

## Design choices worth defending

- **Diff against attempt 1, not against the previous attempt.** Attempt 1 is the *intent*. If attempts 2 and 3 both drift but in the same way, that is two findings, not one — both attempts violated the original intent.
- **`bool` is `bool`, not `int`.** Python's `True == 1` and `isinstance(True, int)` is a footgun that would suppress the very class of finding this template exists for. We override that.
- **Float vs int is a `type_changed`, not a `value_changed`.** The hashing layer cares about the bytes, not the math; `100 != 100.0` in canonical JSON.
- **`non_dense_attempt_no` is a finding, not a hard error.** Missing attempt records happen (host crash between throw and log flush), but the operator must see them — silent "attempt 1 then attempt 3" hides the question "what did attempt 2 do".
- **Pure function over an in-memory list.** No I/O, no clocks, no transport. Replayable from any JSONL of attempts.

## Usage

```python
from detector import Attempt, detect

attempts = [
    Attempt("call-1", 1, "http_get", {"url": "https://x.test", "timeout_s": 5}),
    Attempt("call-1", 2, "http_get", {"url": "https://x.test", "timeout_s": 5}),  # clean
    Attempt("call-2", 1, "charge_card", {"card_id": "tok_a", "amount": 100}),
    Attempt("call-2", 2, "charge_card", {"card_id": "tok_a", "amount": 100.0}),  # type drift
]

report = detect(attempts)
print(report.ok)               # False
for f in report.findings:
    print(f.call_id, f.kind, f.detail)
```

## Worked example

`example.py` runs 5 calls (11 attempts total): one clean retry plus one example of each drift class. Run it:

```
$ python3 example.py
```

Verbatim output:

```
# Attempt fingerprints (same fingerprint within one call_id == clean retry)
  call-001 attempt=1 tool=http_get     fp=4d9e86977a8f
  call-001 attempt=2 tool=http_get     fp=4d9e86977a8f
  call-001 attempt=3 tool=http_get     fp=4d9e86977a8f
  call-002 attempt=1 tool=write_file   fp=e5e97abc0347
  call-002 attempt=2 tool=write_file   fp=7c0e70d08f48
  call-003 attempt=1 tool=charge_card  fp=cd25eb6b4dc2
  call-003 attempt=2 tool=charge_card  fp=30e888052b15
  call-004 attempt=1 tool=search_index fp=d1f23f9939dc
  call-004 attempt=2 tool=search_index fp=fbeab50e348c
  call-005 attempt=1 tool=embed_v1     fp=367e50c71210
  call-005 attempt=3 tool=embed_v2     fp=b02843cfd833

# Drift report: calls_checked=5 attempts_checked=11 ok=False
# Findings (5):
  [call-002] value_changed: attempt 2: arg /content value drifted (first="draft v1", this="draft v2")
  [call-003] type_changed: attempt 2: arg /amount type int->float (first=100, this=100.0)
  [call-004] key_added: attempt 2: arg /max_results added (was absent at attempt 1)
  [call-005] non_dense_attempt_no: missing attempt_no(s): [2]
  [call-005] tool_changed: attempt 3: tool='embed_v2' (first attempt used 'embed_v1')

# All runtime invariants pass.
```

Note `call-001` produces zero findings — three attempts, three identical fingerprints, the happy path. Every other call produces exactly the finding its scenario was designed to surface.

## Composes with

- **`tool-call-idempotency-key`** — that template *enforces* the contract; this template *audits* whether callers are honoring it. Run this nightly over the previous day's attempt log and any output is a real bug.
- **`tool-call-replay-log`** — the JSONL it produces is exactly the input shape this detector wants. Stream it through and you get drift findings essentially for free.
- **`tool-call-retry-envelope`** — the envelope is *responsible* for not mutating args between attempts; this detector verifies it actually doesn't.
- **`structured-error-taxonomy`** — `value_changed` / `type_changed` / `key_added` / `key_removed` → `attribution=tool` (the orchestrator is buggy); `tool_changed` → `attribution=host` (the fallback ladder is misconfigured); `duplicate_attempt_no` → `do_not_retry` (the log itself is corrupt).
- **`agent-decision-log-format`** — one log line per finding, sharing `call_id`.
