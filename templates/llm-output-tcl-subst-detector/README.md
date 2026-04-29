# llm-output-tcl-subst-detector

Pure-stdlib python3 single-pass scanner that flags **dangerous** Tcl
`subst` calls in `.tcl` / `.tk` / `.itcl` / `.exp` source files.

## What it detects

In Tcl, `subst ?-nobackslashes? ?-nocommands? ?-novariables? STRING`
performs backslash, command, and variable substitution on STRING and
returns the result. By default — i.e. with NO flags — `subst $x` is
equivalent to `eval "return \"$x\""`: any `[cmd]` substring inside
`$x` is **executed**, and any `$var` is interpolated. That makes
plain `subst $user_input` a code-injection sink with the same blast
radius as `eval`.

The flag that disables the dangerous (command-execution) branch is
`-nocommands`. The detector flags any `subst` invocation whose
leading flag block does **not** include `-nocommands`. Other flag
combinations (`-nobackslashes` only, `-novariables` only, no flags
at all) leave `[..]` substitution active and are flagged.

| construct                                                | flagged? |
| :------------------------------------------------------- | :------: |
| `subst $tmpl`                                            | yes      |
| `subst "$header\n$body"`                                 | yes      |
| `subst -nobackslashes $tmpl`                             | yes      |
| `subst -novariables $tmpl`                               | yes      |
| `subst {hello [clock seconds]}`                          | yes      |
| `subst -nocommands $tmpl`                                | NO       |
| `subst -nocommands -novariables $tmpl`                   | NO       |
| `subst -nocommands -novariables -nobackslashes $tmpl`    | NO       |

## What gets scanned

* Files with extension `.tcl`, `.tk`, `.itcl`, `.exp`.
* Files whose first line is a shebang containing `tclsh`, `wish`, or
  `expect`.
* Directories are recursed.

## False-positive notes

* `#`-comment tails and `"..."` string contents are masked out before
  scanning, so `subst` mentioned inside a comment or a string is
  never flagged.
* Identifiers that merely contain `subst` (e.g. `substring`,
  `substitutions`) are not flagged — the regex requires a
  `\bsubst\b` token at command position.
* `# subst-ok` (or `;# subst-ok`) on a line suppresses that line.
* `eval`, `uplevel`, `interp eval`, and `regsub` with active `[..]`
  in the substitution body are NOT flagged here — they are different
  (also dangerous) constructs covered by sibling detectors.
* The detector does not try to prove a string is constant —
  `subst {literal}` is still flagged because the literal can contain
  `[..]` that will execute. Add `;# subst-ok` if intentional.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: tcl-subst-unsafe — <stripped source line>
# <N> finding(s)
```

## Smoke test (verified)

```
$ python3 detect.py examples/bad
examples/bad/01_subst_var.tcl:5:7: tcl-subst-unsafe — puts [subst $tmpl]
examples/bad/02_subst_quoted.tcl:5:7: tcl-subst-unsafe — puts [subst "$header\n$body"]
examples/bad/03_subst_nobackslashes_only.tcl:5:7: tcl-subst-unsafe — puts [subst -nobackslashes $tmpl]
examples/bad/04_subst_novariables_only.tcl:5:7: tcl-subst-unsafe — puts [subst -novariables $tmpl]
examples/bad/05_subst_braced_literal.tcl:4:7: tcl-subst-unsafe — puts [subst {hello [clock seconds]}]
examples/bad/06_subst_after_then.tcl:5:25: tcl-subst-unsafe — if {$cond} then { puts [subst $tmpl] }
examples/bad/07_subst_after_semi.tcl:3:16: tcl-subst-unsafe — set x 1; puts [subst $x]
# 7 finding(s)

$ python3 detect.py examples/good
# 0 finding(s)
```

bad: **7** findings, good: **0** findings. PASS.
