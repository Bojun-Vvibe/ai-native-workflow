# Template: Token-budget tracker

A small Python module + JSONL log format + reporting CLI for tracking
**how many tokens (and dollars) an agent session consumed**, broken
down by model, by phase, by tool call, and by cache hit / miss /
write. Designed to be dropped into any agent loop with three lines of
code, and to produce a daily/weekly cost report you can actually act
on.

## Why this exists

If you run AI coding agents continuously, your monthly bill is
dominated by 2–3 missions you can name. The other 95% of the bill is
"miscellaneous." A budget tracker turns the miscellaneous into a
named breakdown so you can ask:

- Which model burned the most input tokens this week?
- Which tool call (read_file? bash?) is the most expensive in a
  typical mission?
- What's my cache hit rate trend over the last 30 days?
- Which mission types blow through their estimated budget by 2×+?

Without this, "the bill is high" is a vague feeling. With this, "the
bill is high because mission-type X uses 3.2× more tokens than
mission-type Y for similar work" is an actionable fact.

## When to use

- You spend > $50/month on agent inference and want a cost story.
- You run multiple **mission types** and want to compare their costs.
- You're optimizing for cache hit rate (use with
  [`cache-aware-prompt`](../cache-aware-prompt/)).
- You're choosing between models and want a real apples-to-apples
  cost comparison on your actual workload.

## When NOT to use

- You're a hobbyist with a fixed monthly budget cap and don't care
  about the breakdown — your provider's billing dashboard is enough.
- Your provider already exposes per-request usage telemetry that you
  query (e.g., LiteLLM with a database backend) — use that instead
  of building a parallel system.
- You only run one-shot completions, not multi-turn agents — the
  tracker assumes a "session" abstraction that one-shots don't have.

## Anti-patterns

- **Tracking only output tokens.** Input tokens dominate cost in
  agent workloads (often 10–30× output volume). If you only track
  output, you'll mis-estimate by an order of magnitude.
- **Hardcoded prices.** Provider prices change (often downward,
  sometimes upward). Pin price strings in a `prices.json` you can
  bump, not in the code.
- **Per-request granularity but no session id.** A session is a unit
  of work; without a session id you can't ask "how much did *this
  mission* cost?" Always log a session id.
- **No cache breakdown.** Without `cache_read` vs `cache_write` vs
  `fresh_input`, you can't measure the value of your cache work.
  Three counters minimum, not one.
- **Reporting only totals.** Totals tell you the bill. The
  *breakdown* (by model × phase × tool) tells you what to fix.
- **Silent overflow on hidden retries.** If your agent retries a
  failed call, the retry usually costs full price. Log retries as
  separate entries with a `retry_of` field, not folded into the
  parent.

## Files

- `src/budget.py` — the tracker. Three public functions:
  `start_session()`, `record(...)`, `report(...)`. Pure stdlib + the
  provider SDK of your choice for usage extraction.
- `src/prices.json` — pinned per-MTok prices for common models.
  Bump as providers update.
- `src/report.py` — CLI: `python -m report --days 7 --by model,tool`.
  Produces a markdown table.
- `examples/sample-session.jsonl` — what a real session log looks
  like (10 turns, mixed models, with a deliberate retry).
- `examples/sample-report.md` — what `report.py` produces from the
  sample session.

## The log format

Each tracked event is one JSON line. The fields are intentionally
flat so you can grep / `jq` without ceremony.

```json
{
  "ts": "2026-04-23T14:32:01.123Z",
  "session_id": "mission-foo-2026-04-23-001",
  "phase": "scout",
  "tool": "read_file",
  "model": "claude-sonnet-4-5-20250929",
  "provider": "anthropic",
  "input_total": 18432,
  "cache_read": 16000,
  "cache_write": 0,
  "fresh_input": 2432,
  "output": 1024,
  "elapsed_sec": 2.341,
  "retry_of": null
}
```

The `phase` field is the mission's logical phase ("scout", "act",
"review") — entirely user-defined; the tracker does not interpret it.
Cost is computed at *report time* from `prices.json`, not stored, so
old logs re-cost correctly when prices change.

## Adapt this section

- `prices.json` — pin to the prices in effect on the day you start
  tracking. Bump when a provider changes them; old logs re-cost
  automatically because cost is computed at report time.
- `phase` and `tool` taxonomies — entirely yours. Some teams use
  `phase` for mission steps; others use it for "interactive" vs
  "batch" buckets.
- Storage backend — defaults to a JSONL file under
  `~/.local/share/token-budget/<yyyy-mm>/<session-id>.jsonl`. Swap
  for SQLite or a remote sink if you want cross-machine aggregation.
- Reporting cadence — `report.py` defaults to "last 7 days." Wire
  into a daily cron or a Slack post for a low-friction signal.
