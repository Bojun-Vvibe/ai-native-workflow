# llm-output-wren-meta-eval-detector

Single-pass Python stdlib scanner that detects use of [Wren](https://wren.io/)'s
optional `meta` module APIs that compile or evaluate strings as code at
runtime. LLM-generated Wren scripts often reach for `Meta.eval` when asked
to "make this scriptable" or "let users write expressions" — a textbook RCE
sink.

## What it flags

| Pattern | Why it's dangerous |
| --- | --- |
| `Meta.eval(s)` | Compiles and runs `s` as Wren source in the current module — full RCE if `s` derives from untrusted input. |
| `Meta.compile(s)` | Compiles `s` into a callable `Fn`. Every later `.call()` re-executes the attacker payload; flagging the compile catches the precursor. |
| `Meta.compileExpression(s)` | Same as `Meta.compile` but for expressions; same risk. |

## How it works

1. Read each `.wren` file.
2. **Mask** `//` line comments, `/* ... */` block comments, and
   `"..."` string literals by replacing their bytes with spaces (newlines
   preserved). This keeps reported line numbers accurate while removing
   false positives where code is only quoted or commented.
3. Run a small set of regexes (anchored by `\bMeta\s*\.\s*eval`, etc.)
   against the masked text.
4. Emit one finding per line: `path:line: wren-dynamic-eval[name]: <code>`.

## Run

```bash
python3 detector.py path/to/file.wren
python3 detector.py path/to/dir/
```

Exit code = number of findings (capped at 255).

## Verify

```bash
./run-example.sh
```

Expects ≥6 findings across `examples/bad/` (6 files, each ≥1) and 0
findings across `examples/good/` (4 files).

## Limitations

- Wren block comments (`/* ... */`) **do** nest. The masker treats them
  as non-nesting, which can cause **over-masking** (we may swallow more
  text than necessary) but never **under-masking**. If you have deeply
  nested block comments containing real `Meta.eval` calls, those calls
  would be missed; this is by design — the detector errs on the side of
  fewer false positives at the cost of some false negatives in unusual
  comment structures.
- The scanner does not track aliasing: `var M = Meta` followed by
  `M.eval(x)` is not flagged. Treat as a lint, not a soundness proof.
- Foreign-class shenanigans (a host-defined class also named `Meta` with
  innocuous `eval`) would produce false positives.
