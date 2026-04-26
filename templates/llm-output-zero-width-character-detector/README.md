# llm-output-zero-width-character-detector

Pure-stdlib detector for invisible Unicode characters in LLM-generated
text — the bug class where the output **renders identically** to clean
prose but the byte stream contains zero-width spaces, byte-order
marks, soft hyphens, or bidi-control codepoints that silently corrupt
downstream processing.

## Why this exists

LLMs occasionally emit invisible codepoints because their tokenizers
treat them as ordinary tokens, because the training corpus has them
(scraped HTML, copy-pasted from rich-text editors, exported from
PDFs), or — most dangerously — because a prompt-injection / smuggling
attempt has fed them in. The bug is invisible at preview time but
surfaces when:

- **Source code is copy-pasted from the rendered output.** A
  `U+200B` in the middle of an identifier breaks the compiler with
  errors like "undefined name `feature_x`" while the `grep` for
  `feature_x` returns zero hits.
- **Search / RAG retrieval misses literal-string matches.** The
  embedder splits on the invisible and the chunk's surface form no
  longer contains the user's query.
- **Diff tools show identical-looking lines that are not byte-equal.**
  The reviewer sees a clean diff and approves; the file is in fact
  changed.
- **Bidi-control runs reorder code visually.** The Trojan-Source
  attack class — `U+202D…U+2069` flips an `if`-branch's display
  order without changing the bytes the compiler sees.
- **Tag characters (`U+E0000…U+E007F`) carry hidden text.** The
  ASCII-Smuggler steganography channel encodes arbitrary instructions
  inside what looks like a single emoji or a blank span.

## Detected kinds

Each is its own finding kind so the operator can decide which classes
are tolerable for their pipeline:

| Kind | Codepoints | Notes |
|---|---|---|
| `zero_width_space` | U+200B | The classic. |
| `zero_width_non_joiner` | U+200C | Used legitimately in some scripts; flag and let the operator allowlist. |
| `zero_width_joiner` | U+200D | Used in emoji ZWJ sequences. Allowlist if you ship emoji content. |
| `word_joiner` | U+2060 | Older name BOM-equivalent at non-start positions. |
| `bom_or_zwnbsp` | U+FEFF | Byte order mark. Legitimate at file start, suspicious mid-file. |
| `soft_hyphen` | U+00AD | Renders only at line breaks; corrupts grep / search. |
| `bidi_control` | U+202A…U+202E, U+2066…U+2069 | The Trojan-Source class. **High severity.** |
| `invisible_separator` | U+2063 | Math operator; almost never in prose. |
| `invisible_times` | U+2062 | Math operator; almost never in prose. |
| `function_application` | U+2061 | Math operator; almost never in prose. |
| `mongolian_vowel_separator` | U+180E | Deprecated. |
| `hangul_filler` | U+115F, U+1160, U+3164, U+FFA0 | Spoofing channel. |
| `tag_character` | U+E0000…U+E007F | ASCII Smuggler steganography channel. **High severity.** |

## API

```python
from validator import detect_invisibles, format_report

findings = detect_invisibles(
    text,
    allowlist=(0x200D,),       # tolerate ZWJ in emoji sequences
    suppress_in_code=False,     # set True to ignore findings inside fenced / inline code
)
print(format_report(findings))
```

Each `Finding` carries `offset`, `line_no`, `column`, `codepoint`,
`char_name`, `kind`, and `in_code`. Findings are sorted by
`(offset, kind)` so byte-identical re-runs make
diff-on-the-output a valid CI signal.

## Worked example

`example.py` exercises seven cases. Run it directly:

```
python3 example.py
```

Captured output (verbatim):

```
=== case 01 clean ===
OK: no invisible characters found.

=== case 02 zero_width_space inside an identifier ===
FOUND 1 invisible character(s):
  line 1 col 14 offset 13: U+200B ZERO WIDTH SPACE kind=zero_width_space

=== case 03 BOM at start of file plus trailing soft-hyphen ===
FOUND 2 invisible character(s):
  line 1 col 1 offset 0: U+FEFF ZERO WIDTH NO-BREAK SPACE kind=bom_or_zwnbsp
  line 3 col 9 offset 23: U+00AD SOFT HYPHEN kind=soft_hyphen

=== case 04 trojan-source bidi run mid-sentence ===
FOUND 2 invisible character(s):
  line 1 col 23 offset 22: U+202D LEFT-TO-RIGHT OVERRIDE kind=bidi_control
  line 1 col 34 offset 33: U+2069 POP DIRECTIONAL ISOLATE kind=bidi_control

=== case 05 multiple kinds in one line ===
FOUND 4 invisible character(s):
  line 1 col 4 offset 3: U+200D ZERO WIDTH JOINER kind=zero_width_joiner
  line 1 col 8 offset 7: U+200C ZERO WIDTH NON-JOINER kind=zero_width_non_joiner
  line 1 col 12 offset 11: U+2060 WORD JOINER kind=word_joiner
  line 1 col 16 offset 15: U+2062 INVISIBLE TIMES kind=invisible_times

=== case 06 invisible inside a fenced code block ===
FOUND 1 invisible character(s):
  line 4 col 6 offset 37: U+200B ZERO WIDTH SPACE kind=zero_width_space [in_code]
--- with suppress_in_code=True ---
OK: no invisible characters found.

=== case 07 tag-character (ASCII smuggler channel) ===
FOUND 1 invisible character(s):
  line 1 col 30 offset 29: U+E0061 TAG LATIN SMALL LETTER A kind=tag_character
```

What the cases prove:

- **01** clean ASCII passes silently — no false positives on normal
  prose.
- **02** a `U+200B` planted inside `feature_x` is reported with the
  exact column so a `sed` fix is one keystroke.
- **03** a BOM at file start AND a soft hyphen mid-word fire as two
  distinct finding kinds — the operator can decide which to fail CI
  on; a stand-alone leading BOM may be tolerable while a
  mid-document soft hyphen almost never is.
- **04** the Trojan-Source pattern (LRO…PDI) is correctly flagged on
  both the opening and closing controls, so the report alone is
  enough for an incident reviewer to reconstruct the bidi run.
- **05** four different kinds on one line are each listed separately
  and sorted by offset — the report shape stays diffable even with a
  worst-case dense input.
- **06** the same `U+200B` inside a fenced code block is reported by
  default with `[in_code]`, and disappears under
  `suppress_in_code=True`. The operator picks the policy: docs that
  legitimately demonstrate invisibles should suppress; production
  prose pipelines should not.
- **07** the `U+E0061` ("TAG LATIN SMALL LETTER A") — the
  ASCII-Smuggler payload character — is correctly flagged as
  `tag_character`. A real exploit chain encodes a full instruction
  string in this range; even one such character in untrusted output
  is a security signal.

## Composition

- **`llm-output-trailing-whitespace-and-tab-detector`** — orthogonal
  invisible-byte hygiene axis (visible-but-trailing whitespace vs
  truly-invisible codepoints). Same `Finding` shape and stable sort,
  so a single CI step can union both reports.
- **`llm-output-emphasis-marker-consistency-validator`** and the rest
  of the Markdown-hygiene family — same fence-awareness convention,
  so running this gate before them keeps their column math honest.
- **`agent-output-validation`** — feed `(kind, offset)` into the
  repair prompt for a one-turn fix
  (`"strip the U+200B at column 14 of line 3"`).
- **`structured-error-taxonomy`** — `bidi_control` and
  `tag_character` are
  `do_not_retry / attribution=infrastructure` (Trojan-Source /
  ASCII-Smuggler classes; the model is being fed or asked to produce
  hostile bytes and the right action is to block, not retry). The
  other kinds are `do_not_retry / attribution=model`.

## Tuning

- For pipelines that ship emoji content, allowlist `0x200D` (ZWJ) so
  legitimate emoji sequences (`👨‍👩‍👧`) do not flag.
- For docs that demonstrate invisible characters in code samples
  (security writeups, this README), pass `suppress_in_code=True`.
- For high-trust internal docs you can weaken the failure threshold
  and only fail CI on the two high-severity kinds (`bidi_control`,
  `tag_character`); leave the others as warnings.
