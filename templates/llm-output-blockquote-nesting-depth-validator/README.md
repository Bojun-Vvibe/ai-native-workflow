# llm-output-blockquote-nesting-depth-validator

Pure stdlib validator for *blockquote nesting* in LLM-emitted
Markdown. The model is asked to quote a source, then quote a
quote inside that source, and the resulting `>` / `> >` /
`> > >` prefixes drift in ways that look fine to a human reader
but break every downstream Markdown renderer in different ways.

This template treats blockquote structure as the only thing that
matters. It does not parse the quoted content. It walks the
file line by line, tracks the per-line `>` depth, and emits one
finding per anomalous line.

Six finding classes:

- **`depth_jump`** — depth increased by more than 1 between
  adjacent blockquote lines (e.g. `>` immediately followed by
  `> > >`). CommonMark and GFM disagree on how to render this;
  some give you nested quotes, some give you a single quote
  containing literal `>` characters.
- **`mixed_marker_spacing`** — within a run of adjacent same-depth
  blockquote lines, the marker tokens use inconsistent spacing
  (e.g. `>>` next to `> >` next to `>  >`). Same intended depth,
  three different ASTs.
- **`trailing_space_after_gt`** — a line is a bare `>` followed
  by whitespace and nothing else. Several renderers treat this
  as "quote continues" and absorb the next paragraph.
- **`empty_quote_line`** — a line is a bare `>` (or `> >` etc.)
  with no content and no trailing whitespace. Often a
  hallucinated separator the model inserted to make a reply
  "look structured."
- **`unindented_continuation`** — a non-blockquote line directly
  follows a blockquote line of depth >= 2 with no blank line
  between them. CommonMark merges it into the deepest open
  quote; the model almost certainly meant to exit.
- **`max_depth_exceeded`** — depth > 4. Beyond depth 4, every
  major renderer disagrees on rendering. If the model is
  emitting depth 5+, it is almost certainly wrong about what it
  is quoting.

## When to use

- CI assertion on prompt-replay outputs that contain quoted
  source material (RAG answers, "summarize this thread,"
  citation-heavy reports).
- Forensic pass on a single bad answer where the *content* looks
  fine in plaintext but the rendered HTML is mangled.
- Pre-merge gate on a prompt change that adds a "quote the
  source" instruction; rerun the corpus, confirm no new
  `depth_jump` or `max_depth_exceeded` regressions appear.

## When NOT to use

- This is **not** a Markdown linter. It only inspects
  blockquote structure. Use a real linter (e.g. `markdownlint`)
  for the rest.
- Files mixing fenced code blocks with blockquotes may produce
  spurious findings if a `>` literal appears inside a code
  fence — the validator does not parse fences. If you need
  fence-aware behavior, strip fenced regions before piping in.
- The unindented-continuation rule fires on the line that comes
  back to depth 0. If you intentionally use that pattern (as
  some style guides allow), suppress this kind in your CI.

## Worked example

Input fixture `examples/sample.md` is a deliberately broken
quoted-source reply that exercises every finding class.

Run:

```
python3 validator.py examples/sample.md
```

Verbatim stdout:

```
{"detail": "prev_depth=1 depth=3", "kind": "depth_jump", "line": 4}
{"detail": "depth=2 variants=['>>_', '>_>_']", "kind": "mixed_marker_spacing", "line": 9}
{"detail": "depth=1 variants=['>', '>_', '>___']", "kind": "mixed_marker_spacing", "line": 13}
{"detail": "depth=1 trailing_chars=3", "kind": "trailing_space_after_gt", "line": 14}
{"detail": "depth=1", "kind": "empty_quote_line", "line": 15}
{"detail": "prev_depth=1 depth=5", "kind": "depth_jump", "line": 17}
{"detail": "depth=5 max=4", "kind": "max_depth_exceeded", "line": 17}
{"detail": "prev_depth=2", "kind": "unindented_continuation", "line": 19}
```

All six finding classes are exercised. (`depth_jump` fires twice
because the fixture contains two distinct depth jumps.)

## Schema

Each output line is a JSON object with:

- `line` (int, 1-indexed) — line where the issue was detected
- `kind` (str) — one of the six classes above
- `detail` (str) — human-readable details, stable enough to
  diff across runs

## Exit code

Always 0. This is a *reporter*. Wrap in CI like:

```
python3 validator.py answer.md > findings.jsonl
test ! -s findings.jsonl
```

if you want a hard gate.
