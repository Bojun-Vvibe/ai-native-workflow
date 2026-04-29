# llm-output-nim-staticexec-detector

Pure-stdlib python3 single-pass scanner that flags Nim compile-time
shell-out and dynamic-include sinks — `staticExec`, `gorge`, `gorgeEx`,
`staticRead`, and the `{.compile: ...}` / `{.passC: ...}` /
`{.passL: ...}` pragmas — in `.nim`, `.nims`, and `.nimble` files.

## What it detects

Nim ships a family of compile-time facilities that execute arbitrary
host commands or splice arbitrary text into the program at compile
time:

* `staticExec(STRING)` — runs `sh -c STRING` on the build host
* `gorge(STRING)` — alias of `staticExec`, returns stdout
* `gorgeEx(STRING, ...)` — `staticExec` with stdin + stderr capture
* `staticRead(PATH)` — slurps an arbitrary file at compile time
* `{.compile: STRING.}` / `{.passC: STRING.}` / `{.passL: STRING.}` —
  pragmas that add files / compiler / linker options driven by build-
  time strings

Driven by an LLM-built string (concatenated env var, build input,
config field, etc.) these are build-time RCE sinks. The safe form is to
do the shell-out in a separate build script that writes a generated
`.nim` file you `include`, or to pass values via `-d:name=value` and
read them through `{.strdefine.}` / `{.intdefine.}`.

The detector flags the call/pragma site itself, regardless of whether
the argument is a literal, a concatenation, or a triple-quoted
heredoc — these names are the smell. Suppress an audited line with a
trailing `# nim-static-ok` comment.

## What gets scanned

* Files with extension `.nim`, `.nims`, `.nimble`.
* Directories are recursed.

## False-positive notes

* String literals (`"..."`, `"""..."""`, `r"..."`) and comments
  (`# ...`, `#[ ... ]#` when single-line) are masked before scanning,
  so a `staticExec` token inside documentation or a warning string is
  never flagged.
* Multi-line block comments / multi-line triple-quoted strings are
  best-effort (single-pass per line). The worst case is a missed flag,
  not a wrong-column false positive.
* Whole-word matching (`\b`) ensures a proc named `staticReader`,
  `gorgeous`, `passConfig`, etc. is not flagged.
* `# nim-static-ok` on a line suppresses that line entirely.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: <kind> — <stripped source line>
# <N> finding(s)
```

`<kind>` is one of `nim-staticexec`, `nim-gorge`, `nim-gorgeex`,
`nim-staticread`, `nim-pragma-compile`, `nim-pragma-passc`,
`nim-pragma-passl`.

## Smoke test (verified)

```
$ python3 detect.py examples/bad.nim
examples/bad.nim:6:13: nim-staticexec — const sha = staticExec("git rev-parse HEAD")
examples/bad.nim:9:16: nim-gorge — const branch = gorge("git symbolic-ref --short HEAD")
examples/bad.nim:12:13: nim-gorgeex — const out = gorgeEx("sh", input = "echo hello", cache = "x")
examples/bad.nim:15:17: nim-staticread — const secrets = staticRead("/etc/hostname")
examples/bad.nim:18:1: nim-pragma-compile — {.compile: "vendor/" & "shim.c".}
examples/bad.nim:21:1: nim-pragma-passc — {.passC: "-DBUILD_TAG=" & sha.}
examples/bad.nim:24:1: nim-pragma-passl — {.passL: "-L/opt/lib -lthing".}
examples/bad.nim:27:16: nim-staticexec — const banner = staticExec("""printf 'still dynamic\n'""")
# 8 finding(s)

$ python3 detect.py examples/good.nim
# 0 finding(s)
```

bad: **8** findings, good: **0** findings.
