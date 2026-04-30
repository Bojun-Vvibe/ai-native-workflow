# llm-output-nodejs-eval-user-input-detector

A pure-stdlib python3 line scanner that flags Node.js / browser
JavaScript code emitted by an LLM where ``eval(...)`` /
``new Function(...)`` / ``vm.runInNewContext(...)`` /
``vm.runInThisContext(...)`` is invoked with an argument that is NOT
a bare string literal — i.e. a variable, a template literal, a
concatenation, a property access, or a function call result.

LLMs reach for ``eval`` in JS because:

1. The user said "make this dynamic" and ``eval`` is the shortest path.
2. They want to JSON-parse and forget that ``JSON.parse`` exists.
3. They are translating a Python ``eval()`` answer line-by-line.

Result: any value that can flow from request body / query string /
WebSocket message / postMessage / DOM input lands in a JS engine and
runs with full process privileges.

## What this flags

A line is flagged when one of these constructs appears with a
non-bare-string-literal first argument:

* ``eval(<expr>)``
* ``window.eval(<expr>)`` / ``global.eval(<expr>)`` /
  ``globalThis.eval(<expr>)``
* ``new Function(<expr>)`` /  ``Function(<expr>)`` (constructor /
  call form, both equivalent)
* ``vm.runInNewContext(<expr> ...)``
* ``vm.runInThisContext(<expr> ...)``
* ``vm.runInContext(<expr> ...)``
* ``vm.compileFunction(<expr> ...)``
* ``vm.Script(<expr>)`` / ``new vm.Script(<expr>)``

A "bare string literal" is a single ``'...'``, ``"..."`` or
backtick-delimited template ``` `...` ``` with NO ``${...}``
substitutions inside.

## What this does NOT flag

* ``eval("1 + 1")`` — fully literal, no interpolation.
* ``new Function("a", "b", "return a + b")`` — every arg is a literal.
* ``JSON.parse(req.body)`` — not eval.
* Lines suffixed with the suppression marker ``// eval-user-input-ok``.

## CWE references

* **CWE-94**  Improper Control of Generation of Code (Code Injection).
* **CWE-95**  Eval Injection.
* **CWE-913** Improper Control of Dynamically-Managed Code Resources.

## Usage

```
python3 detect.py <file_or_dir> [...]
```

Scans `*.js`, `*.mjs`, `*.cjs`, `*.ts`, `*.tsx`, `*.jsx` under any
directory passed in. Exit `1` if any findings, `0` otherwise.
python3 stdlib only.

## Limitations

* Single-line scanner. A multi-line ``eval(\n  someExpr\n)`` is
  examined line-by-line; if the literal/non-literal arg is on a
  different line than the call name the detector may miss it.
* Comment / string stripping is best-effort and does not understand
  JSX. Content inside JSX text nodes is treated as code.
* Template literal detection requires the backtick AND the
  ``${`` to appear on the same line as the call.
