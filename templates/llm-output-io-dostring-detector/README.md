# llm-output-io-dostring-detector

Single-pass python3 stdlib scanner that flags dynamic-evaluation
sinks in [Io](https://iolanguage.org/) source files emitted by LLMs.

## What it detects

Io exposes several methods that take a *string* and execute it as Io
source at runtime:

| Method                          | What it does                                |
| ------------------------------- | ------------------------------------------- |
| `<obj> doString(src)`           | parse + evaluate `src` in `obj`'s context   |
| `<obj> doFile(path)`            | read `path`, then `doString` its contents   |
| `<obj> doMessage(msg)`          | evaluate a pre-parsed message tree          |
| `Object compileString(src)`     | compile `src` into a callable block         |

When the argument is a *bare* string literal with no concatenation,
the detector still emits a (lower-severity) finding kind without the
`-dynamic` suffix — useful to inventory all eval-shaped surfaces.
When the argument involves identifiers, message sends, or `..`
string concatenation, the finding gains the `-dynamic` suffix; this
is the Io flavour of `eval(user_input)`.

| Pattern                                  | Kind                       |
| ---------------------------------------- | -------------------------- |
| `<recv> doString(<arg>)` arg dynamic     | `io-dostring-dynamic`      |
| `<recv> doString(<arg>)` arg literal     | `io-dostring`              |
| `<recv> doFile(<arg>)` arg dynamic       | `io-dofile-dynamic`        |
| `<recv> doFile(<arg>)` arg literal       | `io-dofile`                |
| `<recv> doMessage(<arg>)`                | `io-domessage`             |
| `<recv> compileString(<arg>)` dynamic    | `io-compilestring-dynamic` |
| `<recv> compileString(<arg>)` literal    | `io-compilestring`         |

## False-positive notes

* `//` and `#` line comments and `/* ... */` block-comment fragments
  on the same line are blanked before matching, so doc-comments
  mentioning `doString(src)` do not trip.
* Double-quoted string contents are blanked. Triple-quoted strings
  scrub correctly because each `"` is treated as a toggle.
* `Object perform(name, args...)` (reflective method dispatch) is
  intentionally *not* flagged — that is a distinct smell.
* The detector does not attempt to prove a variable is sanitized;
  a single non-literal argument is enough to flag.

Suppression: append `// io-eval-ok` (or `# io-eval-ok`) on the line.

## Usage

```
python3 detector.py <file_or_dir> [<file_or_dir> ...]
```

Recurses into directories looking for `*.io` files. Exit code is
`1` if any findings were emitted, `0` otherwise. python3 stdlib
only — no external deps.

## Worked example

The `examples/` tree contains five intentionally-bad files and three
clean ones. Running the detector against each:

```
$ python3 detector.py examples/bad
examples/bad/01_dostring_remote.io:5:7: io-dostring-dynamic — Lobby doString(src)
examples/bad/02_dofile_argv.io:3:7: io-dofile-dynamic — Lobby doFile(path)
examples/bad/03_dostring_concat.io:3:7: io-dostring-dynamic — Lobby doString("writeln(\"hello, \" .. " .. name .. ")")
examples/bad/04_compilestring_socket.io:3:17: io-compilestring-dynamic — block := Object compileString(src)
examples/bad/05_domessage.io:4:7: io-domessage — Lobby doMessage(msg)
# 5 finding(s)
$ echo $?
1

$ python3 detector.py examples/good
# 0 finding(s)
$ echo $?
0
```

5 / 5 bad files flagged, 0 / 3 good files flagged. Exit codes match
the contract.

## Why this template exists

LLMs writing Io tutorials reach for `doString` and `doFile` as if
they were `print` — partly because Io's docs themselves use them in
playful examples. In a service that ingests Io snippets (a code
explainer, a notebook kernel, a config evaluator), every dynamic
`doString` is a remote-code-execution surface. This detector lives
where lint runs in CI: a deterministic, dependency-free yes/no on
"did this LLM-produced Io file gain a new eval sink?".
