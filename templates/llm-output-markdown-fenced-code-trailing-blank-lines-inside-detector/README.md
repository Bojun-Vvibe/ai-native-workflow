# llm-output-markdown-fenced-code-trailing-blank-lines-inside-detector

Detects fenced code blocks whose content ends with one or more blank lines
*before* the closing fence — e.g.:

    ```python
    print("hi")


    ```

LLMs often emit this shape when stitching together multi-block outputs. The
trailing blanks bloat copy-paste, shift line numbers in any tool that
extracts the code, and are almost never intentional.

## Why this matters for LLM outputs

- Copy-pasting the block into a file leaves stray empty lines at EOF, which
  some linters (e.g. `gofmt`, `black --check` in some configs) flag.
- Tools that line-number extracted code (eval harnesses, REPL replayers)
  silently shift everything after the block.
- Snippet renderers may add an extra scroll height for the empty rows.

## What it does

- Streams the input file line-by-line.
- Tracks ` ``` ` and `~~~` fence open/close state.
- For each closing fence, reports if the fence had `>= 1` blank
  (whitespace-only) line(s) immediately before it.
- Unclosed fences exit `2` — they are a different bug class and would make
  the count meaningless.
- Exit code: `1` if any offending fence found, else `0`.

## Run

```
python3 detect.py path/to/file.md
python3 detect.py examples/bad.md   # exits 1
python3 detect.py examples/good.md  # exits 0
```

Stdlib only, Python 3.8+.

## Verified output

Against `examples/bad.md` (exit `1`, 3 findings):

```
examples/bad.md:10:1: trailing-blank-lines-inside-fence (fence opened at line 5, 2 blank line(s) before close)
examples/bad.md:18:1: trailing-blank-lines-inside-fence (fence opened at line 14, 2 blank line(s) before close)
examples/bad.md:31:1: trailing-blank-lines-inside-fence (fence opened at line 28, 1 blank line(s) before close)
```

Against `examples/good.md` (exit `0`, no findings, no output).

## Limitations

- Doesn't check leading blanks just after the fence open — that's a
  separate, often-intentional pattern (e.g. shebang spacing).
- Indented code blocks (4-space) are not considered; this rule is
  fence-specific.
- A fence inside a fence (nested via different markers) is treated as
  literal content of the outer fence, matching CommonMark.
