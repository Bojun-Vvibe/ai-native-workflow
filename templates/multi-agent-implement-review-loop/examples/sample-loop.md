# Sample loop transcript

A representative end-to-end run of one WP through the full
implement → review → re-implement → review → arbiter ladder. Token output is
paraphrased; phase boundaries are real.

**WP**: `WP-add-rate-limit` — add a token-bucket rate limiter to the
`/api/upload` endpoint. Spec says: 10 req/min per IP, 429 on overage,
existing tests must pass, one new test covering the 429 path.

---

## Round 1

### implementer → diff.patch + notes.md

```
diff --git a/src/api/upload.ts b/src/api/upload.ts
+import { RateLimiter } from "../middleware/rate-limit";
+const limiter = new RateLimiter({ perMinute: 10, scope: "ip" });
+
 export async function uploadHandler(req, res) {
+  if (!limiter.allow(req.ip)) return res.status(429).send("rate limited");
   ...
diff --git a/src/middleware/rate-limit.ts b/src/middleware/rate-limit.ts (new file, +52)
diff --git a/test/api/upload.test.ts (+18)
```

notes.md:
> Added a new RateLimiter class in src/middleware/. Wired it into the upload
> handler. Added one test for the 429 path.
> Assumptions: in-memory bucket; survives single-process only. Spec didn't
> mention multi-process so I went with the simpler option.
> Out of scope: the auth middleware is structured similarly and could share
> a base class with rate-limit; not touching.

### reviewer → review.md

```
## Verdict
reject

## Mechanical checks
- tests_added_or_unchanged_count: PASS — one new test, none removed.
- no_files_outside_wp_scope: PASS.
- diff_size_within_cap: PASS.

## Judgment checks
- matches_spec_intent: PASS.
- no_unrequested_refactors: FAIL — new file src/middleware/rate-limit.ts
  introduces a generic RateLimiter abstraction. The spec asks for a
  rate limiter on /api/upload specifically; the generic abstraction
  is unrequested architecture.

## Numbered feedback
1. Inline the token-bucket logic in upload.ts instead of creating a
   reusable middleware. The spec is for one endpoint; YAGNI on the
   abstraction.
2. The 429 response body is "rate limited" but the spec says nothing
   about the body. Match the framework default for consistency with
   other 4xx responses in this codebase (see src/api/auth.ts:33).

## Confidence
medium — item 1 is the load-bearing rejection; item 2 is a nit.
```

---

## Round 2

### implementer → diff.patch + notes.md

```
diff --git a/src/api/upload.ts (+28, -2)
- inlined the token-bucket logic
- removed src/middleware/rate-limit.ts (new file in round 1, now deleted)
- 429 body: framework default
diff --git a/test/api/upload.test.ts (+18)
```

notes.md:
> Inlined per item 1. Used framework default 429 body per item 2.
> Disagreements with reviewer: none.

### reviewer → review.md

```
## Verdict
reject

## Numbered feedback
1. The token-bucket state is now declared at module scope inside
   upload.ts. This is functionally identical to the round-1 version
   from a "bucket lives in memory" perspective, but it conflates the
   handler with the limiter state. Move the bucket state into a
   closure inside uploadHandler instead of module scope.

## Confidence
low — I am no longer sure my round-1 feedback was right; this round's
feedback may be over-rotating in the opposite direction.
```

---

## Round 3

### implementer → diff.patch + notes.md

```
diff --git a/src/api/upload.ts (+30, -28)
- bucket state moved into a closure inside uploadHandler
```

notes.md:
> Closure approach per round 2 feedback. The closure means each request
> creates a new RateLimiter, which defeats the purpose of rate limiting
> across requests. I implemented it anyway because that's what the
> reviewer asked for, but I am flagging this as a likely error.
>
> Disagreements with reviewer: closure scope is wrong here. Rate limiter
> state must outlive a single request. Either the round-1 module-scope
> version or a singleton injected via DI is correct. Closure inside
> the handler is not.

### reviewer → review.md

```
## Verdict
reject

## Numbered feedback
1. The closure-scoped limiter doesn't actually rate-limit. Move it
   back to module scope.

## Confidence
low — I am contradicting my round-2 feedback. The implementer's
disagreement note is correct.
```

---

## Round 3 exhausts max_rounds → arbiter invoked

### arbiter → arbiter.md

```
## Verdict
rule_for_implementer

## Pattern of disagreement
The reviewer flip-flopped on bucket scope between rounds 2 and 3. The
implementer's round-1 diff (module-scope bucket, 52-line dedicated file)
satisfied the spec. The reviewer's round-1 rejection on "unrequested
abstraction" had merit; the implementer's round-2 inline version
addressed it correctly. The reviewer's round-2 feedback (move to
closure) was wrong on the merits.

## Why the rounds did not converge
The reviewer's confidence dropped from "medium" in round 1 to "low" in
rounds 2 and 3, indicating the reviewer recognized in-real-time that
the feedback was getting worse. Without an arbiter mechanism, this
loop would have continued indefinitely, ratcheting the implementer
through bad architectural choices.

## Decision
Accept the round-2 implementer diff (inline token-bucket at module
scope inside upload.ts). Discard the round-3 closure version.
The implementer was right to push back in round 3.

## If propose_synthesis
N/A — clean rule for the implementer.
```

---

## Outcome

- Final accepted artifact: round-2 diff.
- Total cost: 3 implementer turns + 3 reviewer turns + 1 arbiter turn.
- Without the arbiter, the loop would have continued and ended up with
  a non-functional rate limiter merged.
- Lesson: the **implementer's "Disagreements with reviewer" section in
  round 3** was the signal that triggered the arbiter to rule for the
  implementer. Without that section, the arbiter would have had no
  evidence the reviewer was wrong and might have ruled the other way.

This is exactly what the multi-agent loop is for: dissent is preserved,
the arbiter has the full transcript, and a deciding voice exists when
the loop would otherwise spin.
