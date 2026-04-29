# llm-output-elisp-eval-detector

Pure-stdlib python3 single-pass scanner that flags Emacs Lisp dynamic-
evaluation sinks: `eval`, `eval-region`, `eval-buffer`, `eval-string`,
`eval-expression`, `eval-last-sexp`, `eval-defun`, and the high-
severity `(eval (read ...))` / `(eval ... (read-from-string ...))`
combination.

## What it detects

Emacs Lisp's `(eval FORM)` evaluates an arbitrary Lisp form at runtime.
Combined with `(read STRING)` or `(read-from-string STRING)` — which
parse a string into a Lisp form — you get a complete code-execution
sink with the exact blast radius of `system($USER_INPUT)`.

This is especially dangerous in:

* `dir-locals.el` / `.dir-locals.el` and file-local variables — Emacs
  will silently `eval` anything an attacker drops into the project
  tree (this is the entire reason `enable-local-eval` exists).
* Auto-update hooks that fetch a snippet from a URL and pass it
  through `eval-region` / `eval-buffer`.
* Org-mode src blocks executed via `org-babel-execute-src-block`.

LLM-emitted Elisp reaches for `(eval (read user-supplied-string))` to
"interpret a config file." Almost always wrong. Safe replacements:

| Anti-pattern                                  | Safe alternative                       |
| --------------------------------------------- | -------------------------------------- |
| `(eval (read s))`                             | `(read s)` then dispatch on `(car form)` against a whitelist |
| `(eval-region START END)` of unknown buffer   | `(read-from-string ...)` then validate |
| `(load FILE)` with attacker-controlled FILE   | hard-coded path + checksum             |

## What gets scanned

* Files with extension `.el`, `.eld`.
* `.emacs`, `init.el`, `early-init.el`, `dir-locals.el`,
  `.dir-locals.el`.
* Files whose first line is an `emacs` / `emacsclient` shebang.
* Directories are recursed.

## Two finding kinds

| Kind                       | Meaning                                                       |
| -------------------------- | ------------------------------------------------------------- |
| `elisp-eval`               | Bareword call to `eval` at command position (`(eval ...)`).   |
| `elisp-eval-region`        | `(eval-region ...)` — evaluates a buffer range.               |
| `elisp-eval-buffer`        | `(eval-buffer)` — evaluates current buffer.                   |
| `elisp-eval-string`        | `(eval-string s)` — Emacs 29+ string-form eval.               |
| `elisp-eval-expression`    | `(eval-expression form)` — interactive eval as a function.    |
| `elisp-eval-last-sexp`     | `(eval-last-sexp ...)`.                                       |
| `elisp-eval-defun`         | `(eval-defun ...)` non-interactively.                         |
| `elisp-eval-of-read`       | `(eval (read ...))` or `(eval ... (read-from-string ...))` on one line — **the highest-severity pattern**. May co-fire with `elisp-eval`. |

## False-positive notes

* `eval` inside a `;` line comment or inside a `"..."` string literal
  is masked before scanning.
* A function NAMED `evaluate-expression`, `my-eval`, etc. is NOT
  flagged — the regex requires the exact opening-paren form
  `(eval ` / `(eval-region ` / etc. with a non-identifier char after
  the name.
* `; eval-ok` on a line suppresses that line entirely.
* `(funcall fn args...)` and `(apply fn args)` are NOT flagged —
  calling a function VALUE is not a source-string sink.
* `(load FILE)` and `(load-file FILE)` are out of scope — separate
  detector.
* `(read STRING)` ALONE (without a wrapping `eval`) is just a parser
  call and is NOT flagged.

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
$ python3 detect.py examples/bad.el
examples/bad.el:4:2: elisp-eval — (eval user-form)
examples/bad.el:7:2: elisp-eval — (eval (read user-supplied-string))
examples/bad.el:7:1: elisp-eval-of-read — (eval (read user-supplied-string))
examples/bad.el:10:2: elisp-eval — (eval (car (read-from-string config-string)))
examples/bad.el:10:1: elisp-eval-of-read — (eval (car (read-from-string config-string)))
examples/bad.el:13:2: elisp-eval-region — (eval-region (point-min) (point-max))
examples/bad.el:18:4: elisp-eval-buffer — (eval-buffer))
examples/bad.el:21:2: elisp-eval-string — (eval-string config-snippet)
examples/bad.el:24:2: elisp-eval-expression — (eval-expression dynamic-form)
examples/bad.el:27:2: elisp-eval-defun — (eval-defun nil)
# 10 finding(s)

$ python3 detect.py examples/good.el
# 0 finding(s)
```

bad: **10** findings across 8 distinct lines (the two `(eval (read ...))`
lines correctly co-fire `elisp-eval` + `elisp-eval-of-read`).
good: **0** findings.
