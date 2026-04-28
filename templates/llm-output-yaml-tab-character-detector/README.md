# llm-output-yaml-tab-character-detector

Detects tab characters in YAML output. The YAML spec forbids tab indentation,
but LLMs sometimes emit tabs (especially when copy-pasting from tab-rendered
sources or when asked to "make this YAML"). The failure mode is silent or
loader-dependent: PyYAML errors, some permissive parsers coerce tabs to a
single space and silently change structure.

## What it flags

- **`indent-tab`** — a tab appears in the leading whitespace of a line.
  Reported once per offending line (the worst case).
- **`inline-tab`** — a tab appears after non-whitespace content on a line.
  Less catastrophic, but breaks alignment and round-tripping.

## Usage

```sh
python3 detector.py < input.yaml
```

Output is one finding per line on stdout:

```
line=<N> col=<C> kind=<indent-tab|inline-tab> snippet=<repr-of-first-60-chars>
```

A `total_findings=<N>` summary is printed on stderr. Exit code is always 0
(advisory tool — wire to your own gate).

## Worked example

```sh
$ python3 detector.py < bad.txt
line=3 col=1 kind=indent-tab snippet='\\t- a'
line=4 col=1 kind=indent-tab snippet='\\t- b'
line=7 col=7 kind=inline-tab snippet='  bad:\\tinline-tab-here'
line=9 col=1 kind=indent-tab snippet='\\t\\tdouble-tab-indent: 1'
# stderr: total_findings=4

$ python3 detector.py < good.txt
# stderr: total_findings=0
```

## Why this matters for LLM output

A YAML config with a tab-indented list will:

- Crash strict parsers (PyYAML raises `ScannerError`).
- Silently flatten in lenient parsers, changing list nesting.
- Pass a quick `cat | grep` review because tabs are invisible.

This detector is cheap to run on every LLM YAML emission and catches the
class outright with stdlib only.

## Limits

- Treats *all* tabs as suspect. YAML technically allows tabs inside double-quoted
  scalars and comments; if you intentionally use those, expect false positives
  and post-filter on `kind=indent-tab` only.
- Does not parse YAML — pure lexical scan. That's the point: it must work even
  when the YAML is unparseable.
