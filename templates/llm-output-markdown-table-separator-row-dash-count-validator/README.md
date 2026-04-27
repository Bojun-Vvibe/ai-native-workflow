# llm-output-markdown-table-separator-row-dash-count-validator

Flags GitHub-flavored markdown table **separator rows** whose dash
segments have inconsistent dash counts within the same row.

## What it detects

A separator row like

```
| --- | -- | ------ |
```

renders fine in most clients but reads as sloppy in diffs and gets
re-flowed inconsistently by formatters. LLMs frequently emit these
when they are estimating column widths from header text and round
unevenly. This validator forces every dash segment in one separator
row to share the same dash count.

It is **code-fence aware**: any separator row inside a fenced code
block (``` or ~~~) is ignored.

## Why it matters for LLM-generated markdown

- Diff churn: a downstream formatter (prettier, mdformat) will
  rewrite the row, generating noisy diffs on PRs that were
  otherwise content-only.
- Reviewer trust: visually uneven separators look like the model
  miscounted columns even when the data row count is correct.
- Deterministic output: enforcing a single dash count per row makes
  template-generated tables byte-stable across runs.

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

Output format: `<file>:<line>: separator-row dash counts [c1, c2, ...]: <raw line>`

## Worked example

Run against `examples/bad.md`:

```
$ python3 detect.py examples/bad.md
examples/bad.md:6: separator-row dash counts [3, 2, 6]: | --- | -- | ------ |
examples/bad.md:12: separator-row dash counts [3, 2, 4]: |:---|:--:|----:|
$ echo $?
1
```

Run against `examples/good.md`:

```
$ python3 detect.py examples/good.md
$ echo $?
0
```

The bad file contains 2 findings (one plain, one with alignment colons);
the row inside the fenced code block on line 25 is correctly ignored.
