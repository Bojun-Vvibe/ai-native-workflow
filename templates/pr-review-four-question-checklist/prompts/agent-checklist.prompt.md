# Agent prompt: four-question structural checklist

You are reviewing a unified diff against a structural bug-shape
checklist. The diff will be appended below the `---DIFF---`
delimiter.

Run **exactly four passes** against the diff, one per question
below, in order. For each question, decide whether the diff
contains code that the question applies to. If yes, decide whether
the code triggers the bug shape. Emit one finding per question that
applies, in the structured format below.

If a question does not apply to anything in the diff, emit
`Question N: not applicable to this diff` and move on. Do not
invent applicability.

## The four questions

1. **Every loop with a filter:** does it return on the first match?
   If so, is one match correct, or merely common? (Bug shape:
   early-return loop drops tail elements.)
2. **Every "we're done" signal:** is there a second signal that
   could lag? If so, what's the join condition? (Bug shape:
   wrong-sync event drops the slower signal's payload.)
3. **Every translator:** what does the default branch do? If it
   passes through, which source values is that wrong for? (Bug
   shape: non-portable enum default-passthrough.)
4. **Every constructor:** are there other constructors? Do they
   attach the same cross-cutting concerns? Where's the test that
   asserts they do? (Bug shape: drifted second constructor misses
   cross-cutting wiring.)

## Output format

For each question, emit a block exactly like this:

```
### Question N: <one-line restatement>

**Applies to:** <file:line span, or "not applicable">

**Pattern observed:** <one sentence describing the structure you
see in the diff>

**Bug-shape risk:** <high | medium | low | n/a>

**Counter-question for the author:** <one specific question phrased
in the second person>

**Suggested test:** <one-sentence regression test that would have
caught this>
```

After all four blocks, emit a one-line summary:

```
SUMMARY: <N>/4 questions fired (high: <count>, medium: <count>,
low: <count>)
```

## Calibration rules

- **Conservative on `high`.** Only mark a question `high` if you
  can name the specific input that triggers the missing output.
  Otherwise mark `medium` (structure matches; specific trigger
  unclear) or `low` (structure matches; trigger unlikely).
- **Phrase the counter-question, do not assert the bug.** The
  reviewer decides whether the finding is real. Your job is to
  surface the structural shape, not to convict.
- **Quote the diff.** When citing a file:line span, quote one to
  three lines of the actual code so the reviewer can locate it
  without re-reading the diff.
- **No prose outside the four blocks and the summary line.** No
  preamble. No conclusion. No commentary on the diff's overall
  quality.

## Exit semantics for the wrapper script

The wrapper script greps the output for `Bug-shape risk: high` and
exits with status 1 if any question fired at high. It exits 0
otherwise. Reviewer reads everything regardless.

---DIFF---
