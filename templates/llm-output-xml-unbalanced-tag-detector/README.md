# llm-output-xml-unbalanced-tag-detector

Pure-stdlib, code-fence-aware detector that catches **unbalanced
XML/HTML tags** inside fenced blocks an LLM emits in markdown.

LLMs routinely produce XML/HTML/SVG fragments with one of these
defects:

1. an open tag with no close (`<config>...EOF`),
2. a close tag for something that was never opened
   (`...</extra>`),
3. crossed nesting (`<a><b></a></b>`).

The model has no parser in its loop, so it cannot see the imbalance.
Downstream XML parsers raise; downstream HTML parsers silently
auto-close into a tree that diverges from what the model intended.
This detector flags it at emit time so the model can be re-prompted
before the doc ships.

## What it flags

| kind | meaning |
|---|---|
| `unmatched_open` | `<foo>` opened, never closed before block end |
| `unexpected_close` | `</foo>` appeared without a matching open |
| `crossed_close` | `</foo>` appeared but the most recent open is something else; reported with `open_line=` of the matching open |

Self-closing tags (`<br/>`, `<img/>`) are ignored. XML declarations
(`<?xml ?>`), processing instructions, comments, CDATA sections, and
DOCTYPEs are skipped by replacing them with whitespace (so line
numbers stay accurate). HTML void elements (`br`, `hr`, `img`,
`input`, `meta`, `link`, `area`, `base`, `col`, `embed`, `source`,
`track`, `wbr`, `param`) are treated as self-closing so plain HTML
doesn't drown the report.

## Usage

```sh
python3 detect.py examples/bad.md
python3 detect.py examples/good.md
```

Findings go to stdout, one per line:

```
block=<N> line=<L> kind=<unmatched_open|unexpected_close|crossed_close> tag=<t> [open_line=<L0>]
```

Summary `total_findings=<N> blocks_checked=<M>` is printed to stderr.
Exit code is `1` if any findings, `0` otherwise.

Only fenced blocks tagged `xml`, `html`, `svg`, `xhtml`, `rss`,
`atom`, or `plist` (case-insensitive) are inspected.

## Worked example — bad input

`examples/bad.md` contains three blocks that exercise all three
finding kinds.

```
$ python3 detect.py examples/bad.md
block=1 line=6 kind=crossed_close tag=config open_line=1
block=2 line=2 kind=crossed_close tag=p open_line=2
block=2 line=2 kind=unexpected_close tag=strong
block=3 line=4 kind=unexpected_close tag=extra
# stderr: total_findings=4 blocks_checked=3
# exit:   1
```

Read across the findings: block 1 closes `</config>` while `<server>`
is still open — reported as a crossed close of `config` because that's
the structural failure (the comment "forgot to close server" inside
the snippet is the smoking gun). Block 2 has classic `<strong>` /
`</strong>` crossed with `<p>` / `</p>`. Block 3 has a stray
`</extra>` after the document is already fully closed.

## Worked example — good input

`examples/good.md` exercises the negative cases that must NOT fire:

- A balanced XML config tree.
- HTML with void elements (`<br>`, `<hr>`, `<img/>`) that have no
  closer — must not be reported as `unmatched_open`.
- A comment that contains `<fake-tag>` text — must be ignored.
- An XML declaration `<?xml ?>`, a CDATA section containing
  `if (a < b)`, and entity-escaped `&lt;` / `&gt;` in element
  text — none must be parsed as tags.

```
$ python3 detect.py examples/good.md
# stderr: total_findings=0 blocks_checked=3
# exit:   0
```

## Composition

- Pair with `llm-output-fenced-code-language-tag-missing-detector`
  to catch XML emitted without any fence tag at all.
- Pair with `llm-output-toml-duplicate-key-detector` and
  `llm-output-json-duplicate-key-detector` for full
  structured-format coverage at emit time.
- A grammar/lint detector (e.g. via `xml.etree.ElementTree.fromstring`
  in the consuming pipeline) catches things this one deliberately
  skips (attribute quoting, entity correctness, namespace prefix
  balance).

## Files

- `detect.py` — checker.
- `examples/bad.md` — markdown with three unbalanced blocks.
- `examples/good.md` — markdown with three balanced blocks
  (including the tricky cases).
- `README.md` — this file.

Stdlib only. Tested on Python 3.9+.
