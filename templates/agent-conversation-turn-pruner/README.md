# agent-conversation-turn-pruner

A stdlib-only pruner that compresses long agent conversations by dropping the *middle* — keeping system messages, the first K "anchor" turns (original task framing, key tool definitions, few-shot examples), and the last M "recent" turns (the agent's last action and its result). Optionally inserts a single elision marker so the model knows context was elided rather than confabulating that the conversation began in medias res.

## The problem

Naive history-management tactics for long agent loops:

- **Drop the oldest turns until you fit.** Sounds reasonable; immediately drops the *original user request* and the *tool-use few-shot example*. The agent loses grounding and starts inventing a different task than the one it was given.
- **Sliding window of the last N turns.** Same failure mode for the same reason. Worse: when the user pinned a critical fact ten turns ago ("the database is read-only"), the window will silently forget it and the agent will issue writes.
- **Summarize everything past turn N.** Now you have two problems: the agent's loss of grounding, plus a summary that may be wrong, plus extra round-trips and tokens spent producing the summary that you were trying to save.
- **Hand-craft per-loop logic.** Every mission ends up with bespoke pruning code that diverges, has different bugs, and is hard to reason about.

The shape that actually works on long missions is:

```
[system, system, ...]                    # always kept (priority -inf)
[first K non-system turns]               # anchors: task framing, tool defs
[<one elision marker, if we dropped any>]
[last M non-system turns]                # recents: agent's last action + result
```

The middle is where slop accumulates: failed tool retries, the model talking to itself, search results it already summarized, dead-end branches the agent abandoned. That band pays for itself when dropped. The anchors and recents are load-bearing and never touched.

A *single* explicit elision marker beats silent deletion: the model can reason "I see a gap" instead of treating the bridged head and tail as a continuous transcript.

## The shape of the solution

```python
from turn_pruner import Turn, PrunePolicy, prune

turns = [Turn("system", "..."), Turn("user", "..."), Turn("assistant", "..."), ...]
policy = PrunePolicy(
    keep_first=3,       # preserve original request + tool intro + first reply
    keep_last=4,        # preserve last 2 user/assistant exchanges
    max_total_tokens=8000,
    token_count_fn=my_real_tokenizer,
)
result = prune(turns, policy)

send_to_model(result.kept)
log_dropped(result.dropped, "elided_in_round_42")
```

`PruneResult` exposes:

- `kept` — the new turn list to send to the model.
- `dropped` — the turns that were dropped (route to `agent-trace-redaction-rules` for archival, or just discard).
- `marker_inserted` — whether an elision marker was added (false on conversations short enough that no pruning happened).
- `kept_token_count` / `dropped_token_count` — for cost reports.
- `decisions` — ordered list of human-readable decision strings, suitable for dropping straight into a step log so a reviewer can see *why* a turn was dropped.

## Conventions implemented

- **System turns are always kept.** They do not count against `keep_first` / `keep_last`. `max_total_turns` and `max_total_tokens` ceilings cannot evict them either.
- **`Turn(pinned=True)` is never dropped**, even from the middle band, even under token ceilings. This is the orchestrator's escape hatch for load-bearing tool results ("the security scan finding") that happen to fall in the elidable region.
- **The elision marker is one synthetic system turn**, inserted between the kept head and the kept tail at the position where the drop happened. Pass `elision_marker=None` to skip it (some models react badly to unfamiliar system messages mid-stream).
- **Token ceilings drop oldest-eligible-first.** When `max_total_tokens` forces additional drops beyond the band logic, the pruner sacrifices anchors before recents — the recents are usually the more important band for the *next* model call.
- **Caller owns tokenization.** Default `token_count_fn` is whitespace-split (deterministic for tests, no external deps). Production callers pass a real tokenizer — the result is a single number per turn so any tokenizer works.
- **Pure value object.** No I/O, no clocks, no global state. The pruner is fully testable with handcrafted `Turn` lists.

## When to use it

- Any agent loop that runs long enough that the conversation grows past the model's context window (or past your prompt-cache budget).
- Sitting *before* `prompt-token-budget-allocator` / `prompt-token-budget-trimmer`: this template decides *which turns* to keep; those decide *how many tokens each kept section gets*.
- As the policy layer behind `prompt-cache-discipline-system-prompt`'s "keep prefix stable, append-only history" rule — pruning happens at the tail of the prefix, then the prefix-cache key is computed over the *kept* turn list.

## When NOT to use it

- For *summarization* of dropped turns. This template drops; it doesn't summarize. If you need a summary in the elision marker, generate it separately and pass it as `elision_marker="..."`.
- For semantic deduplication ("the agent retried the same tool 5 times — collapse"). That's a different pre-pass that happens *before* this one, since it operates on the contents of pairs of turns rather than position.
- For *per-token* trimming inside a single overlong turn. Use `prompt-token-budget-trimmer` for that — it trims content within a section; this trims sections themselves.

## Failure modes the implementation defends against

1. **Anchors silently dropped.** `keep_first` is honored unconditionally before any token math runs. Token ceilings drop oldest *next*, but they cannot evict pinned or system turns.
2. **Recents silently dropped.** `keep_last` is similarly honored before token math.
3. **Pinned middle turn lost to band pruning.** Worked example proves a `pinned=True` security-scan tool result in the middle survives a `keep_first=2, keep_last=2` policy.
4. **No-op pruning still inserts a marker.** A short conversation that fits cleanly returns `marker_inserted=False` so the model isn't told context was elided when it wasn't.
5. **Token ceiling unsatisfiable.** If pinned + system turns alone exceed the token budget, the pruner stops dropping and emits a `budget breached at N tokens` decision rather than corrupting the kept set further.
6. **Duplicate / out-of-order role sequences.** The pruner doesn't re-order or deduplicate — it preserves the original turn order in `kept`, so the model sees a consistent dialogue shape.

## Files in this template

- `turn_pruner.py` — stdlib-only reference (~170 lines), one `prune()` function + dataclasses.
- `worked_example.py` — four scenarios: short conversation that needs no pruning, long conversation with mid-band drop + marker, pinned middle turn surviving band pruning, token-ceiling forcing additional drops past the band.

## Sample run

```text
== short_no_prune_needed ==
  kept: 5 turn(s)  dropped: 0 turn(s)  marker_inserted=False
  kept_tokens=34  dropped_tokens=0
  kept roles: ['system', 'user', 'assistant', 'user', 'assistant']
  decisions:
    - split: 1 system turn(s), 4 conversation turn(s)
    - no middle to drop (head+tail covers all conversation turns)

== long_middle_drop ==
  kept: 7 turn(s)  dropped: 7 turn(s)  marker_inserted=True
  kept_tokens=61  dropped_tokens=56
  kept roles: ['system', 'user', 'assistant', 'system', 'user', 'assistant', 'user']
  decisions:
    - split: 1 system turn(s), 12 conversation turn(s)
    - middle: 7 turn(s), 0 pinned (kept), 7 unpinned (dropped)
    - inserted elision marker at convo position 2

== pinned_middle_survives ==
  kept: 7 turn(s)  dropped: 5 turn(s)  marker_inserted=True
  kept_tokens=57  dropped_tokens=28
  kept roles: ['system', 'user', 'assistant', 'tool', 'system', 'user', 'assistant']
  decisions:
    - split: 1 system turn(s), 10 conversation turn(s)
    - middle: 6 turn(s), 1 pinned (kept), 5 unpinned (dropped)
    - inserted elision marker at convo position 3

== token_ceiling_drops_more ==
  kept: 4 turn(s)  dropped: 4 turn(s)  marker_inserted=True
  kept_tokens=102  dropped_tokens=680
  kept roles: ['system', 'system', 'user', 'assistant']
  decisions:
    - split: 1 system turn(s), 6 conversation turn(s)
    - middle: 1 turn(s), 0 pinned (kept), 1 unpinned (dropped)
    - inserted elision marker at convo position 2
    - max_total_tokens=200 ceiling: kept 102 tokens
```

The `pinned_middle_survives` scenario is the one that justifies the `pinned=True` flag: a `keep_first=2, keep_last=2` policy would normally drop *all* 6 middle turns, but the pinned `tool` turn carrying the security-scan finding survives — its role appears in the kept-roles list (`'tool'`) sandwiched between the head anchors and the elision marker. The agent sees the security finding it must act on, even though five other middle turns of file-reading were correctly elided.

The `token_ceiling_drops_more` scenario shows the second-stage drop: band pruning alone would have kept 5 conversation turns, but a 200-token ceiling forces the oldest of those (the 50-token user turn at position 0 and a 200-token assistant reply at position 1) to be sacrificed too, leaving only the most recent user/assistant exchange plus the system anchor and the elision marker. The recents are preserved, the anchors fall first, and `kept_tokens=102` lands cleanly under the 200 budget.

## Composes with

- **`prompt-cache-discipline-system-prompt`** — pruning happens at the tail of the cached prefix; the prefix-cache key is computed over the *kept* turn list, so a stable head and pinned middle preserve cache hits.
- **`prompt-token-budget-allocator`** — this template chooses which turns survive; the allocator divides the remaining context budget across the kept turns + the new user message + retrieved docs.
- **`prompt-token-budget-trimmer`** — for trimming content *inside* an overlong individual turn after pruning has chosen which turns to keep.
- **`agent-trace-redaction-rules`** — dropped turns can be archived through the redactor before persistence.
- **`agent-decision-log-format`** — the `decisions` list drops straight into a step log so a reviewer can audit the prune decisions for any given mission step.
