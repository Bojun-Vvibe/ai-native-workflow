# llm-output-clojure-eval-read-string-detector

Pure-stdlib python3 single-pass scanner that flags the
`(eval (read-string ...))` and `(load-string ...)` anti-idioms in
Clojure source files.

## What it detects

Clojure has a well-known anti-idiom for "build code as a string and
run it":

```clojure
(eval (read-string (str "(def model-" i " (fit data))")))
```

This is the Clojure equivalent of Python's `exec(s)` or shell
`eval $cmd`. It silently bypasses the compiler's macro hygiene,
defeats `clj-kondo` / `eastwood` static analysis, breaks AOT
compilation guarantees, and — when any fragment of the string flows
from user input, an EDN file, an HTTP body, or a database column —
turns into arbitrary-code execution in the Clojure runtime (which
has full JVM reach: `System/exit`, `Runtime/exec`, reflection,
arbitrary class loading).

LLM-emitted Clojure code reaches for this pattern to dynamically
construct var names, build forms, or "loop and create N defs". In
every such case there is a safer, more idiomatic alternative:

| Anti-idiom                          | Idiomatic Clojure                              |
| ----------------------------------- | ---------------------------------------------- |
| dynamic var name                    | a map keyed by keyword/string                  |
| dynamic form construction           | syntax-quote `` ` `` with `~` / `~@` unquote   |
| compile-time metaprogramming        | a `defmacro` (hygienic, compile-time)          |
| parsing untrusted EDN data          | `clojure.edn/read-string` (data, not code)     |

The detector flags:

* `(eval (read-string ...))`                — including multi-line
* `(eval (clojure.core/read-string ...))`   — fully-qualified inner
* `(clojure.core/eval (read-string ...))`   — fully-qualified outer
* `(load-string ...)`                       — one-shot string-eval
* `(clojure.core/load-string ...)`          — fully-qualified

## What gets scanned

* Files with extension `.clj`, `.cljs`, `.cljc`, `.edn` (matched
  case-insensitively).
* Directories are recursed.

## False-positive notes

* `(clojure.edn/read-string s)` is **not** flagged — it reads EDN
  data, not code, and is the recommended way to parse untrusted
  input.
* `(read-string s)` *not* immediately wrapped in `eval` is **not**
  flagged — the result is a Clojure form (data), harmless on its own.
* `(eval '(+ 1 2))` / `(eval `(+ ~a ~b))` (eval of a quoted or
  syntax-quoted form, not a string) is **not** flagged.
* Mentions inside `;` line comments, `"..."` strings, or `#"..."`
  regex literals are masked out before scanning.
* Trailing `;; eval-read-string-ok` comment on the same line
  suppresses that finding — use sparingly, e.g. for a REPL-helper
  macro whose input is fully internal.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: <kind> — <stripped source line>
# <N> finding(s)
```

`<kind>` is one of `eval-read-string`, `load-string`.

## Smoke test (verified)

```
$ python3 detect.py examples/bad.clj
examples/bad.clj:5:3: eval-read-string — (eval (read-string (str "(def model-" i " (fit data))"))))
examples/bad.clj:9:3: eval-read-string — (eval (read-string (str "(:" name " row)"))))
examples/bad.clj:12:1: eval-read-string — (clojure.core/eval (read-string "(+ 1 1)"))
examples/bad.clj:15:1: eval-read-string — (eval (clojure.core/read-string "(println :hi)"))
examples/bad.clj:18:1: load-string — (load-string "(def x 42)")
examples/bad.clj:21:1: load-string — (clojure.core/load-string "(def y 99)")
examples/bad.clj:24:1: eval-read-string — (eval
examples/bad.clj:30:3: load-string — (load-string s))
# 8 finding(s)

$ python3 detect.py examples/good.clj
# 0 finding(s)
```

bad: **8** findings (covers single-line, multi-line, fully-qualified
`clojure.core/eval` and `clojure.core/read-string`, both `load-string`
spellings, and load-string-from-arg). good: **0** findings (covers
`clojure.edn/read-string`, bare `read-string` without `eval`,
quoted/syntax-quoted-form `eval`, macro alternative, comment mention,
string literal mention, regex literal mention, and
`;; eval-read-string-ok` suppression).
