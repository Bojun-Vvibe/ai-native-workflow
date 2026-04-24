# LOOP.md — Repair-loop state machine

The loop has four exit states and three transitions. Strict.

## States

| State | Meaning | Caller action |
|---|---|---|
| `parsed` | An attempt produced output that passed validation. | Use the parsed value. |
| `stuck` | Two attempts produced errors with the same fingerprint. | Either degrade or hard-fail. Do **not** retry; the model isn't going to discover a new answer. |
| `exhausted` | Reached `max_attempts` without parsing or stuck-detection (every attempt failed differently). | Same as `stuck` — degrade or hard-fail. The model is *trying* but can't satisfy the schema. |
| `expired` | Wall-clock `deadline_ms` elapsed mid-loop. | Treat as `exhausted` for action; treat as `expired` for cost accounting. |

## Transitions

```
                    +--------+
                    | start  |
                    +---+----+
                        |
                        v
                +-------+-------+
        +-----> | call_model    |
        |       +-------+-------+
        |               |
        |               v
        |       +-------+-------+    parses ok
        |       | validate      +-----------> [parsed]
        |       +-------+-------+
        |               |  fails validation
        |               v
        |       +-------+-------+    fp seen before
        |       | fingerprint   +-----------> [stuck]
        |       +-------+-------+
        |               |  new fingerprint
        |               v
        |       +-------+-------+    attempt > max  OR  elapsed > deadline
        |       | bump counters +-----------> [exhausted | expired]
        |       +-------+-------+
        |               |  ok to continue
        |               v
        |       +-------+-------+
        +-------+ render_hint   |
                +---------------+
```

## Defaults

| Setting | Default | Rationale |
|---|---|---|
| `max_attempts` | `4` | Empirically: 1 base + 1 typo-fix + 1 schema-nudge + 1 last chance. Beyond this the marginal probability of success drops below 5% and you're better off degrading. |
| `deadline_ms` | `30_000` | Long enough for a slow model on a large prompt; short enough that an interactive caller doesn't hang. |
| `stuck_threshold` | `2` | Two appearances of the same fingerprint = stuck. Setting it to `3` doesn't help (model isn't going to discover a new answer between attempts 2 and 3 if it didn't between 1 and 2). |

## Things the loop does NOT do

- **Backoff between attempts.** Repair turns are immediate.
  Backoff is for transport-layer retries (use
  `tool-call-retry-envelope` for that). A repair-loop retry
  isn't a transport retry.
- **Temperature manipulation.** Some implementations bump
  temperature on retry hoping for "different output." This
  defeats determinism and rarely helps for *schema* errors;
  the model knows the schema, it just made a mistake.
  Keep temperature pinned across the loop.
- **Prompt-rewriting.** Each repair turn appends a hint, never
  edits the original system prompt. Mutating the system prompt
  mid-loop breaks prompt-cache and breaks reproducibility.
