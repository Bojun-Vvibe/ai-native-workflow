# llm-output-forth-evaluate-detector

Pure-stdlib python3 single-pass scanner that flags Forth's
`EVALUATE`, `INTERPRET`, and `INCLUDED` words — the ANS-Forth
text-interpreter sinks that re-enter the parser on a runtime
string buffer.

## What it detects

Forth's standard word `EVALUATE ( c-addr u -- )` takes a counted
string from the data stack and re-enters the text interpreter on it.
Whatever bytes happen to live at `c-addr` for `u` chars become Forth
source code at run time. That is the same blast radius as
`eval($USER_INPUT)` in any other language.

Sibling sinks flagged here:

| Word        | Hazard                                                        |
| ----------- | ------------------------------------------------------------- |
| `EVALUATE`  | Re-parses the string on the stack as Forth source.            |
| `INTERPRET` | Older / Gforth name for the inner text interpreter loop.      |
| `INCLUDED`  | Loads + evaluates the file whose name is on the stack.        |

LLM-emitted Forth sometimes reaches for `EVALUATE` to "splice a word
that lives in a string buffer". That is almost always wrong. The safe
forms are:

* compile the word once with `: name ... ;` and execute it;
* keep an XT (execution token) and `EXECUTE` it, never re-parse;
* if you really must re-parse, isolate the call inside an audited
  word and add a `\ evaluate-ok` suppression marker on that line.

## What gets scanned

* Files with extension `.fs`, `.fth`, `.4th`, `.forth`.
* Files whose first line is a Forth-ish shebang (`gforth`, `pforth`,
  `vfx`, `swiftforth`).
* `.f` is deliberately NOT auto-claimed — that suffix collides with
  Fortran fixed-form decks. Add a shebang or rename if you want it
  scanned.
* Directories are recursed.

## Suppression marker

A trailing `\ evaluate-ok` (line comment form) or `( evaluate-ok )`
(paren comment form) on the same line suppresses that line entirely.

```forth
s" : init ; init" EVALUATE  \ evaluate-ok  audited, constant string
```

## False-positive notes

* `EVALUATE` / `INTERPRET` / `INCLUDED` mentioned inside a `\ ...`
  line comment, a `( ... )` paren comment, or any of the string
  literals `S" ... "`, `." ... "`, `C" ... "`, `ABORT" ... "` is
  scrubbed before scanning and is never flagged.
* Words whose names merely *contain* the trigger token —
  `my-evaluator`, `reinterpret-bits`, `includedness` — are NOT
  flagged. The regex requires a whitespace-bounded exact bareword
  match, which matches Forth's own tokenization.
* Case-insensitive: `evaluate` and `EVALUATE` are both flagged.
* `EXECUTE` of an XT is the safe pattern and is NOT flagged.
* `POSTPONE`, `[COMPILE]`, `SH`, `SYSTEM` are out of scope.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: forth-<sink> — <stripped source line>
# <N> finding(s)
```

## Live smoke test

Run against the bundled examples:

```
$ python3 detect.py examples/bad/
examples/bad/bad1.fs:3:15: forth-evaluate — S" 2 2 + ." EVALUATE
examples/bad/bad2.fs:3:20: forth-evaluate — user-buf @ count EVALUATE
examples/bad/bad3.fth:5:5: forth-interpret — INTERPRET
examples/bad/bad4.fs:3:3: forth-included — INCLUDED
examples/bad/bad5.4th:3:21: forth-evaluate — s" 1 cells allot" evaluate
examples/bad/bad6.fs:2:19: forth-evaluate — : a ( -- )  s" ." EVALUATE ;
examples/bad/bad6.fs:3:24: forth-included — : b ( -- )  s" foo.fs" INCLUDED ;
# 7 finding(s)

$ python3 detect.py examples/good/
# 0 finding(s)
```

`bad/` has 6 files producing 7 findings (bad6.fs has two sinks).
`good/` has 4 files producing 0 findings: an `EXECUTE`-of-XT pattern,
a file where the trigger word appears only inside comments and
strings, an audited use suppressed with `\ evaluate-ok`, and three
benign words whose names merely contain the trigger substring.

## Implementation notes

* Single-pass per line: scrub Tcl-style (here, Forth-style) comments
  and string literals to spaces, then run a bareword regex.
* No third-party deps. python3 stdlib only (`re`, `sys`, `pathlib`).
* Forth is whitespace-delimited, so a `(?:^|(?<=\s))WORD(?=\s|$)`
  regex is exact and there is no need for a real tokenizer.
