# llm-output-snobol-code-detector

Pure-stdlib python3 single-pass scanner that flags SNOBOL4's
dynamic-execution sinks: `CODE()`, `EVAL()`, `APPLY()`, and `LOAD()`.

## What it detects

SNOBOL4 is a string-processing language with a *very* sharp eval edge:
the built-in `CODE` function takes a string of SNOBOL4 source, compiles
it on the fly, and returns an object that — when assigned to a label
variable and branched to — becomes part of the running program's
control flow. `EVAL` does the same thing for an expression. If the
string came from upstream input you have the same blast radius as
`eval($USER_INPUT)` in any other language — and SNOBOL4 implementations
(SPITBOL, CSNOBOL4) routinely ship with `HOST()` / `SYSTEM()` for
shell access, so the attacker reaches out of the interpreter trivially.

| Sink         | Hazard                                                                |
| ------------ | --------------------------------------------------------------------- |
| `CODE(s)`    | Compile string `s` as SNOBOL4 source; returned object is branched to. |
| `EVAL(s)`    | Evaluate an expression string at run time.                            |
| `APPLY(s,…)` | Call a function whose name is given as a string (SPITBOL extension).  |
| `LOAD(s)`    | Load an external function from a shared library named in `s`.         |

LLM-emitted SNOBOL4 reaches for `CODE` to "build a chunk of program
from a template". That is almost always wrong. Safe forms:

* keep a closed allowlist of verbs and dispatch on them with the
  pattern-match-and-`:S(LABEL)` idiom;
* never feed a string built from upstream input into `CODE` or
  `EVAL`;
* never pass an upstream-controlled library name to `LOAD`.

## What gets scanned

* Files with extension `.sno`, `.snobol`, `.spt`, `.sbl` (always
  treated as SNOBOL4).
* Files whose first line is a SNOBOL4-ish shebang (`snobol4`,
  `spitbol`, `csnobol4`).
* Directories are recursed.

## Suppression marker

A trailing `* CODE-OK` (case-insensitive, anywhere on the line as
long as preceded by `*`) suppresses that line.

```snobol
        OBJ = CODE(SAFE.SRC)            * CODE-OK literal source, not user input
```

## False-positive notes

* The trigger words inside `'...'` or `"..."` string literals (with
  doubled-quote escapes properly tracked) are scrubbed before
  scanning.
* Full-line comments (`*` in column 1) are skipped entirely.
* User-defined names that merely *contain* the trigger token —
  `CODES`, `EVALUATE`, `APPLYALL`, `LOADER` — are NOT flagged. The
  regex requires no SNOBOL4 identifier character (`A-Za-z0-9_.`) on
  the left and a `(` on the right.
* `DEFINE()` over a literal prototype string is the standard way to
  define functions in SNOBOL4 and is deliberately out of scope.
* `HOST()` and `SYSTEM()` are direct shell-out hazards in their own
  right; a separate detector covers them.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: snobol-<sink> — <stripped source line>
# <N> finding(s)
```

## Live smoke test

```
$ python3 detect.py examples/bad/
examples/bad/bad1.sno:3:15: snobol-code — OBJ = CODE(USERSRC)             :S<OBJ>
examples/bad/bad2.sno:4:18: snobol-eval — OUTPUT = EVAL(EXPR)
examples/bad/bad3.spt:6:9: snobol-apply — APPLY(FNAME)
examples/bad/bad4.sno:3:9: snobol-load — LOAD('FOO()', LIBNAME)
examples/bad/bad5.sno:3:15: snobol-code — OBJ = code(SRC)                 :S<OBJ>
examples/bad/bad6.sno:2:15: snobol-code — OBJ = CODE(USERSRC)
examples/bad/bad6.sno:3:17: snobol-eval — EXTRA = EVAL(USEREXPR)
# 7 finding(s)

$ python3 detect.py examples/good/
# 0 finding(s)
```

`bad/` has 6 files producing 7 findings (bad6 contains both `CODE` and
`EVAL` on consecutive lines). `good/` has 4 files producing 0
findings: a closed-allowlist dispatcher, a file where trigger words
appear only inside string literals or full-line comments, an audited
use suppressed with `* CODE-OK`, and four user-defined functions
whose names merely contain the trigger substring.

## Implementation notes

* Single-pass per line; full-line `*`-in-column-1 comments are
  skipped before scrubbing.
* Each line has `'...'` and `"..."` string contents blanked
  column-preservingly (with the SNOBOL4 doubled-quote escape) before
  the regex runs.
* SNOBOL4 has no block comments and no backslash escapes inside
  strings; the scrubber matches that.
* The regex matches both upper and lower case to accommodate
  case-insensitive CSNOBOL4 dialects.
* No third-party deps. python3 stdlib only (`re`, `sys`, `pathlib`).
