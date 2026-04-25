# `prompt-token-budget-trimmer`

Priority-aware prompt assembly under a hard token budget. Given a list
of labeled prompt sections (system, task, retrieved docs, conversation
turns, scratchpad…), produce a final prompt that fits the budget by
**dropping low-priority sections first** and optionally **truncating one
section on the boundary** rather than dropping it whole.

Deterministic, stdlib-only, with a pluggable token counter.

## What it solves

You are about to call a model. You have:

- A 4k or 8k context window (hard cap).
- A growing pile of stuff you'd like in the prompt: system rules,
  current task, retrieved snippets from RAG, recent conversation,
  agent scratchpad.
- A natural priority order on those sections (system > task > diff >
  retrieved docs > scratchpad).

You need a single function that takes the list and the budget and
gives you back a prompt that fits — without silently dropping the
section the model actually needs, and without producing a prompt that
goes over budget by one token because the truncation marker was
counted wrong.

## When to use

- Your prompt has heterogeneous sections with clear priority.
- Budget is hard (rejections from the model, or your own cost cap).
- You want the trim decision to be explainable: which labels stayed,
  which dropped, which got truncated.
- You want it deterministic in tests (no real tokenizer required;
  inject one when you want production accuracy).

## When NOT to use

- All sections are equally important — that's a different problem
  (summarize, don't trim). Pair this with
  `conversation-summarizer-window` for older turns.
- You need streaming output trimming, not assembly trimming — that's
  `streaming-token-rate-limiter`.
- You're trimming a single long doc to a window, not assembling N
  sections — use a sliding-window chunker.

## Anti-patterns this prevents

- **Drop-the-tail truncation**: chopping the final N characters of the
  assembled prompt regardless of which section they belong to —
  routinely eats half the system prompt or the user's actual question.
- **All-or-nothing dropping**: refusing to keep any of a section that
  doesn't fit whole, even when the head of it carries most of the
  signal (a diff, a doc).
- **Marker-not-counted-against-budget**: appending
  `"[truncated]"` after trimming and then going one token over the
  budget you just enforced.
- **Non-deterministic order**: trimming based on `dict` iteration order
  or `set`, producing different prompts on different Python versions
  for the same inputs.

## API surface

`PromptBudgetTrimmer(budget, count=default_count, truncation_marker="[...truncated {n} tokens]")`

| Method | Returns | Notes |
|---|---|---|
| `.trim(sections: List[Section])` | `TrimResult` | Pure function. No I/O. |

`Section(label, text, priority, truncatable=False)`

| Field | Meaning |
|---|---|
| `label` | Stable identifier used in the result (e.g. `"system"`, `"retrieved_doc_3"`). |
| `text` | The actual content. |
| `priority` | Higher = kept first. Ties broken by input order. |
| `truncatable` | If True, this section may be partially kept on the boundary instead of dropped. |

`TrimResult`

| Field | Meaning |
|---|---|
| `sections` | Final ordered sections (re-emitted in input order). |
| `kept_labels` | Labels kept (possibly truncated). |
| `dropped_labels` | Labels dropped entirely. |
| `truncated_label` | Label of the single section that was cut on the boundary, if any. |
| `total_tokens` | Final token count, guaranteed `<= budget`. |
| `budget` | Echoed for downstream logging. |
| `.assemble(joiner="\n\n")` | Joined prompt string. |

## Algorithm in one paragraph

Sort sections by `(priority desc, input_index asc)`. Greedily admit
the highest-priority section while it fits. When the next section
won't fit and is `truncatable`, keep a head-prefix sized exactly to
remaining slack, append a token-counted truncation marker, shave
further if the marker pushed it over. Drop everything below. Re-emit
kept sections in **original input order** so the prompt reads
naturally even though trim decisions were made in priority order.

## Sample output

Running `python3 worked_example.py` against six sections under a
30-token budget:

```
Budget: 30 tokens
Used:   27 tokens
Kept:   ['system', 'task', 'diff']
Dropped:['retrieved_doc_a', 'retrieved_doc_b', 'scratchpad']
Truncated: diff
---- assembled prompt ----
You are a careful code reviewer. Be terse. Cite line numbers.

Review the diff below and flag correctness issues only.

diff: changed retry classifier
[...truncated 30 tokens]
---- end ----
invariants OK
```

Note three things:

1. **27 / 30 tokens used** — under budget, never over. The trimmer
   shaved the diff body further when the truncation marker would have
   pushed the section over the slack.
2. **`diff` was truncated, not dropped** — because it was marked
   `truncatable=True` and the head still carries the salient claim
   ("changed retry classifier"). The `[...truncated 30 tokens]` line
   tells the reader (model) something was elided.
3. **`retrieved_doc_a` and `retrieved_doc_b` dropped whole** — they
   were lower priority than the truncated diff, so they lose. The
   scratchpad (priority 10) was always going to lose first.

## Wiring in a real tokenizer

`default_count` is whitespace-split — fine for tests, wrong for
production. Inject your real one:

```python
from your_tokenizer import count_tokens
trimmer = PromptBudgetTrimmer(budget=4000, count=count_tokens)
```

Token counts then match what the model actually sees.

## Files

- `trimmer.py` — `PromptBudgetTrimmer`, `Section`, `TrimResult`.
- `worked_example.py` — six-section assembly under a 30-token budget.
