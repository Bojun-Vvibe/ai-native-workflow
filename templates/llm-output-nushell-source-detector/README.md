# llm-output-nushell-source-detector

Pure-stdlib python3 single-pass scanner that flags **dynamic** `source`,
`source-env`, and `nu -c` / `nu --commands` invocations in Nushell
(`.nu`) source files.

## What it detects

Nushell's `source FILE` and `source-env FILE` parse and execute the
contents of FILE in the current scope at evaluation time. When FILE is
not a constant string literal — i.e. it is a variable, an expression
involving `$nu.*` / `$env.*`, the result of a `($expr)` paren block,
an interpolated string `$"...($var)..."`, or any subexpression — the
script that gets executed is no longer audit-controlled. That makes
`source $cfg` semantically equivalent to `eval` over the contents of
whatever path `$cfg` resolved to.

`nu -c $cmd` (or `nu --commands $cmd`) re-enters the Nushell parser
on a string from a variable; an LLM that builds that string by joining
user input has constructed a code-injection sink.

The detector flags:

| construct                                    | flagged kind                  |
| :------------------------------------------- | :---------------------------- |
| `source $cfg`                                | `nushell-source-dynamic`      |
| `source-env $env.X`                          | `nushell-source-env-dynamic`  |
| `source $"($base)/x.nu"`                     | `nushell-source-dynamic`      |
| `source ($cfg \| str trim)`                  | `nushell-source-dynamic`      |
| `nu -c $cmd`                                 | `nushell-nu-c-dynamic`        |
| `nu --commands $"do ($x)"`                   | `nushell-nu-c-dynamic`        |

NOT flagged: bareword path literals (`source ./init.nu`), or
single/double-quoted literals with no `$` interpolation
(`source "config/init.nu"`, `nu -c 'ls'`).

## What gets scanned

* Files with extension `.nu`.
* Files whose first line is a shebang containing `nu` or `nushell`.
* Directories are recursed.

## False-positive notes

* `#`-comment tails are masked out before scanning (string-literal
  contents are preserved so we can correctly evaluate the `source`
  argument).
* Identifiers that merely contain `source` or `nu` (e.g. `resource`,
  `nuget`, `sourcecode`) are not flagged — the regex requires a
  word-boundary token at command position.
* `# source-ok` on a line suppresses `source` / `source-env` findings
  on that line. `# nu-c-ok` suppresses `nu -c` findings on that line.
* `use $mod` and `overlay use $name` are NOT flagged — different
  semantics, out of scope.
* External-process invocations (`^nu -c ...`) are NOT flagged — those
  are the caller's responsibility.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: <kind> — <stripped source line>
# <N> finding(s)
```

## Smoke test (verified)

```
$ python3 detect.py examples/bad
examples/bad/01_source_var.nu:5:1: nushell-source-dynamic — source $cfg
examples/bad/02_source_env.nu:4:1: nushell-source-env-dynamic — source-env $env.NU_INIT
examples/bad/03_source_interp.nu:5:1: nushell-source-dynamic — source $"($base)/init.nu"
examples/bad/04_source_paren_expr.nu:4:1: nushell-source-dynamic — source ($cfg | str trim)
examples/bad/05_nu_c_var.nu:4:4: nushell-nu-c-dynamic — nu -c $cmd
examples/bad/06_nu_commands_interp.nu:4:4: nushell-nu-c-dynamic — nu --commands $"do build ($target)"
examples/bad/07_source_after_semi.nu:3:20: nushell-source-dynamic — let _ = (echo hi); source $env.MY_INIT
# 7 finding(s)

$ python3 detect.py examples/good
# 0 finding(s)
```

bad: **7** findings, good: **0** findings. PASS.
