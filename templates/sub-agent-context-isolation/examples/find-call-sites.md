# Worked example: find call sites of `processInvoice()`

A parent agent is in turn 18 of a refactor mission. It needs to
know every call site of `processInvoice()` before it can plan
the rename. The parent's context is already 38k tokens (mission
spec, plan, decisions log, recent edits). It dispatches a
sub-agent.

## What the parent sends to the sub-agent

(System prompt = `prompts/sub-agent-system-prompt.md`. User
message below.)

```
ROLE
You are a single-turn investigator. ...

TASK
List every call site of processInvoice() in this repo.

SCOPE
- Allowed paths: src/, test/
- Forbidden paths: node_modules/, dist/, .next/
- Max files to read: 30
- Max tool calls: 25
- Time budget: 60s

EVIDENCE RULES
- Only cite things you actually read in this session.
- Use file:line references.
- Do not include matches inside comments or strings.

OUTPUT SCHEMA
{
  "answer": [
    { "path": "src/foo.ts:42", "context": "1-line surrounding code" }
  ],
  "confidence": "high" | "medium" | "low",
  "assumptions": [string],
  "evidence": [ { "path": "src/foo.ts:42", "why": "string" } ],
  "not_found": [string]
}

DO NOT RETURN
- Narrative reasoning
- Markdown headers or fences
- Paths you did not actually open
```

## What the sub-agent does internally (parent never sees this)

| turn | tool | summary |
|---|---|---|
| 1 | grep `processInvoice` in src/ | 7 hits across 5 files |
| 2 | grep `processInvoice` in test/ | 4 hits across 2 files |
| 3 | read src/billing/runner.ts | 1 real call site, 1 import |
| 4 | read src/billing/queue.ts | 2 real call sites |
| 5 | read src/api/webhook.ts | 1 real call site |
| 6 | read src/jobs/retry.ts | 1 real call site |
| 7 | read src/types/billing.ts | match was a type alias, skip |
| 8 | read test/billing/runner.test.ts | 2 call sites |
| 9 | read test/api/webhook.test.ts | 1 call site, 1 in a comment (skip) |
| 10 | (compose answer) | |

Tokens consumed inside sub-agent: ~14,200 (input + output, summed
across 10 turns). Wall time: ~9 seconds.

## What the sub-agent returns to the parent

```json
{
  "answer": [
    { "path": "src/billing/runner.ts:88",   "context": "await processInvoice(inv, ctx);" },
    { "path": "src/billing/queue.ts:142",   "context": "return processInvoice(item);" },
    { "path": "src/billing/queue.ts:201",   "context": "results.push(await processInvoice(i));" },
    { "path": "src/api/webhook.ts:67",      "context": "void processInvoice(payload.invoice);" },
    { "path": "src/jobs/retry.ts:34",       "context": "await processInvoice(failed);" },
    { "path": "test/billing/runner.test.ts:23", "context": "expect(await processInvoice(fx)).toEqual(...)" },
    { "path": "test/billing/runner.test.ts:81", "context": "await processInvoice(fxRetry);" },
    { "path": "test/api/webhook.test.ts:55", "context": "await processInvoice(stub);" }
  ],
  "confidence": "high",
  "assumptions": [
    "Comments and string literals containing 'processInvoice' were excluded.",
    "Type-only references (interface members named processInvoice) were excluded."
  ],
  "evidence": [
    { "path": "src/billing/runner.ts:88",  "why": "direct call" },
    { "path": "src/billing/queue.ts:142",  "why": "direct call" },
    { "path": "src/billing/queue.ts:201",  "why": "direct call in loop" },
    { "path": "src/api/webhook.ts:67",     "why": "direct call (fire-and-forget)" },
    { "path": "src/jobs/retry.ts:34",      "why": "direct call inside retry handler" },
    { "path": "test/billing/runner.test.ts:23", "why": "test invocation" },
    { "path": "test/billing/runner.test.ts:81", "why": "test invocation" },
    { "path": "test/api/webhook.test.ts:55", "why": "test invocation" }
  ],
  "not_found": []
}
```

## What enters the parent context

Just the JSON above — about **280 tokens**. The 14,200 tokens of
intermediate file reads, greps, and reasoning never enter the
parent's window.

## Parent's next turn

The parent now has a clean, verifiable list. Its next turn:

> "OK, 8 call sites in 5 source files + 2 test files. Plan: rename
> in source first (3 files), run typecheck, then update tests.
> Dispatching the rename WP."

Cache hit rate on this next turn: **82%** (the long-lived mission
prefix is still warm). Compare to `comparison-without-isolation.md`
where the parent did the investigation itself and the cache hit rate
on the equivalent turn dropped to 61%.
