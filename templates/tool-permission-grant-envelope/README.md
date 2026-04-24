# tool-permission-grant-envelope

Pre-call authorization envelope for agent tool use. Declarative grants
say *what an agent is allowed to do*; a deterministic decision engine
turns a (grants, usage, request) tuple into `allow` or `deny(reason=…)`
with no side effects.

This is the **pre-flight** layer. The other runtime-control templates
fire on calls that have already cleared this gate:

| Template | Question it answers |
|---|---|
| `tool-permission-grant-envelope` (this) | *Is this agent allowed to call this tool with these args at all?* |
| `agent-cost-budget-envelope` | Can it afford the call? |
| `tool-call-circuit-breaker` | Is the tool itself currently healthy? |
| `tool-call-retry-envelope` | If the call fails, can it be safely re-attempted? |

A request that passes all four is the only kind that should reach the
tool implementation.

## Problem

Agent CLIs typically gate tool use with one of two unfortunate shapes:

1. **Coarse boolean per tool.** "Allow `fs.write`? y/N." Once
   approved, the tool is allowed everywhere, with any arguments,
   forever. This is what burns down `~/.ssh/authorized_keys` when an
   agent loops.
2. **Hard-coded policy in host code.** Permission lives inside the
   shell wrapper or plugin code. Adding a temporary scope (e.g. "let
   the migration mission write to `/tmp/mig-2026-04` only, max 50
   calls, expires in 1h") requires editing and redeploying the host.

The first is unsafe. The second is unmaintainable. Real agent hosts
need a declarative permission layer where:

- grants are data, not code;
- decisions are pure functions (replayable from a JSONL log);
- denial reasons are *specific* enough to drive UX (don't say "denied"
  when you mean "argument not allowlisted") and *stable* enough to
  drive metrics;
- a quota-exhausted grant on a tool the agent shouldn't be touching
  still reports the *real* reason (the tool not being in the grant),
  not a misleading "out of quota".

## Design

### The grant object

```json
{
  "grant_id": "g-fs-tmp-write",
  "agent_id": "mission-42",
  "tool": "fs.write",
  "scopes": ["write"],
  "max_calls": 10,
  "expires_at": 2000000000,
  "arg_allow": {"dir": ["/tmp/mission-42", "/tmp/mission-42/out"]},
  "revoked": false
}
```

Schema in [`schema/grant.schema.json`](schema/grant.schema.json).

Key constraints baked into the schema:

- `grant_id` is stable and **never reused**. Revoking and re-granting
  the same logical permission requires a new id. This makes the JSONL
  event log replayable indefinitely without ambiguity.
- `tool` is exact-match, no wildcards. Wildcards are how you accidentally
  grant `fs.*` thinking you only granted `fs.read`.
- `arg_allow` is a per-field allowlist; if the field is listed, the
  request **must** supply it and the value must be in the allowlist.

### Decision precedence

Decisions are deterministic and order-independent (the engine sorts
candidate grants by `grant_id` before considering them). Within each
candidate grant the checks fire in this order, surfacing the
most-specific failure reason:

1. `no_grant` — agent has no grants at all
2. `tool_not_in_grant` — no grant for this tool
3. `revoked` — grant has the sticky revoke bit set
4. `expired` — `now >= expires_at`
5. `scope_not_granted` — required scope missing (with `missing` list)
6. `argument_not_allowed` — `arg_allow` field not satisfied
7. `call_quota_exhausted` — `usage[grant_id] >= max_calls`
8. `ok` — allow

Quota check is **last** on purpose. If an agent hammers a tool it was
never granted, you want every denied call to report `tool_not_in_grant`,
not have the first N report it correctly and the rest silently flip to
`call_quota_exhausted` once the engine starts caring about counters.

### Replay model

The engine itself never mutates state. The host pattern is:

```
grants  = load_grants("grants.json")
usage   = replay_log(grants, "events.jsonl")          # rebuild counters
decision = decide(grants, usage, request)
if decision.allowed:
    usage[decision.grant_id] += 1
    append_event(decision.grant_id, request.now)      # persist
```

Because the engine is pure, the same `decide()` call against the same
`(grants, usage, request)` always returns the same decision — useful
for unit tests, audit re-runs, and "would this have been allowed
yesterday" what-ifs.

## Files

- [`grant_engine.py`](grant_engine.py) — stdlib-only reference engine + CLI
- [`schema/grant.schema.json`](schema/grant.schema.json) — JSON Schema (draft 2020-12)
- [`examples/example_1_path_allowlist.py`](examples/example_1_path_allowlist.py) — `arg_allow`, scope escalation, tool-not-granted
- [`examples/example_2_quota_and_expiry.py`](examples/example_2_quota_and_expiry.py) — JSONL replay, quota exhaustion, expiry

## CLI usage

```sh
python3 grant_engine.py grants.json events.jsonl request.json
```

Exits `0` if allowed, `1` if denied (any reason), `2` on usage error.
Always prints the full JSON decision on stdout so the host can log it
without re-evaluating.

## Worked examples

### Example 1 — `arg_allow`, tool-not-granted, scope escalation

```
$ python3 examples/example_1_path_allowlist.py
req 1: tool=fs.write args={"dir": "/tmp/mission-42", "name": "a.txt"}
  -> {"allowed": true, "detail": {"remaining": 9}, "grant_id": "g-fs-tmp-write", "reason": "ok"}

req 2: tool=fs.write args={"dir": "/etc", "name": "passwd"}
  -> {"allowed": false, "detail": {"field": "dir", "value": "/etc"}, "grant_id": "g-fs-tmp-write", "reason": "argument_not_allowed"}

req 3: tool=fs.delete args={"dir": "/tmp/mission-42"}
  -> {"allowed": false, "detail": {"tool": "fs.delete"}, "reason": "tool_not_in_grant"}

req 4: tool=fs.write args={"dir": "/tmp/mission-42", "name": "ok.txt"}
  -> {"allowed": false, "detail": {"missing": ["admin"]}, "grant_id": "g-fs-tmp-write", "reason": "scope_not_granted"}
```

What this shows:

- req 1 — clean allow. `remaining` reflects post-decrement (9 left
  after this one).
- req 2 — `/etc` is not in the dir allowlist, denied with a
  field-anchored reason (UX can offer "request a wider scope").
- req 3 — `fs.delete` is a different tool; engine reports the tool
  problem, not "no quota for fs.delete".
- req 4 — agent asked for `["write", "admin"]`; grant only has
  `["write"]`. Denied with `missing=["admin"]` so the host can prompt
  to upgrade the grant rather than silently failing.

### Example 2 — JSONL replay, quota exhaustion, expiry ordering

```
$ python3 examples/example_2_quota_and_expiry.py
replayed usage: {'g-net-search': 2}

req 5: now=1700000100
  -> {"allowed": true, "detail": {"remaining": 0}, "grant_id": "g-net-search", "reason": "ok"}

req 6: now=1700000110
  -> {"allowed": false, "detail": {"max": 3, "used": 3}, "grant_id": "g-net-search", "reason": "call_quota_exhausted"}

req 7: now=1700000400
  -> {"allowed": false, "detail": {"expires_at": 1700000300, "now": 1700000400}, "grant_id": "g-net-search", "reason": "expired"}

final usage: {'g-net-search': 3}
```

What this shows:

- The two prior allowed calls were rebuilt from disk
  (`replayed usage: {'g-net-search': 2}`) — engine has no memory of
  its own.
- req 5 is the third (last) allowed call; `remaining=0` after it.
- req 6 trips the quota with a precise `used`/`max` payload.
- req 7 is *also* over quota, but the engine reports `expired` because
  expiry is checked *before* the quota counter — the operator caring
  about "why was this denied" wants the time-bound reason, not a stale
  counter.

## Composition

- Pair with [`agent-decision-log-format`](../agent-decision-log-format/)
  by recording the decision (`reason`, `grant_id`, `detail`) in the
  step's `tools_called` payload.
- Pair with [`agent-trace-redaction-rules`](../agent-trace-redaction-rules/)
  before exporting the JSONL event log — `agent_id` and per-arg values
  may need redaction.
- Pair with [`agent-cost-budget-envelope`](../agent-cost-budget-envelope/)
  by running the budget check **after** this gate. A denied-by-permission
  call should not consume the cost ledger.
