# llm-output-markdown-nested-fence-same-backtick-count-detector

## Problem

CommonMark fenced code blocks open with three or more backticks (or
tildes) and are closed by the **first** subsequent line whose fence
character and length match-or-exceed the opener. Concretely:

````
```
print("hello")
```
echo $?
```
````

The author meant to nest a fenced example inside a tutorial, but the
inner ` ``` ` actually **closes** the outer block. From line 3 onward
the parser is back in prose mode, then opens a new fence at line 5,
producing scrambled rendering.

## When LLM output triggers it

- The model writes a tutorial about Markdown that quotes a fenced
  example using the same backtick count as the surrounding fence.
- Multi-turn editing replaces a tilde fence (`~~~`) with backticks but
  forgets to bump the outer fence to 4 backticks.
- The model emits a fenced "shell session" containing a fenced
  "expected output" block at the same backtick count.

The correct fix is well-known: when nesting, the outer fence must use
**strictly more** of the same character than the inner. So
`````` ```` `````` (4) wraps an inner ` ``` ` (3), or use mismatched
characters (` ``` ` outer, `~~~` inner).

## Why it matters

- Documentation renders with sections silently bleeding into each other.
- Syntax highlighting flips off mid-block.
- Downstream tooling (RAG chunkers, snippet extractors) splits the
  content at the wrong boundaries.
- The bug is invisible in plaintext review because the prose still
  "looks right" line by line.

## Detection rule

Walk the document with a 1-deep fence state machine:

1. Find a fence opener of length `n` (e.g. ` ``` ` → n=3,
   ` ```` ` → n=4) and remember its character (` ` `` ` `` ` ` or `~`).
2. While inside the fence, every line is scanned for a fence-shaped
   line of the **same character**. If such a line has length **strictly
   less than** the opener `n`, it's an inner-fence shaped line that
   would not close — interesting but legal.
3. If such a line has length **exactly equal to** the opener `n` and
   appears in a position that visually looks like an attempt to nest
   (specifically: at least one prose-or-fence line follows on the same
   block, *and* the file contains another opener of the same length
   later), flag the original opener as "ambiguous nested fence".

The flag fires when the **opener length equals the closer length and
there is a follow-on opener of the same length** — that's the textual
fingerprint of `bad-nested.md` above. Single-block files do not flag.

## False-positive notes

- A file with a single fenced block followed by prose: NOT flagged
  (no follow-on opener of same length).
- A file using ` ```` ` (4) outer and ` ``` ` (3) inner: NOT flagged
  (different lengths).
- A file using ` ``` ` outer and `~~~` inner: NOT flagged (different
  fence characters).
- Files where blocks alternate cleanly with prose between them: NOT
  flagged — the heuristic only fires when opener-closer-opener of the
  same length occurs in such a way that the second opener is at the
  same indentation as the first.

## Usage

```sh
python3 detector.py path/to/file.md [more.md ...]
```

Exit codes: `0` clean, `1` ambiguous nested fence found, `2` usage/IO
error.

## Worked example

`examples/bad/` contains three fixtures, each with a different flavor
of same-count nesting. `examples/good/clean.md` exercises the legal
nesting patterns (4-outer/3-inner, mismatched characters, single
block) and must report 0 findings.
