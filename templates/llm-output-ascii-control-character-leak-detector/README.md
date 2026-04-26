# llm-output-ascii-control-character-leak-detector

Pure-stdlib detector for **ASCII C0 control characters** (U+0000..U+001F)
and **DEL** (U+007F) leaking into LLM output where they should not
appear.

This is the *7-bit* sibling of
[`llm-output-zero-width-character-detector`](../llm-output-zero-width-character-detector/),
which targets multi-byte invisible Unicode (`U+200B`, `U+FEFF`,
`U+202D`, tag characters, etc.). The two problem classes are
orthogonal: a `\x00` from a tokenizer hiccup is a different bug from a
`U+200B` from a copy-pasted training sample, and conflating them in
one report makes triage harder. Run both detectors in CI; union the
findings.

## Why this exists

LLMs occasionally emit C0 / DEL bytes for boring reasons (the
tokenizer has them, a long prompt nudged a sampler into the rare
codepoint range, an upstream pipe converted a delimiter byte) and for
adversarial reasons (a prompt-injection that smuggles in
`\x1b[2J\x1b[H` to clear the reviewer's terminal, a `\x00` planted to
truncate a downstream C-string read, an exfil attempt over a BEL-`\x07`
side channel). The bug class shows up when:

- **A NUL byte (`\x00`) terminates a C-string.** Downstream tooling
  that ultimately calls into a C library (`grep`, `git index`,
  filesystem APIs on some platforms) sees the field truncate at the
  NUL while Python sees the full string. Diff and search drift apart.
- **An ANSI escape (`\x1b[…m`) repaints the reviewer's terminal.**
  Pasting agent output into a terminal-rendering log viewer (`less
  -R`, `tail -f`, GitHub Actions log UI) executes the escape. A
  hostile `\x1b[2J\x1b[H` clears prior context; `\x1b[8m` hides
  payload text from human review.
- **`\x07` (BEL) makes a noise on every render.** Cute prank, real
  side channel for shell automation that watches stderr for bells.
- **`\x08` (BS) corrupts diffs and copy-paste.** Combined with another
  character it visually overstrikes — what the reviewer sees does
  not match what the bytes are.
- **`\x0B` (VT) and `\x0C` (FF) masquerade as line breaks.** Some
  terminals advance lines; some do not. Markdown parsers treat them
  as ordinary characters. Line counts disagree across tools.
- **`\x7F` (DEL) is non-printable and dangerous in regex.** A planted
  DEL inside an identifier defeats `grep` and breaks compilers
  silently.

Permitted by default: `\t` (HT, U+0009), `\n` (LF, U+000A), `\r` (CR,
U+000D). Everything else in C0 + DEL is reported.

## Detected kinds

Each is its own finding kind so the operator decides which classes
are tolerable for their pipeline:

| Kind | Codepoint(s) | Notes |
|---|---|---|
| `nul_byte` | U+0000 | C-string truncation hazard. **High severity.** |
| `bell` | U+0007 | Terminal nuisance, side-channel. |
| `backspace` | U+0008 | Visual overstrike, breaks diffs. |
| `vertical_tab` | U+000B | Line-break masquerade. |
| `form_feed` | U+000C | Line-break masquerade. |
| `escape` | U+001B | ANSI escape lead-in. **High severity.** |
| `del` | U+007F | Non-printable, regex hazard. |
| `other_c0` | other 0x00..0x1F | Catch-all for SOH/STX/ETX/etc. |

## API

```python
from validator import detect_controls, format_report

findings = detect_controls(
    text,
    allowlist=(0x09, 0x0A, 0x0D),     # default — HT, LF, CR
    suppress_in_code=False,           # set True to ignore findings inside fenced / inline code
)
print(format_report(findings))
```

Each `Finding` carries `offset`, `line_no`, `column`, `codepoint`,
`char_name`, `kind`, and `in_code`. Findings are sorted by
`(offset, kind)` so byte-identical re-runs make diff-on-the-output a
valid CI signal.

## Worked example

`example.py` exercises seven cases. Run it directly:

```
python3 example.py
```

Captured output (verbatim):

```
=== case 01 clean prose ===
OK: no ASCII control characters found.

=== case 02 NUL byte inside an identifier ===
FOUND 1 control character(s):
  line 1 col 22 offset 21: U+0000 <control-00> kind=nul_byte

=== case 03 ANSI escape sequence (color code) ===
FOUND 2 control character(s):
  line 1 col 9 offset 8: U+001B <control-1B> kind=escape
  line 1 col 20 offset 19: U+001B <control-1B> kind=escape

=== case 04 BEL + BS combo (terminal-corrupting) ===
FOUND 6 control character(s):
  line 1 col 6 offset 5: U+0007 <control-07> kind=bell
  line 1 col 14 offset 13: U+0008 <control-08> kind=backspace
  line 1 col 15 offset 14: U+0008 <control-08> kind=backspace
  line 1 col 16 offset 15: U+0008 <control-08> kind=backspace
  line 1 col 17 offset 16: U+0008 <control-08> kind=backspace
  line 1 col 18 offset 17: U+0008 <control-08> kind=backspace

=== case 05 form feed and vertical tab masquerading as line breaks ===
FOUND 2 control character(s):
  line 1 col 6 offset 5: U+000C <control-0C> kind=form_feed
  line 1 col 12 offset 11: U+000B <control-0B> kind=vertical_tab

=== case 06 control char inside fenced code block ===
FOUND 1 control character(s):
  line 4 col 9 offset 37: U+0000 <control-00> kind=nul_byte [in_code]
--- with suppress_in_code=True ---
OK: no ASCII control characters found.

=== case 07 DEL byte mid-word ===
FOUND 1 control character(s):
  line 1 col 20 offset 19: U+007F <control-7F> kind=del
```

What the cases prove:

- **01** — clean prose passes silently. No false positives on `\n`
  in normal text (LF is in the default allowlist).
- **02** — a `\x00` planted inside `feature_x` is reported with the
  exact column. A `sed` fix is one keystroke and the report alone is
  enough to author the patch.
- **03** — the two halves of an ANSI color escape (`\x1b[31m` and
  `\x1b[0m`) are flagged independently. Both are `kind=escape`, so a
  CI rule "fail on any `kind=escape`" catches every variant
  (`\x1b[2J`, `\x1b[8m`, OSC 8 hyperlinks, etc.) without an
  ANSI-escape grammar.
- **04** — the BEL prefix and the five-`\x08` overstrike sequence are
  reported per-byte. The reviewer can reconstruct the visual prank
  from the offset list alone (the user sees `ALERT Press OK` after
  rendering; the bytes contain `ALERT\x07 Press \x08\x08\x08\x08\x08OK`).
- **05** — `\x0C` (form feed) and `\x0B` (vertical tab) are flagged
  as distinct kinds. Some pipelines tolerate FF as a page-break;
  per-kind reporting lets the operator allowlist `0x0C` while still
  failing on `0x0B`.
- **06** — the same `\x00` inside a fenced code block is reported by
  default with `[in_code]`, and disappears under
  `suppress_in_code=True`. Docs that legitimately demonstrate
  control bytes (security writeups, this very README's source if it
  contained any) should suppress; production prose should not.
- **07** — `\x7F` (DEL) mid-word is correctly classified as `del`
  rather than `other_c0`. DEL is technically not in the C0 range
  (0x00..0x1F) but is grouped here because it's the same problem
  class — non-printable 7-bit byte that breaks downstream tooling.

## Composition

- **`llm-output-zero-width-character-detector`** — orthogonal
  (multi-byte Unicode invisibles vs single-byte ASCII controls). Same
  `Finding` shape and stable sort, so a single CI step can union both
  reports.
- **`llm-output-trailing-whitespace-and-tab-detector`** — orthogonal
  axis (visible-but-trailing whitespace vs non-printable controls).
  Same fence-awareness convention so column math stays honest across
  the three detectors.
- **`agent-output-validation`** — feed `(kind, offset)` into a repair
  prompt for a one-turn fix
  (`"strip the \x00 at column 22 of line 1"`). Same prompt shape
  works for any kind.
- **`structured-error-taxonomy`** — `kind=escape` and `kind=nul_byte`
  are `do_not_retry / attribution=infrastructure` (likely
  prompt-injection or smuggling; block, do not retry). The other
  kinds are `do_not_retry / attribution=model`.

## Tuning

- For pipelines that legitimately ship form-feed page breaks (some
  PDF-to-text exports), allowlist `0x0C` so they do not flag.
- For docs that demonstrate control bytes in code samples (security
  writeups), pass `suppress_in_code=True`.
- For high-trust internal docs you can fail CI only on the two
  high-severity kinds (`nul_byte`, `escape`) and downgrade the rest
  to warnings.
