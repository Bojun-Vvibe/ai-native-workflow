# llm-output-list-count-mismatch-detector

Pure-stdlib post-output gate that flags when an LLM's enumerated-list reply does not match the count the prompt asked for. Catches under-delivery, over-delivery, mid-stream truncation (model hit `max_tokens` mid-bullet), promise-without-delivery (model wrote prose instead of a list), and ordinal gaps (`1. … 2. … 4. …`).

## The bug class this catches

The prompt says **"give me 5 reasons"**. The model returns:

- `under` — 3 bullets. The model ran out of useful things to say but didn't admit it. Most common in production.
- `over` — 7 bullets. The model padded with restatements. Caller's downstream code probably hardcodes "take the first 5" and silently drops two.
- `truncated_tail` — 5 bullets, but the last one ends mid-clause: `… lets clients hint and`. Hit `max_tokens` mid-stream. The schema validator says "yep, 5 bullets". The user reads garbage.
- `no_list_promised_was_made` — 0 bullets, free-form prose. Most caller code doesn't even check; it just regexes for bullets and returns `[]`.
- `ordinal_gap` — 4 bullets but the ordinals are `1, 2, 4, 5`. The model deleted the "real" item 3 and renumbered the rest, or it hallucinated a continuation of an outline it doesn't actually have.

A JSON-schema validator catches none of these. A length check catches `under` and `over` but misses `truncated_tail` (right count, wrong bytes) and the "promise vs no-list" case (no list at all to validate against).

## What it does

`detect(prompt, output) → ListCountReport(promised, delivered, findings, verdict)`. Pure function, two strings in, one report out. No I/O, no clocks. Findings are sorted alphabetically for cron-friendly diffing.

### Promise extraction

Regex over the prompt for digit-or-spelled-number (1–20) followed by one of: `reasons, items, bullets, points, steps, examples, ways, tips, things, options, ideas, advantages, disadvantages, benefits, drawbacks, failure modes, modes, causes, approaches, techniques, patterns, practices, rules, principles, strategies, methods` (with optional plural `s`). Anchored on word boundaries so `"in 25 minutes"` does NOT match `25 ...`. Returns the *first* match — operators reading findings need predictability, not cleverness.

### Bullet extraction

Recognized shapes: `1. foo`, `1) foo`, `- foo`, `* foo`, `• foo`. Markers must be followed by exactly one space. Up to three leading spaces of indent allowed (matches realistic markdown).

### Truncation heuristic (two-arm signal)

A trailing bullet is `truncated_tail` when it lacks terminal punctuation **and** at least one of:

1. **Lexical signal** — last token is a stop-word (`and, or, the, a, an, to, of, with, in, for, …`) or ends in a comma. No model writes a complete bullet ending in `"and"`; the only generator of that pattern is `max_tokens` cutting mid-clause.
2. **Geometric signal** — bullet length < 60% of the median peer length. The model started a bullet and ran out of budget before saying anything substantive.

Either arm is enough; both must pass the punctuation+last-position prefilter. This combination keeps false positives low (lots of bullets are short by design; lots of bullets end without punctuation by style) while still catching `case 4` in the worked example, where length-only would miss it (`44/72 = 0.61 > 0.6`).

### Closed verdict enum

`clean`, `under`, `over`, `truncated_tail`, `no_list_promised_was_made`, `no_promise`, `ordinal_gap`. When multiple apply, the *most actionable* wins: `truncated_tail` beats `under` (because raising `max_tokens` fixes both, but `under` would mislead the operator into re-prompting).

## Design choices worth defending

- **`no_promise` is its own verdict, not `clean`.** A pure-prose answer to a pure-prose question shouldn't get rubber-stamped as if it had been counted. Distinguishing the two lets the operator filter their dashboard meaningfully.
- **First-promise wins.** Prompts often say "give me at least 5, up to 10". We honor the floor (5) — a 6-bullet response is `over` only if the floor was 5, never if the floor was 10. Operators tune this by writing prompts with a single count.
- **Mixed-marker lists are fine.** A list of `1. … 2. … - …` counts as 3 bullets. Ordinal-gap detection only inspects the *numeric subsequence*, so the unordered bullet doesn't break the check.
- **Stdlib-only.** `re` and `dataclasses`. No NLTK, no model call to "judge" the list. The cost of running this on every output must round to zero; that's the only way it gets adopted.

## Usage

```python
from detector import detect

prompt = "Give me 5 reasons to switch to a write-ahead log."
output = "..."  # the model's reply
report = detect(prompt, output)
if report.verdict != "clean":
    # route to repair loop, raise alert, log finding, etc.
    print(report.verdict, report.findings)
```

## Worked example

`example.py` runs 7 prompt/output pairs designed to hit each verdict exactly once (plus one no-promise control). Run it:

```
$ python3 example.py
```

Verbatim output:

```
--- case 1 ---
prompt: Give me 5 reasons to switch to a write-ahead log.
promised=5  delivered=5  verdict=clean

--- case 2 ---
prompt: List five ways to reduce embedding cost.
promised=5  delivered=3  verdict=under
  finding: under_delivery: promised 5, delivered 3

--- case 3 ---
prompt: Name three failure modes of retry-with-backoff.
promised=3  delivered=5  verdict=over
  finding: over_delivery: promised 3, delivered 5

--- case 4 ---
prompt: Give me 5 reasons HTTP/2 helps long-tail latency.
promised=5  delivered=5  verdict=truncated_tail
  finding: truncated_tail: last bullet at line 5 ends without terminal punctuation and is markedly shorter than peers

--- case 5 ---
prompt: List 4 advantages of column-oriented storage.
promised=4  delivered=0  verdict=no_list_promised_was_made
  finding: no_list: prompt promised 4 items but output has zero bullets

--- case 6 ---
prompt: Explain what a circuit breaker is.
promised=None  delivered=2  verdict=no_promise

--- case 7 ---
prompt: Give me 4 steps to onboard a new agent profile.
promised=4  delivered=4  verdict=ordinal_gap
  finding: ordinal_gap: ordinal jumped from 2 to 4 at line 3

# All runtime invariants pass.
```

Note case 4: the right *count* (5/5) but the trailing bullet `"Request prioritization lets clients hint and"` triggers the lexical arm of the truncation heuristic. A length-only check would miss it (44 chars vs median 62 → ratio 0.71, above the 0.6 geometric floor). The combined two-arm signal catches it; that's the design payoff.

## Composes with

- **`llm-output-numeric-hallucination-detector`** — sibling content gate. This one validates list shape; that one validates number grounding. Run both at every output boundary.
- **`structured-output-repair-loop`** — `under` / `truncated_tail` / `ordinal_gap` are exactly the trigger conditions to re-prompt with the explicit complaint: *"you delivered 3 but I asked for 5; here are the 3 you wrote — give me 2 more, do not repeat these"*.
- **`model-output-truncation-detector`** — that template detects truncation at the byte/JSON-shape level (unclosed brace, mid-string cut). This one detects truncation at the *list semantics* level (right count, wrong tail). They catch disjoint failures and should both run.
- **`agent-output-validation`** — schema first (does it parse?), list-count second (does the prose honor the prompt contract?), numeric grounding third.
- **`agent-decision-log-format`** — one log line per finding, sharing the request id; the verdict slots cleanly into the structured `outcome` field.
