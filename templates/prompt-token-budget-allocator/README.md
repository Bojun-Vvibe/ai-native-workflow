# prompt-token-budget-allocator

Allocate a finite token budget across N prompt sections by priority and
declared floors, and report exactly which sections were intact / truncated /
dropped — so the orchestrator can log the truncation, not silently ship a
mangled prompt.

## Problem

You are assembling a prompt out of multiple sections — system, instructions,
recent chat, retrieved docs, few-shot examples, scratchpad — and your hard
ceiling is something like:

```
budget = model_context_window - reserved_completion - safety_margin
```

When the sections you want to ship sum to more than `budget`, *something has
to give*. The naive approaches all bite you:

- **Cap-and-truncate-the-last-section** — biases the loss to one section
  regardless of importance.
- **Proportional shrink across all sections** — silently halves your system
  prompt, which usually carries critical instructions.
- **Drop sections without telling anyone** — the model hallucinates because
  it never saw the retrieved doc, and your trace shows a normal-looking
  prompt assembly.
- **Hard fail at the boundary** — rejects requests that could have shipped
  with a slightly truncated docs section.

What you want is a small, deterministic policy: priorities decide who eats
first, declared floors decide who is droppable, and **every truncation /
drop is recorded in a decision log** the orchestrator can attach to the
trace.

## Approach

Two-pass allocator over a list of `Section(name, priority, min_tokens,
ideal_tokens, current_tokens)`:

**Pass 1 — floor pass** (priority asc, then input order):
Try to allocate each section's `min_tokens`. If a section's floor doesn't
fit:
- If `priority == 0` (mandatory), raise `BudgetTooSmall` — the caller's
  budget is structurally wrong, fail loud.
- Otherwise, drop the section (allocated = 0, status = `dropped`,
  reason = `floor_did_not_fit`) and continue.

**Pass 2 — top-up pass** (priority asc, then input order):
For each surviving section, top up toward `min(ideal_tokens, current_tokens)`
using remaining headroom. Once headroom hits 0, stop. **Same-priority
sections do not split fairly** — first one in input order wins. This is
intentional: fair-share allocation is harder to debug than "the order I
declared is the order that wins ties."

Pass 1 commits floors *before* anyone gets top-up. That guarantees a
high-priority section's floor is never starved by a lower-priority
section's ideal.

## When to use

- **Multi-section prompt assembly** where total content can exceed the
  context window (RAG pipelines, chat with long history, agent loops with
  scratchpads).
- **Anywhere you want a reproducible truncation policy** — replay a trace
  and the same `(sections, budget)` produces the same allocation.
- **Trace-driven debugging**: the `decisions` log tells you exactly which
  section ate which slice and which one got dropped at what step.

## When NOT to use

- **Single-section prompts**. Just pre-truncate the section.
- **Settings where dropping a section is unsafe.** If a section is
  load-bearing (e.g. tool schema for a tool the model is being asked to
  call), set `priority=0` so the allocator raises instead of dropping it
  silently.
- **Fair-share is required.** This allocator is priority-then-input-order;
  it is intentionally unfair within a priority. If you need proportional
  splits across same-priority sections, this is the wrong primitive.
- **Token counting is wrong.** `current_tokens` is caller-supplied; if the
  caller passes raw character counts, the allocator will happily make a
  decision based on the wrong number. Pair with a real tokenizer.

## API contract

```python
from allocator import Section, allocate, BudgetTooSmall

result = allocate(
    sections=[
        Section("system",       priority=0, min_tokens=100,  ideal_tokens=100,  current_tokens=100),
        Section("instructions", priority=1, min_tokens=200,  ideal_tokens=400,  current_tokens=400),
        Section("recent_chat",  priority=2, min_tokens=200,  ideal_tokens=600,  current_tokens=600),
        Section("rag_docs",     priority=3, min_tokens=300,  ideal_tokens=1200, current_tokens=1200),
    ],
    budget=1500,
)

result.budget_used      # int  (always == budget - budget_headroom)
result.budget_headroom  # int  (0..budget)
result.allocations      # list[Allocation], in INPUT order
result.decisions        # list[str]  (audit log of every commit / drop)

# Per allocation:
a.section_name
a.allocated   # 0..current_tokens
a.status      # "intact" | "truncated" | "dropped" | "skipped_empty"
a.reason      # human-readable when truncated/dropped/skipped
```

### Validation rules (raise at construction or call)

- `Section.min_tokens > Section.ideal_tokens` → `ValueError`.
- Negative tokens or negative priority → `ValueError`.
- Duplicate `Section.name` in the input list → `ValueError`.
- Negative budget → `ValueError`.
- Priority-0 section whose floor exceeds remaining headroom →
  `BudgetTooSmall`. The caller has a structural bug; do not silently drop
  a mandatory section.

### Status semantics

| status          | meaning                                                              |
|-----------------|----------------------------------------------------------------------|
| `intact`        | `allocated == current_tokens` (and >= min)                            |
| `truncated`     | `min_tokens <= allocated < min(ideal_tokens, current_tokens)`         |
| `dropped`       | `allocated == 0` AND section had `current_tokens > 0`                 |
| `skipped_empty` | `current_tokens == 0` — section had no content to ship                |

The `decisions` log is the *audit trail*: it lists every floor commit, every
drop, and every top-up in the order they happened, with the resulting
headroom after each step.

## Edge cases handled

- **Empty section** (`current_tokens == 0`) — never participates, status =
  `skipped_empty`, separate from `dropped`.
- **`ideal_tokens > current_tokens`** — caller said the section *wants*
  more than it has; we cap at `current_tokens` (you cannot ship bytes you
  don't have).
- **`min_tokens == 0`** — section is fully optional; floor pass skips it,
  top-up gives it whatever's left in priority order.
- **Same priority, multiple sections** — input-order wins ties (in both
  passes). Documented, not a bug.
- **Floors sum exactly to budget** — pass 2 has zero headroom; everyone is
  at floor (or `intact` if their floor == ideal == current).
- **Pathological budget** — priority-0 floor that doesn't fit raises
  `BudgetTooSmall` before any partial allocation is committed.

## Tradeoffs

- **No fair-share within priority.** First section in declaration order
  consumes top-up first. Predictable, but you must order your input list
  the way you want ties broken.
- **No "reserve N tokens for this specific section after pass 2".** If
  you need that, give it `priority=0` and a `min_tokens` equal to the
  reservation.
- **No re-balancing.** Once pass 2 commits a top-up to section X, a later
  same-priority section Y cannot reclaim it.
- **Caller owns the tokenizer.** `current_tokens` is an input. The
  allocator treats it as truth. Garbage in, garbage out.
- **No cross-section knowledge.** A retrieved-docs section that is half-
  truncated may now contain partial citations the model can't reason about.
  That's the caller's problem; pair with a section-internal truncator.

## Composes with

- `prompt-token-budget-trimmer` — token-level trimmer for **inside** a
  single section. This allocator decides *how many tokens* go to "recent
  chat"; the trimmer decides *which messages* survive.
- `agent-cost-budget-envelope` — pre-flight gate on whether the call is
  affordable. This allocator runs **after** that gate to shape the prompt.
- `tool-call-cost-estimator` — estimator's `prompt_tokens` field is the
  sum of `allocated` across this allocator's output.
- `agent-decision-log-format` — `result.decisions` drops directly into the
  step's decision log.

## Example output

Scenario 2 (tight budget, 1500 tokens, 5 sections + 1 empty):

```
budget_used     : 1500
budget_headroom : 0
allocations     :
  system               INTACT     allocated=120
  instructions         INTACT     allocated=400
  recent_chat          TRUNCATED  allocated=280   (allocated 280 of ideal 600)
  retrieved_docs       TRUNCATED  allocated=300   (allocated 300 of ideal 1200)
  few_shot_examples    TRUNCATED  allocated=400   (allocated 400 of ideal 800)
  scratchpad           SKIPPED_EMPTY allocated=0   (section had no content)
decisions       :
  - skip 'scratchpad': empty (current_tokens=0)
  - floor 'system' (priority=0): allocated 120 tokens, headroom now 1380
  - floor 'instructions' (priority=1): allocated 200 tokens, headroom now 1180
  - floor 'recent_chat' (priority=2): allocated 200 tokens, headroom now 980
  - floor 'retrieved_docs' (priority=3): allocated 300 tokens, headroom now 680
  - floor 'few_shot_examples' (priority=4): allocated 400 tokens, headroom now 280
  - topup 'instructions' (priority=1): +200 tokens (now 400/400), headroom now 80
  - topup 'recent_chat' (priority=2): +80 tokens (now 280/600), headroom now 0
```

`recent_chat` got the 80 tokens of remaining top-up because it sits at
priority 2 and `instructions` (priority 1) had already been topped up to
its ideal. `retrieved_docs` and `few_shot_examples` are stuck at floor
because the budget ran dry — and the decision log shows that explicitly.

Scenario 4 (small budget, drops a bulky optional, keeps a small low-priority
hint):

```
budget_used     : 340
budget_headroom : 60
allocations     :
  system               INTACT     allocated=100
  user_query           INTACT     allocated=200
  rag_docs             DROPPED    allocated=0   (floor_did_not_fit (need 500, headroom 100))
  style_hint           INTACT     allocated=40
```

Note: `rag_docs` (priority 3, floor 500) is dropped *before* `style_hint`
(priority 4, floor 40) is even visited. `style_hint` then fits cleanly
because the floor pass continues past the dropped section.

Scenario 3 (priority-0 floor cannot fit) raises:

```
BudgetTooSmall: section 'system' is priority=0 (mandatory) but its
min_tokens=2000 does not fit remaining headroom=1000
```

Run it:

```bash
python3 templates/prompt-token-budget-allocator/worked_example.py
```

Stdlib-only. No third-party deps.
