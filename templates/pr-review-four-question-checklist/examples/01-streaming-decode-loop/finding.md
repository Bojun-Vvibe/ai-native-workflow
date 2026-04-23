### Question 1: every loop with a filter — does it return on the first match?

**Applies to:** `src/decode/stream.ts:42-56`

**Pattern observed:** The `for ... of chunks` loop filters out
`synthetic` chunks with `continue`, then decodes the first
non-synthetic chunk and immediately `return blocks` — exiting the
loop after exactly one decoded block. The TODO comment confirms
the author knows this doesn't handle multiple blocks per stream;
the comment also confirms the author is assuming "today the
upstream emits one block" without a regression test pinning that
assumption.

**Bug-shape risk:** high

**Counter-question for the author:** When the upstream model
starts emitting two content blocks per stream (which the SDK
release notes already say it will in the next minor), what does
this function return — both blocks, or just the first? Is there a
caller that relies on the all-blocks behavior such that returning
only the first would silently truncate the model's output?

**Suggested test:** A two-element fixture: a stream containing
exactly two non-synthetic chunks (with one synthetic chunk
sandwiched between them, to also exercise the filter). Assert that
`extractContentBlocks(...)` returns an array of length 2, in
chunk-order. The current implementation will fail this test by
returning length 1.

---

### Question 2: every "we're done" signal — is there a second signal that could lag?

**Applies to:** not applicable to this diff

**Pattern observed:** —

**Bug-shape risk:** n/a

**Counter-question for the author:** —

**Suggested test:** —

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
