# llm-output-bom-byte-detector

Pure-stdlib detector for **byte-order-mark (BOM)** sequences embedded in
LLM-generated output, operating on the **raw byte stream** (`bytes`)
rather than decoded `str`.

## Why this exists

A BOM at the start of a UTF-8 stream is permitted by the Unicode
standard but breaks an enormous amount of real tooling:

- **Shell scripts** whose `#!` is no longer the first byte — the kernel
  reads `\xef\xbb\xbf#!/bin/sh` and refuses to exec.
- **JSON parsers** that error on a leading `U+FEFF` ("Unexpected token
  at position 0").
- **Diff tools** that report a one-byte change on otherwise-identical
  files; the reviewer can't see what changed.
- **Web servers** that serve the BOM through to the page and produce a
  stray glyph at the top of the rendered HTML, or break
  `Content-Length`-sensitive intermediaries.
- **SQL / CSV importers** that take the BOM as the first character of
  the first column name (`\ufefffirst_col` ≠ `first_col`).

A BOM **mid-stream** is almost always a concatenation accident — two
files were glued together and each kept its own BOM. That case is far
more dangerous than a leading BOM and the detector classifies it
separately.

## Why operate on bytes, not str

By the time the LLM output has been decoded to `str` the BOM is already
a `U+FEFF` codepoint and indistinguishable from a deliberate
zero-width-no-break-space. Detecting it at the *codepoint* level is
the job of `llm-output-zero-width-character-detector` (which fires on
the same `U+FEFF` after decoding). The byte-level view is the one that
catches the actual file-format bug — the LLM literally emitted bytes
the loader would have to swallow before decoding.

## Detected encodings

Each is its own finding kind so the operator can decide which classes
are tolerable:

| Kind | Signature (hex) | Notes |
|---|---|---|
| `utf8` | `EF BB BF` | The classic. Tolerable for some prose pipelines, fatal for shell / JSON / SQL. |
| `utf16_le` | `FF FE` | Windows defaults; almost certainly wrong in LLM output. |
| `utf16_be` | `FE FF` | Java / network-order legacy. |
| `utf32_le` | `FF FE 00 00` | Checked **before** UTF-16-LE — same prefix. |
| `utf32_be` | `00 00 FE FF` | Rare but real. |
| `utf7` | `2B 2F 76 38/39/2B/2F` | Four variants in the spec. |
| `utf1` | `F7 64 4C` | ISO-10646 historical. |
| `utf_ebcdic` | `DD 73 66 73` | Mainframe export. |
| `scsu` | `0E FE FF` | Standard Compression Scheme for Unicode. |
| `bocu1` | `FB EE 28` | Binary-Ordered Compression for Unicode. |
| `gb18030` | `84 31 95 33` | Mandatory CN encoding; real in mixed-locale tooling. |

The match table is ordered longest-signature-first within each family
so UTF-32-LE (`FF FE 00 00`) is matched before UTF-16-LE (`FF FE`).
A naive shortest-first scan would mis-classify every UTF-32-LE stream
as UTF-16-LE plus two stray null bytes — the worked example proves the
correct ordering with case 05.

## Severity

| Severity | When | Default policy |
|---|---|---|
| `leading` | offset 0 | Block only when `fail_on_leading=True` (shell / JSON / SQL pipelines). Tolerable for prose. |
| `mid_stream` | anywhere else | **Always** blocks. A BOM at offset > 0 is a concatenation bug. |

## API

```python
from detector import detect_boms, format_report, has_blocking_bom

findings = detect_boms(data)              # data: bytes
print(format_report(findings))
if has_blocking_bom(findings, fail_on_leading=True):
    sys.exit(1)
```

Each `Finding` carries `offset`, `kind`, `severity`, `bytes_hex`.
Findings are sorted by `(offset, kind)` so byte-identical re-runs make
diff-on-the-output a valid CI signal.

`detect_boms` raises `TypeError` if passed a `str` — decode-stage
detection is explicitly out of scope (use the zero-width-character
detector). This is by design: a `str` input would silently work for
UTF-8 BOMs (because `U+FEFF` looks like `\xef\xbb\xbf` semantically)
but silently fail for every other encoding's BOM, since those byte
sequences don't survive UTF-8 decoding round-trip.

## Worked example

`example.py` exercises seven cases. Run it directly:

```
python3 example.py
```

Captured output (verbatim):

```
=== 01 clean ascii ===
OK: no BOM bytes found.
blocking(fail_on_leading=False): False

=== 02 leading utf-8 bom only ===
FOUND 1 BOM occurrence(s):
  offset 0: utf8 severity=leading bytes=[ef bb bf]
blocking(fail_on_leading=True): True

=== 03 leading utf-16-le bom ===
FOUND 1 BOM occurrence(s):
  offset 0: utf16_le severity=leading bytes=[ff fe]
blocking(fail_on_leading=False): False

=== 04 mid-stream utf-8 bom (concat accident) ===
FOUND 1 BOM occurrence(s):
  offset 9: utf8 severity=mid_stream bytes=[ef bb bf]
blocking(fail_on_leading=False): True

=== 05 leading utf-32-le bom (utf-16-le prefix trap) ===
FOUND 1 BOM occurrence(s):
  offset 0: utf32_le severity=leading bytes=[ff fe 00 00]
blocking(fail_on_leading=False): False

=== 06 utf-16-le leading + utf-8 mid-stream ===
FOUND 2 BOM occurrence(s):
  offset 0: utf16_le severity=leading bytes=[ff fe]
  offset 8: utf8 severity=mid_stream bytes=[ef bb bf]
blocking(fail_on_leading=False): True

=== 07 gb18030 leading bom ===
FOUND 1 BOM occurrence(s):
  offset 0: gb18030 severity=leading bytes=[84 31 95 33]
blocking(fail_on_leading=False): False

```

What the cases prove:

- **01** clean ASCII passes silently — no false positives on normal
  prose.
- **02** a leading UTF-8 BOM in front of a JSON document is reported
  with `severity=leading` and only blocks when the operator has opted
  in via `fail_on_leading=True`. A JSON pipeline would; a Markdown
  pipeline probably wouldn't.
- **03** a leading UTF-16-LE BOM is reported as exactly that — the
  detector does not silently treat it as UTF-8 garbage.
- **04** a UTF-8 BOM at offset 9 (the boundary between two concatenated
  files) is reported as `severity=mid_stream` and blocks **regardless**
  of `fail_on_leading`. Mid-stream BOMs are never tolerable.
- **05** the prefix-trap case: UTF-32-LE's BOM (`FF FE 00 00`) starts
  with UTF-16-LE's BOM (`FF FE`). The detector matches UTF-32-LE first
  so the reviewer sees the correct encoding name. A naive shorter-first
  scan would have reported `utf16_le` plus two stray nulls — wrong, and
  much harder to diagnose.
- **06** two BOMs in one stream: leading UTF-16-LE plus mid-stream
  UTF-8. Both are listed, sorted by offset; the run blocks because of
  the mid-stream finding even though the leading one is policy-allowed.
- **07** GB18030 is checked too — relevant when LLM output is fed
  through a CN-locale toolchain.

## Composition

- **`llm-output-zero-width-character-detector`** — the codepoint-level
  sibling. Run *both*: this one catches the byte-level concatenation /
  encoding bug, that one catches the
  decoded-`U+FEFF`-as-zero-width-no-break-space bug. Same `Finding`
  dataclass shape and stable sort, so a single CI step can union the
  two reports.
- **`llm-output-mixed-line-ending-detector`** — orthogonal byte-level
  hygiene axis (CRLF vs LF) that pairs naturally with BOM detection
  before any text-mode processing.
- **`structured-error-taxonomy`** — `mid_stream` BOM findings should
  classify as `do_not_retry / attribution=tool` (the upstream
  concatenated two streams; retrying produces the same bytes).
  `leading` findings under `fail_on_leading=True` are
  `do_not_retry / attribution=model` (the model emitted the BOM; a
  one-shot repair prompt fixes it).
- **`agent-output-validation`** — feed `(kind, offset)` into a repair
  prompt: `"strip the 3 BOM bytes at offset 9 of the output"` is a
  one-turn fix.

## Tuning

- For **prose** pipelines (Markdown docs, chat replies), leave
  `fail_on_leading=False`. A single leading BOM is annoying but
  rendering tooling handles it.
- For **shell / JSON / SQL / CSV** pipelines, set
  `fail_on_leading=True`. A leading BOM in any of these formats is a
  real bug.
- The detector never auto-strips. Stripping is a write operation; the
  catalog convention is detect-first, repair-explicitly.
