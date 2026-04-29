# llm-output-postscript-exec-detector

Pure-stdlib python3 single-pass scanner that flags PostScript's
dynamic-execution sinks: `exec`, `cvx`, `run`, `token`, and
`filenameforall`.

## What it detects

PostScript is a stack-based, *homoiconic* language: a procedure is just
an array of objects with the executable bit set. Anything reachable
through `exec` is interpreted as code at run time. If the array, the
string fed to `cvx` (convert-to-executable), or the file path passed to
`run` came from upstream, you have the same blast radius as
`eval($USER_INPUT)` in any other language — and the interpreter has
direct access to the host file system (`file`, `deletefile`,
`renamefile`) and to other processes via the `%pipe%` device on most
implementations.

| Sink              | Hazard                                                          |
| ----------------- | --------------------------------------------------------------- |
| `exec`            | Pop the operand and execute it as code.                         |
| `cvx`             | Flip the executable bit on a string/array. Predecessor of `exec`. |
| `run`             | Read a named file and execute its contents as PostScript.       |
| `token`           | Scan one PostScript token from a string and return it executable. |
| `filenameforall`  | Apply a procedure to every matching path; the procedure runs.   |

LLM-emitted PostScript reaches for `cvx exec` to "build a procedure
from a string". That is almost always wrong. Safe forms:

* keep a closed allowlist of literal procedures (`/foo { ... } def`)
  and dispatch on a name token;
* never feed a string built from upstream data into `cvx`;
* never pass an upstream-controlled path to `run`.

## What gets scanned

* Files with extension `.ps`, `.eps` (always treated as PostScript).
* Files whose first line is the PostScript magic `%!PS`.
* Directories are recursed.

PDFs are out of scope: PDF can embed PostScript fragments via
`Action` / `OpenAction` dictionaries, but full PDF parsing belongs to
a dedicated detector.

## Suppression marker

A trailing `% exec-ok` (or `%% exec-ok`) on the same line suppresses
that line.

```postscript
Body exec  % exec-ok  Body is a literal procedure, not user input
```

## False-positive notes

* The trigger words inside a `% ...` line comment, a `(...)`
  parenthesised string (with proper depth tracking and `\` escapes),
  a `<...>` hex string, or a `<~ ... ~>` ASCII85 string are all
  scrubbed before scanning.
* User-defined names that merely *contain* the trigger token —
  `my-exec`, `runner`, `cvxhelp`, `tokenize` — are NOT flagged. The
  regex requires no PostScript-name character (`A-Za-z0-9_-.?!`) on
  either side.
* Dict delimiters `<<` / `>>` are left intact and never scrubbed.
* DSC `%%` directives are treated as line comments.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: postscript-<sink> — <stripped source line>
# <N> finding(s)
```

## Live smoke test

```
$ python3 detect.py examples/bad/
examples/bad/bad1.ps:4:10: postscript-cvx — UserCode cvx exec
examples/bad/bad1.ps:4:14: postscript-exec — UserCode cvx exec
examples/bad/bad2.ps:3:19: postscript-run — (/tmp/payload.ps) run
examples/bad/bad3.eps:4:6: postscript-cvx — Body cvx
examples/bad/bad3.eps:5:1: postscript-exec — exec
examples/bad/bad4.ps:3:8: postscript-token — (quit) token pop exec
examples/bad/bad4.ps:3:18: postscript-exec — (quit) token pop exec
examples/bad/bad5.ps:3:29: postscript-filenameforall — (*.ps) { (found ) print = } filenameforall
examples/bad/bad6.ps:3:18: postscript-run — (/tmp/loader.ps) run
examples/bad/bad6.ps:5:9: postscript-cvx — Payload cvx exec
examples/bad/bad6.ps:5:13: postscript-exec — Payload cvx exec
# 11 finding(s)

$ python3 detect.py examples/good/
# 0 finding(s)
```

`bad/` has 6 files producing 11 findings (bad1, bad3, bad4, bad6 each
contain a paired `cvx`/`exec` or split chain). `good/` has 4 files
producing 0 findings: a closed-allowlist dispatcher, a file where the
trigger words appear only inside comments and strings, an audited use
suppressed with `% exec-ok`, and five user-defined procedures whose
names merely contain the trigger substring.

## Implementation notes

* Single-pass per line.
* Each line has `% ...` line comments, `(...)` parenthesised strings
  (depth-tracked, `\` escapes preserved), `<...>` hex strings, and
  `<~ ... ~>` ASCII85 strings blanked column-preservingly before the
  regex runs.
* `<<` / `>>` dict delimiters are left intact.
* No third-party deps. python3 stdlib only (`re`, `sys`, `pathlib`).
