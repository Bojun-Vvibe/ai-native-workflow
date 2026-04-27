# llm-output-markdown-numeric-character-reference-out-of-range-detector

Flags HTML/markdown numeric character references like `&#1234;`
or `&#x1F600;` whose code point is outside the legal Unicode range
or otherwise illegal in HTML.

## What it detects

Three classes of broken numeric character references:

1. **Above the Unicode max** — any code point greater than
   `0x10FFFF`, e.g. `&#x110000;` or `&#1114112;`.
2. **Surrogate halves** — code points in `0xD800..0xDFFF`, which
   are reserved for UTF-16 surrogate pairs and must never appear
   as standalone characters. HTML5 specifies these are parsed as
   U+FFFD.
3. **NULL** — `&#0;` / `&#x0;`, which the HTML5 parser also
   replaces with U+FFFD.

Example bad input from an LLM:

```
The smiley emoji is &#x1F6000;.
```

(The model dropped or added a hex digit; `0x1F6000` exceeds the
Unicode max of `0x10FFFF`.)

The corrected form is:

```
The smiley emoji is &#x1F600;.
```

## Why it matters for LLM-generated markdown

- **Silent character loss**: HTML5 parsers convert these to U+FFFD
  (the replacement character). The page renders a `?` in a box
  instead of the intended glyph; the source still looks plausible.
- **Hex digit drift is common**: LLMs producing emoji or rare
  glyphs frequently miscount hex digits, producing `&#x1F6000;`
  instead of `&#x1F600;`. The 6-digit form `0x1F6000` is exactly
  one too many digits for typical emoji code points.
- **Ambiguous decimal forms**: a leading-zero decimal reference
  like `&#0128512;` may look like a typo but is actually valid;
  this detector deliberately does not flag merely-padded forms.

The detector is **code-fence aware** (skips ``` and ~~~ blocks)
and ignores inline-code spans (text between single backticks on
the same line) so deliberately-illustrative bad references inside
documentation prose are not flagged.

## Usage

```
python3 detect.py path/to/file.md
```

Exit codes:

| code | meaning |
| --- | --- |
| 0 | no findings |
| 1 | findings printed to stdout |
| 2 | usage error |

## Worked example

```
$ python3 detect.py examples/bad.md
examples/bad.md:3:21: numeric reference &#x110000; is above U+10FFFF
examples/bad.md:5:14: numeric reference &#xD800; is a UTF-16 surrogate half
examples/bad.md:7:10: numeric reference &#0; is NULL (parsed as U+FFFD)
examples/bad.md:9:21: numeric reference &#x1F6000; is above U+10FFFF
$ echo $?
1

$ python3 detect.py examples/good.md
$ echo $?
0
```
