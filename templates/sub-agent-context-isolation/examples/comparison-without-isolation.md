# Comparison: same task, no sub-agent isolation

Same parent agent, same mission state, same question — but this
time the parent does the investigation itself instead of dispatching.

## What the parent does (all in its own context)

| turn | tool | tokens added to parent context |
|---|---|---|
| 18 | grep `processInvoice` in src/ | +480 |
| 19 | grep `processInvoice` in test/ | +320 |
| 20 | read src/billing/runner.ts (220 lines) | +2,100 |
| 21 | read src/billing/queue.ts (340 lines) | +3,200 |
| 22 | read src/api/webhook.ts (180 lines) | +1,750 |
| 23 | read src/jobs/retry.ts (95 lines) | +940 |
| 24 | read src/types/billing.ts (140 lines) | +1,360 |
| 25 | read test/billing/runner.test.ts (210 lines) | +2,000 |
| 26 | read test/api/webhook.test.ts (160 lines) | +1,510 |
| 27 | (compose answer) | +280 |

**Total context growth:** +13,940 tokens.

Total tokens billed: ~13,800 (slightly less than the sub-agent
approach because no separate system prompt overhead).

Wall time: ~7.1s (slightly faster — no dispatch round-trip).

## What hurts on the next turn (turn 28)

The parent now needs to plan the rename. Its prompt for turn 28
includes everything from turns 1–27, including all 9 file reads.

- **Cache hit rate on turn 28: 61%** (down from 82% in the
  isolation case). Why: the new file-read content broke the cache
  prefix the parent had been hitting; the cached prefix now ends
  somewhere mid-investigation.
- **Latency on turn 28: 4.8s** (vs 2.9s in the isolation case).
  Mostly cache miss + larger context to process.
- **Distraction risk:** the parent now has 9 full files in its
  recent history. On turn 30 it briefly considers refactoring
  `runner.ts` because it just read it — even though that wasn't
  in the original mission. (This is a real failure mode; sub-agent
  isolation prevents it because the parent never sees the bodies.)

## The compounding effect

For one investigation, the cost difference is small or even
favors the no-isolation path. But the parent has 4 more
investigations to do this mission. Cumulative impact:

| metric | isolation (5 investigations) | no isolation (5 investigations) |
|---|---|---|
| parent context after all 5 | 39,400 tokens | 108,700 tokens |
| avg cache hit rate on next turn | 79% | 48% |
| avg latency per turn (turns 30–50) | 3.1s | 5.6s |
| distractions logged in decision log | 0 | 3 |

This is where isolation pays off. Per-investigation it looks
break-even. Across a long mission it dominates.
