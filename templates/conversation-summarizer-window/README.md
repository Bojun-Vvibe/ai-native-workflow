# `conversation-summarizer-window`

Drop-and-summarize compactor for long-running agent conversations.
When the message log crosses a configurable fraction of the model's
context window, the oldest non-pinned messages are folded into a
single synthetic `summary` message in-place, leaving the recent tail
verbatim.

Pure stdlib. The token counter and the summarizer function are both
**injected** — no LLM calls inside the primitive — so the same
implementation works with any tokenizer and any summarization model,
and unit tests are deterministic.

## What it solves

Long agent sessions inevitably outgrow the context window. The two
naive options are both wrong:

- **Hard truncate** the oldest messages → you silently lose the
  original task description, decisions, and tool-call history.
- **Refuse new turns** at the limit → the agent dies on a long task.

The standard fix is "summarize the dropped tail into a single
synthetic message and keep the recent tail intact." This template
codifies that pattern with explicit, testable trigger rules and an
invariant: **pinned messages are never dropped**.

## When to use

- Multi-turn agent loops where the message list grows monotonically.
- You can identify a small set of always-keep messages (system prompt,
  user's original goal, task contract) and pin them.
- You have, or can build, a summarizer (LLM call, extractive, or
  rule-based — the primitive doesn't care).

## When NOT to use

- One-shot calls — there's nothing to compress.
- The "messages" are actually a structured plan (state machine, tree,
  graph). Summarize the plan in its own representation; don't flatten
  it into prose.
- You need lossless truncation (e.g. legal or audit replay). Use
  off-band storage (`tool-call-replay-log`) instead and keep the
  in-context view short by other means.

## Anti-patterns this prevents

- **"Drop oldest until under cap"** with no summary: silent context loss.
- **"Summarize everything every turn"**: re-summarizing already-stable
  history wastes tokens and degrades fidelity (lossy generation on
  lossy generation).
- **"Hide the system prompt in the same pool"** so it eventually gets
  summarized away. Pinning solves this — system prompts and anchor
  decisions live in `pinned=True` messages and the algorithm refuses
  to touch them.
- **"Summarize inside the primitive"** — couples this template to a
  specific LLM client. Dependency injection keeps it testable.

## Trigger rule

```
when total_tokens >= ceil(window_tokens * trigger_pct):
    drop oldest non-pinned messages,
    summarize them into one new "summary" role message,
    insert the summary just before the kept recent tail,
    until total_tokens <= ceil(window_tokens * target_pct)
```

Typical knobs: `trigger_pct=0.80`, `target_pct=0.50`. The gap
(`trigger - target`) prevents thrashing — every compression frees
real headroom before the next one fires.

## API surface

`SummarizerWindow(window_tokens, trigger_pct, target_pct, summarize_fn, token_counter=...)`

| Method | Returns | Notes |
|---|---|---|
| `total_tokens(msgs)` | `int` | Sum via `token_counter` over content. |
| `should_compress(msgs)` | `bool` | True iff at-or-over `trigger_pct * window_tokens`. |
| `compress(msgs)` | `(new_msgs, report)` | Pinned messages preserved in original order; one `summary` role message replaces the dropped block. |

`Message(role, content, pinned=False, msg_id="")` is a small
dataclass; `role` is free-form (`"system"`, `"user"`, `"assistant"`,
`"tool"`, plus `"summary"` for synthetic ones).

The `report` dict is structured for logging:

```json
{
  "compressed": true,
  "reason": "trigger_met",
  "tokens_before": 337,
  "tokens_after": 229,
  "dropped_count": 2,
  "dropped_ids": ["u1", "a1"],
  "summary_inserted_at": 1
}
```

## Files

- `summarizer.py` — pure-stdlib reference (`python summarizer.py demo`).
- `example.py` — end-to-end worked example with two compression rounds.

## Smoke test — `python3 example.py`

A 6-message conversation crosses the 320-token trigger; after
compression we add 3 more turns and trigger again. Note how round 2
drops the recent tail of round 1 (including the first synthetic
summary's tail neighbours) but the pinned system prompt stays at
position 0 throughout.

```
--- initial conversation ---
{"msg_id": "sys", "pinned": true, "role": "system", "tokens": 37}
{"msg_id": "u1", "pinned": false, "role": "user", "tokens": 76}
{"msg_id": "a1", "pinned": false, "role": "assistant", "tokens": 64}
{"msg_id": "u2", "pinned": false, "role": "user", "tokens": 76}
{"msg_id": "a2", "pinned": false, "role": "assistant", "tokens": 76}
{"msg_id": "u3", "pinned": false, "role": "user", "tokens": 8}
total_tokens=337

{"should_compress": true, "trigger_threshold": 320}

--- compression report (round 1) ---
{
  "compressed": true,
  "dropped_count": 2,
  "dropped_ids": [
    "u1",
    "a1"
  ],
  "reason": "trigger_met",
  "summary_inserted_at": 1,
  "tokens_after": 229,
  "tokens_before": 337
}

--- after compression (round 1) ---
{"msg_id": "sys", "pinned": true, "role": "system", "tokens": 37}
{"msg_id": "summary_of_2", "pinned": false, "role": "summary", "tokens": 32}
{"msg_id": "u2", "pinned": false, "role": "user", "tokens": 76}
{"msg_id": "a2", "pinned": false, "role": "assistant", "tokens": 76}
{"msg_id": "u3", "pinned": false, "role": "user", "tokens": 8}
total_tokens=229

--- after 3 more turns ---
{"msg_id": "sys", "pinned": true, "role": "system", "tokens": 37}
{"msg_id": "summary_of_2", "pinned": false, "role": "summary", "tokens": 32}
{"msg_id": "u2", "pinned": false, "role": "user", "tokens": 76}
{"msg_id": "a2", "pinned": false, "role": "assistant", "tokens": 76}
{"msg_id": "u3", "pinned": false, "role": "user", "tokens": 8}
{"msg_id": "a3", "pinned": false, "role": "assistant", "tokens": 121}
{"msg_id": "u4", "pinned": false, "role": "user", "tokens": 76}
{"msg_id": "a4", "pinned": false, "role": "assistant", "tokens": 61}
total_tokens=487

{"should_compress": true}

--- compression report (round 2) ---
{
  "compressed": true,
  "dropped_count": 5,
  "dropped_ids": [
    "u2",
    "a2",
    "u3",
    "a3",
    "u4"
  ],
  "reason": "trigger_met",
  "summary_inserted_at": 2,
  "tokens_after": 199,
  "tokens_before": 487
}

--- after compression (round 2) ---
{"msg_id": "sys", "pinned": true, "role": "system", "tokens": 37}
{"msg_id": "summary_of_2", "pinned": false, "role": "summary", "tokens": 32}
{"msg_id": "summary_of_5", "pinned": false, "role": "summary", "tokens": 69}
{"msg_id": "a4", "pinned": false, "role": "assistant", "tokens": 61}
total_tokens=199

{
  "final_total_tokens": 199,
  "pinned_still_at_top": true,
  "under_window": true
}
```

Things to notice:

- After round 1: pinned system prompt at index 0, synthetic summary
  at index 1 (replacing `u1, a1`), then the verbatim recent tail.
- Round 2 drops 5 messages including the recent tail of round 1, but
  importantly it does NOT drop the older `summary_of_2` — the
  algorithm leaves earlier summaries in place when room permits, so
  the chain of compressed history is preserved as a sequence of
  ever-coarser summaries. (If you'd rather collapse them, do that in
  your `summarize_fn`.)
- The pinned system prompt is at position 0 in every state. The
  invariant assertion in `example.py` enforces this.
- Token totals stay below `window_tokens=400` after every compression.

## Composition

- **`token-budget-tracker`** — the budget tracker decides whether you
  can *afford* a summarization call; this template decides *when* to
  call. The summary call itself spends tokens.
- **`prompt-cache-discipline-system-prompt`** — keep the pinned
  system prompt cache-friendly so each compressed-conversation turn
  still reuses the cached prefix.
- **`tool-call-replay-log`** — store the full untruncated history
  off-band; the in-context view is for the model, the replay log is
  for audits / re-runs.

## Non-goals

- No specific tokenizer (inject `token_counter`).
- No specific summarizer (inject `summarize_fn`).
- No async — the primitive is pure and synchronous; if your
  summarizer is async, wrap the call site, not the primitive.
- No automatic re-summarization of existing summaries (you can do
  that in your `summarize_fn` if you want a hierarchical scheme).
