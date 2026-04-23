### Question 1: every loop with a filter — does it return on the first match?

**Applies to:** not applicable to this diff

**Pattern observed:** —

**Bug-shape risk:** n/a

**Counter-question for the author:** —

**Suggested test:** —

---

### Question 2: every "we're done" signal — is there a second signal that could lag?

**Applies to:** `src/runtime/completion.ts:88-105`

**Pattern observed:** Two completion signals are emitted by the
upstream: `server-done` (the upstream says it's finished) and
`final-chunk` (the last chunk of payload arrives). The handler for
`server-done` now calls `this.teardown()` immediately after
emitting `complete`, but `teardown()` calls `removeAllListeners()`
— which means if `final-chunk` arrives _after_ `server-done` (a
common race on a slow client or a buffering proxy), the
`final-chunk` listener is already detached and the chunk is
silently dropped.

The previous implementation called `flushPendingChunks()` before
emitting `complete`, which suggests the original author was aware
of buffered tail chunks. That call was removed in this diff, so
even chunks that already arrived but hadn't been flushed are
lost.

**Bug-shape risk:** high

**Counter-question for the author:** On a slow network where
`final-chunk` arrives 50ms after `server-done`, what does the
caller see — a complete payload or one missing the last chunk?
And what was the reason for removing the `flushPendingChunks()`
call before `emit("complete", ...)`?

**Suggested test:** A two-event fixture where `server-done` is
emitted on the upstream, then 10ms later `final-chunk` is
emitted. Assert that the `complete` event's payload contains the
chunk emitted after `server-done`. The current implementation
will fail this test because the listener is torn down between
the two events.

---

### Question 3: every translator — what does the default branch do?

**Applies to:** not applicable to this diff

**Pattern observed:** —

**Bug-shape risk:** n/a

**Counter-question for the author:** —

**Suggested test:** —

---

### Question 4: every constructor — are there other constructors that share concerns?

**Applies to:** not applicable to this diff

**Pattern observed:** —

**Bug-shape risk:** n/a

**Counter-question for the author:** —

**Suggested test:** —

---

SUMMARY: 1/4 questions fired (high: 1, medium: 0, low: 0)
