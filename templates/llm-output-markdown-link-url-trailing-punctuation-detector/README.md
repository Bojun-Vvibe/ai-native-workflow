# llm-output-markdown-link-url-trailing-punctuation-detector

Flags markdown inline links of the form `[text](url)` whose URL
ends with sentence punctuation: `.` `,` `;` `:` `!` `?`.

## What it detects

LLMs frequently capture sentence terminators inside the URL portion
of a link, producing dead 404 targets. Example:

```
See [the docs](https://example.com/page.).
```

The trailing `.` is the end of the sentence, not part of the URL.
The corrected form is:

```
See [the docs](https://example.com/page).
```

## Why it matters for LLM-generated markdown

- Broken targets: the captured punctuation produces real HTTP 404s
  that don't exist anywhere on the destination site.
- Hidden in review: the rendered link text looks identical, so
  human reviewers rarely notice until users click.
- Crawlable consequence: docs published from LLM output get linkrot
  flagged by external link checkers; this catches the failure mode
  at authoring time, not after publishing.

The detector is **code-fence aware** (skips ``` and ~~~ blocks)
and ignores inline-code spans (text between single backticks on
the same line), so deliberately-illustrative bad links inside
documentation prose are not flagged.

## Usage

```
python3 detect.py path/to/file.md
```

## Exit codes

| code | meaning |
| --- | --- |
| 0 | no findings |
| 1 | findings printed to stdout |
| 2 | usage error |

Output format: `<file>:<line>:<col>: link URL ends with '<char>': <url>`

## Worked example

Run against `examples/bad.md`:

```
$ python3 detect.py examples/bad.md
examples/bad.md:3:44: link URL ends with '.': https://example.com/page.
examples/bad.md:5:20: link URL ends with ',': https://acme.test/foo,
examples/bad.md:7:33: link URL ends with ';': https://x.test/a;
examples/bad.md:7:61: link URL ends with '!': https://y.test/b!
examples/bad.md:9:23: link URL ends with '?': https://example.com/?q=hi?
$ echo $?
1
```

Run against `examples/good.md`:

```
$ python3 detect.py examples/good.md
$ echo $?
0
```

The bad file contains 5 findings across 4 lines. The inline-code
example on line 13 and the fenced-code example on line 17 are
correctly ignored. The good file has zero findings — it includes
both an intentionally-bad link inside inline code and inside a
fence to confirm the suppressors work.
