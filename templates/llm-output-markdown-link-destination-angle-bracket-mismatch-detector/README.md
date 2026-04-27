# llm-output-markdown-link-destination-angle-bracket-mismatch-detector

## Problem

CommonMark inline links accept two destination forms:

```
[text](https://example.com)
[text](<https://example.com>)
```

The second form (angle-bracketed) is useful when the URL contains spaces or
characters that would otherwise terminate the destination. But the angle
brackets must be **balanced**. LLM output frequently produces half-open
variants like:

- `[text](<https://example.com)`  — opening `<`, no closing `>`
- `[text](https://example.com>)`  — closing `>`, no opening `<`
- `[text](<https://exa<mple.com>)` — extra `<` inside the wrap

Most renderers fall back to literal text on these, so the link silently
breaks. This detector catches all three patterns plus stray `<`/`>` in bare
destinations.

## Usage

```sh
python3 detector.py path/to/file.md
```

Exit code: `0` clean, `1` if any file has at least one finding.

Fenced code blocks and inline code spans are skipped.

## Worked example

```sh
$ python3 detector.py examples/bad.md
examples/bad.md:3: opening '<' without closing '>': (<https://example.com/docs)
examples/bad.md:5: closing '>' without opening '<': (https://example.com/api>)
examples/bad.md:7: nested or extra angle bracket inside <...>: (<https://example.com<inner>)
examples/bad.md:9: stray '<' or '>' in bare destination: (https://example.com>extra)

$ python3 detector.py examples/good.md
$ echo $?
0
```

## Limitations

- Does not parse the URL contents; it only inspects the bracket structure.
- Inline-code stripping is a regex approximation; pathological backtick
  patterns may slip through.
- Does not handle reference-style links (`[text][label]`) — those have no
  inline destination to check.
