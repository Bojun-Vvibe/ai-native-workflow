# llm-output-php-loose-equality-detector

## Purpose

Detect PHP loose-equality operators (`==`, `!=`, `<>`) in source code.
Strict comparison (`===`, `!==`) is the recommended default for
production PHP because it avoids type juggling.

PHP's loose-equality operators famously produce results that surprise
even experienced developers:

```
0 == "abc"        // true on PHP < 8
"1" == "01"       // true
"10" == "1e1"     // true
100 == "1e2"      // true
null == false     // true
[] == false       // true
```

These are not exotic edge cases — they routinely cause auth bypasses
and silent data corruption when applied to user input, IDs, tokens,
or configuration values.

## Why LLMs emit this anti-pattern

- The training corpus contains a large amount of legacy PHP 5 code
  written before strict comparison was idiomatic.
- Cross-contamination from JavaScript and Python where `==` is the
  default equality operator.
- "Equal" is the obvious one-token completion; reaching for `===`
  requires the model to remember PHP-specific style.
- Code in tutorials and SO answers from 2010-2015 still dominates and
  almost universally uses `==`.

## When to use

- Reviewing LLM-generated PHP (`.php`, `.phtml`, `.inc`) before merge.
- CI lint over a sample / examples directory.
- Pre-commit lint on agent-authored PHP code.

## How to run

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exit code is `1` if any findings, `0` otherwise. Findings print as
`path:line:col: <kind> — <snippet>`.

## What it flags

- `eq` — `==` (loose equality)
- `ne` — `!=` (loose inequality)
- `angle-ne` — `<>` (alternate spelling of `!=`)

## What it intentionally skips

- `===` and `!==` — the recommended strict forms.
- `=>` (array key arrow), `<=>` (spaceship), `<=`, `>=` — unrelated
  operators that share a character.
- The literal characters `==`, `!=`, `<>` inside `//`, `#`, and
  `/* */` comments.
- The literal characters inside `'...'`, `"..."`, and heredoc/nowdoc
  string bodies.

The detector is a single-pass scanner with explicit comment/string
masking, not a full PHP parser; it errs toward false negatives on
heavily DSL-style code rather than false positives on plain code.

## Files

- `detect.py` — the detector (python3 stdlib only).
- `bad/` — four PHP files that MUST trigger.
- `good/` — two PHP files that MUST NOT trigger.
- `smoke.sh` — runs the detector on `bad/` and `good/` and asserts
  bad-hits > 0 and good-hits == 0.

## Smoke output

```
$ bash smoke.sh
bad_hits=10
good_hits=0
OK: bad=10 good=0
```

## How to fix the findings

- Replace `==` with `===` and `!=`/`<>` with `!==`.
- For comparing secrets (tokens, hashes, HMACs), use `hash_equals()`
  to also avoid timing attacks.
- If you genuinely want type juggling (rare), document it explicitly
  with a comment and a cast: `if ((int)$a === (int)$b)` is clearer
  than relying on `==`.
