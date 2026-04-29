# llm-output-tex-write18-detector

Detect shell-escape sinks in TeX / LaTeX source.

## Why

TeX engines (pdfTeX, XeTeX, LuaTeX) ship a "shell escape" channel
where any string after `\write18{...}` (or its named-pipe form
`\immediate\write18{...}`) is handed to `/bin/sh`. Modern engines
also expose:

* `\write18{<cmd>}`             -- pdfTeX/XeTeX classic shell escape
* `\immediate\write18{<cmd>}`   -- forces flush, otherwise identical
* `\directlua{os.execute(...)}` -- LuaTeX's lua-side shell-out
* `\directlua{io.popen(...)}`   -- LuaTeX, same threat model
* `\ShellEscape{<cmd>}`         -- LaTeX3 (l3sys) wrapper, same engine
* `\input|"<cmd>"`              -- pipe-input form (rare but lethal)

LLM-generated build glue and `minted`/`epstopdf` recipes routinely
emit these with command strings built from `\jobname`, `\detokenize`,
or user-supplied `\newcommand` arguments -- a textbook RCE if the
document is compiled with `-shell-escape` (or, worse, the engine is
configured for unrestricted shell escape).

## What this flags

After blanking comments (`%` to EOL, with `\%` honored as a literal
percent) and the contents of curly-brace `{...}` groups *only when
they are arguments to known shell-escape primitives*:

| Pattern                                | Kind                       |
| -------------------------------------- | -------------------------- |
| `\write18{...}`                        | `tex-write18`              |
| `\immediate\write18{...}`              | `tex-write18`              |
| `\directlua{... os.execute ...}`       | `tex-directlua-execute`    |
| `\directlua{... io.popen ...}`         | `tex-directlua-popen`      |
| `\ShellEscape{...}`                    | `tex-shellescape`          |
| `\input|"..."` or `\input|'...'`       | `tex-input-pipe`           |

A finding is upgraded to `-dynamic` if the argument span (curly
group or pipe target), after string-blanking, still contains any
`\` macro reference -- i.e. the command is not a pure literal.

## Suppression

Append `% tex-exec-ok` on the same line.

## Usage

    python3 detector.py <file_or_dir> [...]

Recurses into directories looking for `*.tex`, `*.ltx`, `*.sty`,
`*.cls`, `*.dtx`. Exit 1 if findings, 0 otherwise. python3 stdlib
only.

## Exit codes

* `0` -- no findings
* `1` -- one or more findings
* `2` -- usage error
