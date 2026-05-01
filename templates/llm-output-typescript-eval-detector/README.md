# llm-output-typescript-eval-detector

Stdlib-only Python detector that flags **TypeScript / JavaScript**
dynamic-code-execution sinks that LLMs habitually emit when asked to
"evaluate a user formula", "run a snippet from the request body", or
"build a function from a string". This is the canonical CWE-95
(Improper Neutralization of Directives in Dynamically Evaluated Code,
"Eval Injection") / CWE-94 (Code Injection) shape.

## What it flags

* `eval(<non-literal>)` — anything other than a single pure
  string-literal argument.
* `new Function(<...>)` and bare `Function(<...>)` calls — same rule.
* `vm.runInNewContext(...)`, `vm.runInThisContext(...)`,
  `vm.runInContext(...)`, `vm.compileFunction(...)` — **always** flagged
  (no benign literal form exists in real codebases).

## Why it matters

When the argument to `eval` / `new Function` / `vm.run*` is
attacker-influenced, the runtime will execute arbitrary code with the
full privileges of the calling process. In Node services this is
straight RCE; in browsers it gives the attacker the user's session,
DOM, and any tokens in storage.

Common LLM-emitted shapes the detector catches:

```ts
const v = eval(req.query.expr as string);
const fn = new Function("ctx", `return (${body.code});`);
vm.runInNewContext(userScript, sandbox);
return eval("(" + formula + ")(" + x + ")");
```

The fix is always one of:

* Use `JSON.parse` if the input is supposed to be data.
* Use a real expression parser (e.g. an AST library you control) if the
  input is supposed to be a formula.
* If you genuinely need sandboxed code execution, use a separate
  process / WASM runtime, never `vm` against untrusted input.

## Heuristic details

1. String literals (`"..."`, `'...'`, `` `...` ``) and comments
   (`//`, `/* */`) are **token-blanked** before scanning so an `eval`
   inside a quoted string never trips the detector.
2. For `eval(...)` and `new Function(...)`, calls whose argument list
   is **only** string literals (no `+` concatenation, no `${}`
   interpolation) are exempted — they are still ugly but not the
   "untrusted-input" shape this detector targets.
3. `vm.*` calls are **always** flagged.
4. Markdown files are scanned by extracting fenced
   `` ```ts ``/`tsx`/`typescript`/`js`/`jsx`/`javascript` blocks; line
   numbers are preserved. Prose mentions of `eval(` are ignored.
5. Per-line suppression marker (in any comment on that line):
   `// llm-allow:ts-eval`.

## Running

```bash
python3 detect.py path/to/src
python3 detect.py file.ts other.tsx README.md
```

Exits `1` if any findings are emitted, `0` otherwise. Findings are
printed as `path:lineno: ts-<kind>-sink(<callee>)`.

## Worked example

```bash
./verify.sh
```

Confirms the detector trips on every file in `examples/bad/`
(≥6 findings) and stays silent on every file in `examples/good/`.
The script exits `0` and prints `PASS` on success.

## Files

* `detect.py` — the matcher (Python 3 stdlib only).
* `verify.sh` — runs detector on `examples/bad/` and `examples/good/`,
  asserts `bad>=6, good=0`, prints `PASS` / `FAIL`.
* `examples/bad/` — six samples that MUST trip.
* `examples/good/` — six samples that MUST NOT trip (parsers,
  `JSON.parse`, suppression marker, markdown prose, identifier-suffix
  collisions like `retrieval`, `approval`).
