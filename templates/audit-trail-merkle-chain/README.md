# Template: audit-trail-merkle-chain

An append-only log for agent decisions where each entry's hash
includes the prior entry's hash. Tampering with any historical
record (or removing one, or reordering them) breaks the chain at
the point of tampering and every entry after it. The whole log is
verifiable in O(N) by replaying the chain; integrity is anchored
by publishing the **head hash** somewhere outside the log itself
(operator notebook, Slack pin, signed daily snapshot).

This template is the integrity counterpart to
`agent-decision-log-format` (which standardizes *what* a decision
record contains). The decision-log template answers "what fields";
this template answers "how do you know nobody edited the file".

## Why this exists

Three failure modes that show up the moment an agent's decision
log is used as evidence for anything (post-incident review,
auditor question, blame analysis, model-drift investigation):

1. **Quiet edits.** Someone (or a runaway script) opens the JSONL
   file, fixes a typo or "clarifies" a rationale. The file still
   parses; nothing flags it. Now the log is no longer evidence
   of what the agent actually did.
2. **Convenient deletions.** A failed-and-embarrassing decision
   gets snipped out before review. The line count drops by one;
   nothing flags it.
3. **Subtle reordering.** Two records get swapped (perhaps by a
   buggy log shipper). Causality is lost. Whatever incident
   timeline you reconstruct from this is wrong.

A merkle chain catches all three. Each entry stores
`prev_hash = sha256(prev_entry_canonical)` and
`entry_hash = sha256(canonical(entry_without_entry_hash))`.
Verification walks the file front-to-back recomputing both. Any
mismatch is reported with the exact entry index where the chain
broke.

## When to use it

- Agent decision logs intended for post-hoc audit.
- Tool-call ledgers where retroactive edits would be a problem.
- Cost / budget ledgers (pairs naturally with
  `agent-cost-budget-envelope`).
- Anywhere "did the agent really say that" might come up later.

When *not* to use it:

- Pure debug logs. Overhead with no audit purpose.
- High-throughput telemetry. The chain serializes writes; if you
  need 10k entries/sec, batch them into chunks first and chain
  the chunks.

## Files

- `SPEC.md` — entry format, hashing rules, head-hash publication
  protocol.
- `bin/merkle_log.py` — stdlib-only append + verify implementation.
- `bin/verify_log.py` — CLI that verifies a log file and prints
  one summary line.
- `examples/01-append-and-verify/` — clean log, verifier prints
  `ok`.
- `examples/02-tamper-detected/` — same log with one byte changed
  in the middle; verifier reports the exact entry index where the
  chain breaks.

## Head-hash publication

The chain is only as strong as the head hash you compare against.
The pattern:

1. Agent appends entries; periodically (end of mission, end of day)
   reads the current head hash.
2. Agent publishes the head hash to a channel **outside the log
   file itself**: pin in operator chat, append to a separate
   small file under different access controls, sign with a key,
   etc.
3. At verification time, the operator supplies the published
   head hash. Verifier confirms (a) the chain is internally
   consistent and (b) the recomputed head matches the published
   one.

Without step 2, an attacker who controls the log file can simply
recompute the chain after editing — internal consistency means
nothing.

## See also

- `agent-decision-log-format` — what to put in each entry.
- `agent-trace-redaction-rules` — apply *before* hashing, or you
  bake secrets into the hash chain.
- `commit-message-trailer-pattern` — a lightweight cousin: trailer
  pins specific decision-record IDs into git history.
