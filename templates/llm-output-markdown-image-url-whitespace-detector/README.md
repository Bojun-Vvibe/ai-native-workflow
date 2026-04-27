# llm-output-markdown-image-url-whitespace-detector

Flags markdown image syntax of the form `![alt](url)` whose URL
portion contains a literal space or tab character.

## What it detects

LLMs frequently emit image references where the URL was copied
from a context that included whitespace, or where the model hallucinated
a "human-readable" path with spaces. Example:

```
![diagram](assets/system diagram.png)
```

Markdown renderers will treat the space as the boundary between the
URL and an optional title, so the URL becomes `assets/system` and
the rest is interpreted as a (malformed) title — the image silently
fails to load. The corrected form uses `%20` or, better, a path
without spaces:

```
![diagram](assets/system-diagram.png)
![diagram](assets/system%20diagram.png)
```

A literal tab inside the URL is always wrong and is also flagged.

## Why it matters for LLM-generated markdown

- **Silent rendering failure**: the rendered page shows alt text or
  a broken-image icon, not the diagram. Reviewers reading the source
  often miss it because the syntax "looks fine".
- **Cross-renderer divergence**: some renderers tolerate the space,
  some do not. LLM output that "worked on my machine" breaks in CI
  preview pipelines.
- **Distinguishable from intentional titles**: a real title uses
  the form `![alt](url "title")` with the title quoted. This
  detector only flags URLs whose first whitespace-separated token
  is followed by content that is **not** a quoted title.

The detector is **code-fence aware** (skips ``` and ~~~ blocks)
and ignores inline-code spans (text between single backticks on
the same line), so deliberately-illustrative bad examples inside
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
examples/bad.md:3:1: image URL contains whitespace: 'assets/system diagram.png'
examples/bad.md:5:1: image URL contains whitespace: 'images/figure 2.svg'
examples/bad.md:7:1: image URL contains tab: 'a\tb.png'
$ echo $?
1

$ python3 detect.py examples/good.md
$ echo $?
0
```
