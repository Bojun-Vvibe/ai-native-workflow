# llm-output-hy-eval-detector

Single-pass Python stdlib scanner that detects dangerous dynamic-evaluation
patterns in [Hy](https://hylang.org/) (a Lisp on top of Python) source code,
as commonly produced by LLM code generation when asked for "load this script
at runtime" or "let users extend the program."

## What it flags

| Pattern | Why it's dangerous |
| --- | --- |
| `(eval ...)` | Evaluates an arbitrary form at runtime — full RCE if the form is built from untrusted data. |
| `(hy.eval ...)` | Explicit Hy eval; same risk as `eval`. |
| `(hy.read ...)` / `(hy.read-many ...)` | Parses a string into a Hy form — almost always followed by `eval`; flagging the parse step catches the precursor. |
| `(hy.eval-and-compile ...)` | Compile-and-eval; same risk as `eval` plus side effects at compile time. |
| `(exec ...)` | Hy exposes Python `exec`; arbitrary statement execution. |
| `(compile ... "exec")` | Python `compile(..., "exec")` followed by `exec` is a common bypass for naive `eval` greps. |

## How it works

1. Read each `.hy` file.
2. **Mask** comments (`;` to end of line), single-line strings (`"..."`,
   `'...'`), triple-quoted strings, and Hy bracket-strings (`#[[ ... ]]`)
   by replacing their bytes with spaces. This preserves line/column offsets
   so reported line numbers match the original source.
3. Run a small set of regexes against the masked text.
4. Print one finding per line in `path:line: hy-dynamic-eval[name]: <code>`.

The masker means a comment like `; don't use (eval x)` does **not** trigger
the detector, and neither does a string literal that contains the word
`eval`.

## Run

```bash
python3 detector.py path/to/source.hy
python3 detector.py path/to/dir/
```

Exit code = number of findings (capped at 255), so it's CI-friendly.

## Verify with bundled examples

```bash
./run-example.sh
```

The script runs the detector over `examples/bad/` (expects ≥6 findings,
one per file) and `examples/good/` (expects 0 findings) and prints `OK`
on success.

| Bucket | Count | Expectation |
| --- | --- | --- |
| `examples/bad/` | 6 files | every file produces ≥1 finding |
| `examples/good/` | 4 files | zero findings |

## Limitations

- Hy bracket-string masking handles the simple `#[[ ... ]]` form. Custom
  delimiters (`#[delim[ ... ]delim]`) are not parsed precisely.
- The detector matches on the syntactic call shape; macros that wrap
  `eval` under another name will not be caught. Treat this as a lint, not
  a soundness proof.
- Multi-line nested s-expressions are matched on the opener; the actual
  argument is not evaluated.
