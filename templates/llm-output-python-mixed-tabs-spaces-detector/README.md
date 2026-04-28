# llm-output-python-mixed-tabs-spaces-detector

Pure-stdlib, code-fence-aware detector that flags Python code
blocks where tab and space characters are mixed in indentation —
either within a single line's leading whitespace, or across the
lines of a single block.

Python 3 makes some forms of tab/space mixing a hard `TabError`,
but not all of them. The cases it does *not* catch are the
dangerous ones: a block that is uniformly tab-indented on some
lines and space-indented on others can parse and *run* but mean
something different than the author intended (the rule is "tabs
expand to the next multiple of 8 for tokenisation", but the
visual width may be 4 in the editor). LLMs that emit Python in
markdown blocks frequently mix the two when they switch between
copying training data and synthesising new lines, because the
stop/start of generation does not preserve indentation
character-class. This detector flags both forms at emit time so
the output can be re-prompted before it lands in source control.

## What it flags

| kind | meaning |
|---|---|
| `mixed_in_line` | A single line's leading whitespace contains BOTH tab and space characters |
| `block_mixed` | The block has some indented lines that are tab-led and others that are space-led (each line internally pure, but the block disagrees with itself). Reported once per block, on the first disagreeing line |

Recognized fence info-string tags (case-insensitive):
`python`, `py`, `python3`, `py3`.

## Out of scope (deliberately)

- Indent *width* (2 vs 4 vs 8).
- Indent depth consistency across blocks.
- Blank lines (their "indentation" is meaningless).
- Continuation lines inside parentheses.
- Any AST-level analysis.

This is a *first-line-defense* sniff test, not a linter.

## Usage

```
python3 detect.py <markdown_file>
```

Stdout: one finding per line, e.g.

```
block=1 line=2 kind=mixed_in_line detail=lead_repr='\t    '
```

Stderr: `total_findings=<N> blocks_checked=<M>`.

Exit codes:

| code | meaning |
|---|---|
| `0` | no findings |
| `1` | at least one finding |
| `2` | bad usage |

## Worked example

Run against the bundled examples:

```
$ python3 detect.py examples/bad.md
block=1 line=2 kind=mixed_in_line detail=lead_repr='\t    '
block=2 line=3 kind=block_mixed detail=baseline=space@line2 this=tab
block=3 line=2 kind=mixed_in_line detail=lead_repr='\t    '
block=3 line=3 kind=mixed_in_line detail=lead_repr=' \t'
# stderr: total_findings=4 blocks_checked=4
# exit: 1

$ python3 detect.py examples/good.md
# stderr: total_findings=0 blocks_checked=3
# exit: 0
```

In `bad.md`, all four python blocks are scanned. Block 4 is clean
(no findings) but still counted in `blocks_checked`. In `good.md`,
the ruby block is ignored (language tag not in the recognized
set), so `blocks_checked=3`.
