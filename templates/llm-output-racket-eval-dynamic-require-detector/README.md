# llm-output-racket-eval-dynamic-require-detector

Pure-stdlib python3 single-pass scanner that flags dynamic-code-loading
anti-idioms in Racket source files: string-`eval`, `eval-syntax`,
the legacy `load` family, and `dynamic-require` / `namespace-require`
with a computed module spec.

## What it detects

Racket inherits Scheme's `eval` and adds its own dynamic-loading
surface — `dynamic-require`, `dynamic-require-for-syntax`, the
namespace-reflection routines `eval-syntax` and `namespace-require`,
and the legacy `load` / `load/use-compiled` family. Each is a
legitimate building block, but each turns into arbitrary-code
execution the moment the *identifier of what to load* (a module path,
a syntax object, or a form) flows from outside the program.

Common LLM-emitted Racket footguns:

```racket
;; 1. Eval a form parsed from a string at runtime.
(eval (read (open-input-string s)) (make-base-namespace))

;; 2. Load a module by string path constructed from input.
(dynamic-require (string->path user-supplied) 'main)

;; 3. Eval a syntax object reconstructed from a datum.
(eval-syntax (datum->syntax #f form) (current-namespace))

;; 4. Legacy `load` — runs a whole file in the current namespace,
;;    with full filesystem reach on the path argument.
(load file-path)
(load/use-compiled file-path)

;; 5. namespace-require with a runtime-built module spec.
(namespace-require `(file ,user-path))
```

The detector flags:

| Kind                          | Pattern                                                |
| ----------------------------- | ------------------------------------------------------ |
| `eval-read-string-port`       | `(eval (read (open-input-string ...)))` etc.           |
| `eval-with-input-from-string` | `(eval (with-input-from-string ... read) ...)`         |
| `eval-read-from-string`       | `(eval (read-from-string ...))`                        |
| `eval-syntax`                 | `(eval-syntax ...)` (always)                           |
| `dynamic-require-computed`    | `(dynamic-require <non-quoted-spec> ...)`              |
| `dynamic-require-computed`    | `(dynamic-require-for-syntax ...)` (always)            |
| `namespace-require-computed`  | `(namespace-require <non-quoted-spec>)`                |
| `load-file`                   | `(load ...)`, `(load/use-compiled ...)`, `(load-relative ...)`, `(load-extension ...)` |

## Module-spec policy

`dynamic-require` and `namespace-require` are flagged unless the
first argument starts with a plain `'` quote (e.g.
`'racket/base`). A leading quasiquote `` ` `` is treated as
**unsafe** because it commonly carries unquote (`,`) holes that
splice runtime values into the module spec — exactly what we want
to surface. A truly pure quasiquoted constant can be silenced with
the line-suppression comment.

## What gets scanned

* Files with extension `.rkt`, `.rktl`, `.rktd`, `.scrbl` (matched
  case-insensitively).
* Directories are recursed.

## False-positive notes

* `(eval form env)` where `form` is a quoted/quasiquoted s-expression
  literal (no `(read ...)` / `(read-from-string ...)` inside) is
  **not** flagged — that's normal metaprogramming.
* `define-syntax` / `syntax-parse` / `syntax-rules` are **not**
  flagged — they run at compile time inside Racket's hygienic
  macro system.
* `(load-plugin ...)`, `(loader ...)`, `(load-config ...)`, and any
  user-defined identifier that merely *starts with* `load` are not
  matched — the regex requires the exact form names with a
  word boundary on the trailing side.
* Mentions inside `;` line comments and `"..."` string literals are
  masked out before scanning. `#| ... |#` block comments and `#;`
  datum comments are not specifically handled — they're rare in
  real code; suppress with the line comment if needed.
* Trailing `; eval-string-ok` comment on the same line suppresses
  that finding — use sparingly, e.g. for a sandboxed plug-in
  loader behind a `make-evaluator` boundary or a unit-test helper.

## Usage

```
python3 detect.py <file_or_dir> [<file_or_dir> ...]
```

Exits 1 if any findings, 0 otherwise. Output format:

```
<path>:<line>:<col>: <kind> — <stripped source line>
# <N> finding(s)
```

## Smoke test (verified locally)

```
$ python3 detect.py examples/bad.rkt
examples/bad.rkt:7:3: eval-read-string-port — (eval (read (open-input-string s))
examples/bad.rkt:12:3: eval-read-string-port — (eval (read (open-string-input-port s))
examples/bad.rkt:17:3: eval-with-input-from-string — (eval (with-input-from-string s read)
examples/bad.rkt:22:3: eval-read-string-port — (eval (read (call-with-input-string s)) (current-namespace)))
examples/bad.rkt:26:3: eval-read-from-string — (eval (read-from-string s) (current-namespace)))
examples/bad.rkt:30:3: eval-syntax — (eval-syntax (datum->syntax #f form) (current-namespace)))
examples/bad.rkt:34:3: dynamic-require-computed — (dynamic-require (string->path user-path) 'main))
examples/bad.rkt:38:3: dynamic-require-computed — (dynamic-require-for-syntax mod 'expand))
examples/bad.rkt:42:3: namespace-require-computed — (namespace-require `(file ,(symbol->string mod-sym))))
examples/bad.rkt:46:3: load-file — (load path))
examples/bad.rkt:50:3: load-file — (load/use-compiled path))
# 11 finding(s)

$ python3 detect.py examples/good.rkt
# 0 finding(s)
```

bad: **11** findings across **11** distinct anti-patterns. good:
**0** findings (covers `dynamic-require` with quoted module-path
literals, `namespace-require` with a quoted symbol, `eval` of a
quasiquoted s-expression literal — *normal* metaprogramming —
hash-table dispatch as the idiomatic alternative to dynamic
function lookup, `define-syntax-rule` for compile-time codegen,
mention of the dangerous patterns inside a string literal, mention
inside a `;` comment, and the `; eval-string-ok` line-suppression
on a sandboxed test helper).
