# llm-output-octave-eval-detector

Pure-stdlib python3 single-pass scanner that flags
`eval` / `evalin` / `feval` / `assignin` calls in GNU Octave (and
MATLAB) source files.

## What it detects

In Octave/MATLAB, `eval(STR)` parses STR as Octave source and runs it
in the calling workspace; `evalin(WS, STR)` does the same in a named
workspace (`'base'` or `'caller'`); `feval(FN, ...)` calls a function
whose name is given by string FN; `assignin(WS, NAME, V)` writes a
variable named by string NAME into a workspace. All four are
dynamic-code sinks: any caller-controlled fragment in the string
becomes runnable Octave code, with full filesystem and shell access.

LLM-emitted Octave code reaches for `eval` to "build a variable name
from a loop index" (e.g. `eval(['x' num2str(i) ' = 0'])`). The safe
replacements are almost always:

* a struct field — `x.(sprintf('f%d', i)) = 0`
* a cell array — `x{i} = 0`
* a function handle — `fn = @sin; fn(x)` instead of
  `feval('sin', x)`

## What gets scanned

* Files with extension `.octave` (always).
* Files with extension `.m` that do **not** contain Objective-C
  markers (`#import`, `@interface`, `@implementation`, `@protocol`)
  in the first 4 KiB.
* Directories are recursed.

## False-positive notes

* `%`-comments and `#`-comments are masked.
* `'...'` strings (with `''` for embedded apostrophe) and `"..."`
  strings (with `\` escapes) are masked. The `'` is correctly treated
  as transpose (not string start) when it follows an identifier, `)`,
  `]`, `}`, or `.` — so `A' * A` does NOT enter a phantom string.
* A method-style call `obj.eval(s)` is NOT flagged — the lookbehind
  `(?<![A-Za-z0-9_.])` rejects names preceded by `.`.
* A user function literally named `evaluate_score` is NOT flagged —
  the regex requires `\beval\s*\(`, not `evaluate`.
* Suppress an audited line with a trailing `% eval-ok` (or
  `# eval-ok`) comment.
* `str2func`, `system`, `unix`, `dos`, `popen` are out of scope —
  they are different (also dangerous) constructs.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: octave-eval|evalin|feval|assignin — <line>
# <N> finding(s)
```

## Worked example

```
$ python3 detect.py examples/bad.m
examples/bad.m:5:5: octave-eval — eval(['x' num2str(i) ' = ' num2str(i*i) ';']);
examples/bad.m:10:7: octave-evalin — v = evalin('caller', name);
examples/bad.m:14:7: octave-feval — r = feval(fname, x);
examples/bad.m:18:3: octave-assignin — assignin('base', vname, val);
examples/bad.m:22:3: octave-eval — eval(s, 'disp("eval failed")');
examples/bad.m:26:11: octave-eval — y = 1 + eval(s);
examples/bad.m:31:3: octave-assignin — assignin('caller', name, val); evalin('caller', name);
examples/bad.m:31:34: octave-evalin — assignin('caller', name, val); evalin('caller', name);
# 8 finding(s)

$ python3 detect.py examples/good.m
# 0 finding(s)
$ echo $?
0
```

`examples/bad.m` has 7 dangerous lines yielding 8 findings (line 31
chains `assignin` and `evalin`). `examples/good.m` has 8
deliberately-tricky shapes (struct field, function handle, cell array,
transpose `'`, `eval` mention inside `%`-comment, `eval` text inside
`'...'` and `"..."` literals, `evaluate_score` look-alike, method
`obj.eval(s)`, audited `% eval-ok` line) — all must produce zero
findings.

## Why this matters

`eval(['x' num2str(i) ' = 0'])` is the canonical "build a variable
name in a loop" antipattern that LLMs emit confidently for Octave/
MATLAB. It silently grants the input string full code execution and
defeats every static-analysis pass downstream. This detector turns it
into a PR-time conversation instead of a post-incident forensic.
