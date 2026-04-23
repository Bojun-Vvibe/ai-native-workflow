# Template: Prompt fingerprinting

A small library + CLI that **fingerprints every prompt sent to a
model** and detects drift across runs of the same mission. The
fingerprint is a structured digest of:

- system prompt (full content hash + length)
- tools section (sorted name list, each with arg-schema hash)
- conversation prefix (turn-count-truncated content hash)
- model id and provider
- decoding params (`temperature`, `top_p`, `max_tokens`)

When two runs of the same mission produce different fingerprints, you
get a **diff explanation**: which component changed, by how much, and
how that breaks prompt cache reuse.

## Why this exists

"Same mission, but it's slower / more expensive / less accurate this
week" is one of the most common and most misdiagnosed complaints in
agent ops. The cause is almost always silent prompt drift:

- Someone reordered tools.
- A tool's arg schema gained a new optional parameter.
- The system prompt grew by 200 tokens because someone added a
  "remember to..." line that everyone forgets is there.
- A library bumped a default and your cache prefix shifted by 4
  characters.

Each of these breaks the prompt cache prefix. The model still works.
The bill goes up. The latency goes up. Nobody knows why.

Fingerprinting catches it deterministically: same fingerprint →
identical cache prefix; different fingerprint → here is the exact
component that drifted.

## When to use

- You run the same mission shape repeatedly (daily digest, PR
  triage, weekly audit) and want week-over-week comparability.
- You have multiple developers editing system prompts and tools.
- You're trying to improve cache hit rate (use with
  [`cache-aware-prompt`](../cache-aware-prompt/) and
  [`prompt-cache-discipline-system-prompt`](../prompt-cache-discipline-system-prompt/)).

## When NOT to use

- One-shot prompts with no continuity. Drift across one-shots is
  expected and meaningless.
- You don't control the system prompt (e.g. you call a hosted agent
  API and the provider injects). Fingerprint only what you control.

## Anti-patterns

- **Hashing only the system prompt.** Tools and decoding params
  break cache too. Hash the whole prefix package.
- **Hashing the *full* conversation.** Conversation grows; the
  fingerprint will always change. Truncate to a turn count or to a
  prefix length aligned with your cache breakpoint.
- **Whitespace-sensitive hashes for human-edited prompts.** A
  trailing newline change shouldn't register as drift if the
  semantic content is identical. Normalize whitespace before
  hashing.
- **Whitespace-INsensitive hashes when measuring cache impact.**
  The cache *is* whitespace-sensitive. If you're explaining a
  cache miss, you must hash with whitespace.

  Resolution: emit *both* (`semantic_hash` and `cache_hash`) and
  diff each.

- **Storing fingerprints only in memory.** Drift detection means
  comparing today's fingerprint to last week's. Persist them.
- **Diffing two prompts and printing 4kB of context.** A drift
  report is "system prompt grew by 312 chars (was 4,810 → now
  5,122); 0 lines removed, 8 lines added." The full diff goes in
  a sibling file.

## Files

- `src/fingerprint.py` — produces a fingerprint dict from a
  prompt-package input. Stable, stdlib-only.
- `src/diff.py` — diffs two fingerprints and emits a structured
  drift report.
- `src/cli.py` — `python -m cli fingerprint <input.json>` and
  `python -m cli diff <a.json> <b.json>`.
- `examples/prompt-pkg-v1.json` — week-1 prompt package.
- `examples/prompt-pkg-v2.json` — week-2, with one tool reordered
  and 12 tokens added to the system prompt.
- `examples/sample-fingerprint.json` — fingerprint of v1.
- `examples/sample-drift-report.md` — drift report for v1 → v2.

## Worked example

```bash
$ python3 -m src.cli fingerprint examples/prompt-pkg-v1.json
{
  "model": "claude-opus-4.7",
  "system_hash":     "9e2c…",
  "system_len":      4810,
  "tools_hash":      "a1b3…",
  "tool_names":      ["bash","edit","glob","grep","read","todowrite","write"],
  "decoding_hash":   "ab12…",
  "cache_hash":      "f7…",
  "semantic_hash":   "c4…"
}

$ python3 -m src.cli diff examples/prompt-pkg-v1.json examples/prompt-pkg-v2.json
DRIFT DETECTED
  system_prompt:   +12 tokens (4810 → 4822 chars)
  tools_order:     reordered (no schema change)
  decoding:        unchanged
  cache_hash:      9e2c → 4f1a   (cache prefix BROKEN — full re-prime expected)
  semantic_hash:   c40e → c40e   (same intent)
```

## Adapt this section

- Wire `fingerprint(pkg)` into your agent loop's session-start.
  Persist to `~/.cache/prompt-fingerprints/<mission-id>.jsonl`.
- Run `cli diff` weekly across the same mission's fingerprints; if
  `cache_hash` changed but `semantic_hash` didn't, you have a
  silent cache-busting drift to fix.
- Add a CI gate: PRs that touch system prompts must update an
  expected fingerprint file. Reviewers see the drift inline.
