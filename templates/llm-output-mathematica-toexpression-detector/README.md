# llm-output-mathematica-toexpression-detector

Pure-stdlib python3 single-pass scanner that flags Wolfram Language
/ Mathematica dynamic-code execution sinks (`ToExpression`, `Get`,
`<<`, `Needs`, `Run`, `RunProcess`) in `.m` / `.wl` / `.wls` source
files.

## What it detects

Wolfram Language has several ways to take a string (or a path) and
evaluate it as code. All are code-injection sinks when the input is
attacker- or LLM-controlled:

* `ToExpression[s]` — parses `s` as Wolfram source and evaluates it
  in the current context. The canonical "eval a string" sink.
* `ToExpression[s, fmt]` and `ToExpression[s, fmt, head]` — same
  hazard; `fmt` only picks the parser, `head` only wraps the
  result.
* `Get[path]` and the operator form `<< path` — read a `.m` / `.wl`
  file and evaluate it. With a non-literal path this is arbitrary
  code by another name.
* `Needs[ctx, path]` — if `path` is computed from input, same
  hazard as `Get`.
* `RunProcess[…]` and `Run[…]` — shell out (separate hazard
  class — command injection rather than expression injection — but
  same root cause when the operand flows from input).

LLM-emitted Wolfram code reaches for `ToExpression` to "evaluate
an expression the user typed" or `<<` to "load whatever package
the config names" — almost always wrong. Safer alternatives:

* `Switch[op, "name1", expr1, "name2", expr2, _, $Failed]` for
  small allowlist dispatch,
* `Association[...]` / `Lookup` for data-driven dispatch over
  pre-defined functions,
* `Symbol[name]` if you really only need a symbol reference (it
  does **not** evaluate as source).

## What this template gives you

* `detect.py` — single-pass scanner; pure python3 stdlib.
* `examples/bad/` — 7 worked positive cases (`ToExpression` 1-,
  2-, 3-arg forms, `Get`, `<<` operator, `Needs`,
  `RunProcess` / `Run`) — 8 findings total (`07_runprocess_run.wl`
  has both `RunProcess` and `Run`).
* `examples/good/` — 6 worked negative cases (`Switch` allowlist,
  in comments, in strings, suppressed call, `Symbol[]`, nested
  `(* (* … *) *)` comments).
* `verify.sh` — end-to-end check: asserts `bad ≥ 6`, `good == 0`,
  and the detector exits with the conventional 1/0.

## Usage

```sh
python3 detect.py path/to/file.wl
python3 detect.py path/to/dir/
```

Prints `path:line:col: wolfram-eval — <stripped source line>` per
finding and a `# N finding(s)` summary. Exits 1 on any finding,
0 otherwise.

### Suppression

A trailing `(* eval-ok *)` comment on the line silences a single
finding. Use sparingly and only when the argument is a static
literal under your control:

```mathematica
ToExpression["1 + 1"]  (* eval-ok *)
```

## File-type detection

Scans files with `*.m` / `*.wl` / `*.wls` extensions, plus any file
whose first line is a `wolframscript` or `MathKernel` shebang.

Note: `*.m` is shared with Objective-C; if your repo has a lot of
Objective-C alongside Wolfram, point `detect.py` at the Wolfram
subtree only.

## Comment + string masking

Wolfram comments are `(* … *)` and **may nest**. The detector
tracks nesting depth across lines so that `Get[bad]` inside a
nested inner comment does not flag. Strings are double-quoted with
`\\` escapes; `Get`-shaped substrings inside strings do not flag.

## Out of scope

* `Symbol[name]` — turns a string into a symbol but does not
  evaluate it as source.
* `Hold` / `HoldComplete` wrappers — these are usually defensive,
  but we still flag the underlying call site so a reviewer can
  confirm the hold is in fact respected downstream.

## Verify

```sh
./verify.sh
```

Expected output:

```
bad findings:  8 (rc=1)
good findings: 0 (rc=0)
OK: mathematica-toexpression detector verified (bad=8, good=0)
```
