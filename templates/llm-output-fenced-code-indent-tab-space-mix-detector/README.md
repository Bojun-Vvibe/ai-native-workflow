# llm-output-fenced-code-indent-tab-space-mix-detector

Pure-stdlib detector for tab-vs-space indent mixing **inside fenced
Markdown code blocks** of LLM-generated text. This is the bug class
where the rendered Markdown looks fine but the code inside, once a user
copy-pastes it, fails to parse — because Python or YAML cannot tolerate
mixed leading whitespace and the model has produced exactly that.

## Why this exists

LLMs frequently emit code blocks where:

- One line is tab-indented and the next is space-indented at the same
  logical depth — Python raises `TabError: inconsistent use of tabs
  and spaces in indentation`, YAML raises a parse error or, worse,
  silently re-nests the document.
- A single line begins with `\t    ` (tab then four spaces). It
  renders to "an indented line" in the Markdown preview, but Python
  treats the tab as 8 columns and the four spaces as four more, so
  the line is at column 12, not column 4 — a real "looks right,
  parses wrong" trap.
- Two adjacent fenced blocks in the same document use different
  regimes (block A is spaces-only, block B is tabs-only). The
  reader copy-pastes both into one file and the second one will not
  run.

This detector is orthogonal to
`llm-output-trailing-whitespace-and-tab-detector` (which looks at
visible-but-trailing whitespace anywhere in the document). This one
**only** scans inside fenced blocks and **only** looks at the leading
indent run.

## Detected kinds

| Kind | Trigger | Why it's bad |
|---|---|---|
| `mixed_in_line` | A single line's indent run contains both `\t` and ` ` | Python `TabError`, YAML mis-nesting; the form most likely to silently break a copy-paste |
| `mixed_in_block` | The same fenced block has at least one tab-indented line and at least one space-indented line | Same parse failure once the snippet is concatenated |
| `inconsistent_in_doc` | Different fenced blocks in the document use different indent regimes | Copy-pasting two snippets into one file produces a `TabError` even if each snippet alone is clean |

## Skipped languages

Blocks whose info string declares `make`, `makefile`, `mk`, `go`, or
`golang` are skipped — leading tabs are required (Make) or strongly
idiomatic (gofmt) and flagging them is noise.

## API

```python
from validator import detect_indent_mix, format_report

findings = detect_indent_mix(text)
print(format_report(findings))
```

Each `Finding` carries `kind`, `block_index`, `block_start_line`,
`line_no`, `detail`, and `info_string`. Findings are sorted by
`(block_start_line, line_no, kind)` so byte-identical re-runs produce
byte-identical reports — diff-on-the-output is a valid CI signal.

## Worked example

`example.py` exercises six cases. Run it directly:

```
python3 example.py
```

Captured output (verbatim):

```
=== case 01 clean spaces-only block ===
OK: no indent-mix findings.

=== case 02 mixed in single line (tab then spaces) ===
FOUND 1 indent-mix finding(s):
  block #0 (opens line 3) line 5 info='python': mixed_in_line -- indent run = TABSPSPSPSP

=== case 03 same block: one line tabs, next line spaces ===
FOUND 1 indent-mix finding(s):
  block #0 at line 1 info='python': mixed_in_block -- block contains both tab-indented and space-indented lines

=== case 04 doc-level inconsistency across two blocks ===
FOUND 1 indent-mix finding(s):
  block #1 (opens line 10) line 10 info='python': inconsistent_in_doc -- this block is tab-indented; earlier block(s) used space

=== case 05 makefile block is skipped (tabs are required) ===
OK: no indent-mix findings.

=== case 06 prose-only document, no code blocks ===
OK: no indent-mix findings.

```

What the cases prove:

- **01** clean spaces-only Python is silent — no false positive on
  the most common LLM output shape.
- **02** the per-line mix `\t    ` is reported with the leading run
  spelled out as `TABSPSPSPSP`, so the operator sees exactly what to
  strip without re-opening the file.
- **03** a block that mixes tab-indented and space-indented lines
  fires `mixed_in_block` once for the block (not once per line),
  pinned to the block's opening fence.
- **04** the doc-level case fires `inconsistent_in_doc` on the
  *second* block, naming the regime of both, so the operator knows
  which block to rewrite to match the other.
- **05** a `make`-tagged block with both tab and space indents stays
  silent — Make requires leading tabs and flagging them would be
  noise.
- **06** a document with no code blocks at all is silent — the
  detector never inspects prose.

## Composition

- **`llm-output-trailing-whitespace-and-tab-detector`** — orthogonal
  axis (trailing whitespace anywhere vs leading whitespace inside
  code). Same `Finding` shape, so a single CI step can union both.
- **`llm-output-code-fence-language-tag-validator`** — runs naturally
  before this one; if the language tag is missing the
  `_TAB_REQUIRED_LANGS` skip cannot fire and an unfair flag may be
  raised.
- **`agent-output-validation`** — feed `(kind, block_start_line)`
  back into a repair prompt: "rewrite the fenced block opening at
  line 10 to use spaces-only indentation."

## Tuning

- If your docs legitimately mix Make and Python in the same file,
  the `inconsistent_in_doc` finding will still fire across the two
  Python blocks, never against the Make block — that is correct.
- If you ship a language not in `_TAB_REQUIRED_LANGS` that
  legitimately uses tabs (some custom DSL), extend the constant
  rather than weakening the detector.
- The default policy is "any finding fails CI." For high-tolerance
  docs you can downgrade `mixed_in_block` and `inconsistent_in_doc`
  to warnings and only fail on `mixed_in_line` — that is the form
  that will definitely break a copy-paste.
