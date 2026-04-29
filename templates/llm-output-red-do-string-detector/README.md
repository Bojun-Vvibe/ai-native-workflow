# llm-output-red-do-string-detector

Single-pass Python stdlib scanner that detects use of [Red](https://www.red-lang.org/)'s
runtime evaluation primitives (`do`, `load`) on strings or words. LLM-generated Red
code reaches for `do user-input` or `do load some-string` whenever asked to "make
this dynamic" — a textbook RCE sink in a homoiconic language.

## What it flags

| Pattern | Why it's dangerous |
| --- | --- |
| `do <expr>` | Evaluates a string/block as Red source; full RCE if `<expr>` derives from untrusted input. |
| `do/expand`, `do/next`, `do/args`, etc. | Refinements of `do`; same risk surface. |
| `load <expr>` | Parses a string into Red values. Often immediately followed by `do`; flagging the `load` catches the precursor. |
| `load/all`, `load/header`, `load/part`, etc. | Refinements of `load`; same risk surface. |

The two work together (`do load remote-string`) — flagging both halves
gives reviewers either side of the chain.

## How it works

1. Read each `.red` / `.reds` file.
2. **Mask** lexical regions so they cannot trigger findings:
   - `;` line comments to end-of-line
   - `"..."` strings with `^` (caret) escapes
   - `{...}` curly-brace strings, **respecting Red's nesting rules**;
     `^{` and `^}` are escaped braces and do not change depth
3. Run word-boundary regexes (`(?<![A-Za-z0-9_!?\-])do(?:/[A-Za-z]+)*`)
   against the masked text. The negative look-behind prevents matches
   inside identifiers like `do-thing` or `load-balancer`.
4. Emit one finding per match: `path:line: red-dynamic-eval[name]: <code>`.

## Run

```bash
python3 detect.py path/to/file.red
python3 detect.py path/to/dir/
```

Exit code = number of findings (capped at 255).

## Verify (bundled examples)

```bash
$ python3 detect.py examples/bad examples/good
examples/bad/02_do_user_input.red:4: red-dynamic-eval[do]: do cmd
examples/bad/01_do_word.red:4: red-dynamic-eval[do]: do user-script
examples/bad/06_load_all.red:4: red-dynamic-eval[load]: config: load/all config-text
examples/bad/06_load_all.red:5: red-dynamic-eval[do]: do config
examples/bad/03_do_expand.red:3: red-dynamic-eval[load]: payload: load/all incoming
examples/bad/03_do_expand.red:4: red-dynamic-eval[do]: do/expand payload
examples/bad/04_load_then_do.red:4: red-dynamic-eval[do]: do load src
examples/bad/04_load_then_do.red:4: red-dynamic-eval[load]: do load src
examples/bad/05_do_next.red:5: red-dynamic-eval[do]: set [val stream] do/next stream
--- 9 finding(s) ---
```

* `examples/bad/` has 6 files; every one is flagged (9 findings total
  because some files exercise both `do` and `load`).
* `examples/good/` has 4 files (string-only mention, comment-only
  mention, `do-thing`/`load-balancer` user words, braced string
  mentioning the words) — all return 0 findings.

## Limitations

- We deliberately do **not** parse Red's `comment` form (e.g.
  `comment {ignored block}`). It is a regular function call rather
  than a lexical construct, and parsing it correctly would require a
  real Red lexer. A literal `do <string>` inside `comment {...}`
  would be flagged as a false positive — acceptable for a lint.
- Aliasing is not tracked: `my-do: :do` followed by `my-do payload`
  is invisible to the scanner. Treat as a lint, not a soundness proof.
- Red is case-insensitive. The regex is `(?i)`, so `DO`, `Do`, and
  `do` all match.
- Red's `{...}` strings nest; the masker honours nesting. If you
  rely on raw braces inside non-string contexts (you shouldn't —
  Red doesn't allow that), the masker would over-consume.
