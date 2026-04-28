# llm-output-tcl-eval-detector

Pure-stdlib python3 single-pass scanner that flags `eval STRING` calls
in Tcl/Tk/Expect source files.

## What it detects

In Tcl, `eval ARG ?ARG ...?` concatenates its arguments with spaces and
re-parses the result as a Tcl script. Whenever any argument holds
attacker- or user-controlled text, `eval` is a code-injection sink with
the same blast radius as `system($USER_INPUT)` in shell.

LLM-emitted Tcl reaches for `eval` to "splice a command that lives in
a variable" — almost always the wrong tool. The modern, safe forms
are:

* `{*}$cmd_list` (Tcl 8.5+ argument expansion)
* direct invocation: `command $arg1 $arg2 ...`
* never `eval $cmd`

The detector flags `eval` at command position, regardless of whether
the argument is quoted, interpolated, command-substituted, or a braced
literal — `eval` itself is the smell. Suppress an audited line with a
trailing `;# eval-ok` (or `# eval-ok`) comment.

## What gets scanned

* Files with extension `.tcl`, `.tk`, `.itcl`, `.exp`.
* Files whose first line is a shebang containing `tclsh`, `wish`, or
  `expect`.
* Directories are recursed.

## False-positive notes

* `eval` inside a `#` comment or inside a `"..."` literal is masked
  out before scanning, so it is never flagged unless it is the
  command-position token itself.
* A proc/variable named `evaluate`, `eval_log`, `tcleval`, etc. is
  NOT flagged — the regex requires `\beval\b` followed by whitespace.
* `# eval-ok` (or `;# eval-ok`) on a line suppresses that line entirely.
* The detector does not try to prove a string is constant — braced
  literal `eval {puts ok}` is still flagged. Add `# eval-ok` if it's
  intentional.
* `uplevel`, `interp eval`, `subst -nocommands` are NOT flagged —
  they are different (also dangerous) constructs and out of scope for
  this single-purpose detector.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: tcl-eval — <stripped source line>
# <N> finding(s)
```

## Smoke test (verified)

```
$ python3 detect.py examples/bad.tcl
examples/bad.tcl:5:1: tcl-eval — eval $cmd                                  ;# 1: variable into eval
examples/bad.tcl:8:1: tcl-eval — eval "$action"                             ;# 2: quoted variable into eval
examples/bad.tcl:10:13: tcl-eval — set result [eval [list puts $action]]     ;# 3: command-substitution into eval
examples/bad.tcl:14:1: tcl-eval — eval "deploy_$target --force"          ;# 4: interpolated string into eval
examples/bad.tcl:19:1: tcl-eval — eval {puts "hello world"}                  ;# 5: braced-literal eval
examples/bad.tcl:22:23: tcl-eval — if {$cmd ne ""} then { eval $cmd }         ;# 6: after `then`
examples/bad.tcl:23:35: tcl-eval — if {$cmd eq ""} { puts no } else { eval $cmd }  ;# 7: after `else`
examples/bad.tcl:26:9: tcl-eval — set x 1; eval $cmd                         ;# 8: after `;`
# 8 finding(s)

$ python3 detect.py examples/good.tcl
# 0 finding(s)
```

bad: **8** findings, good: **0** findings.
