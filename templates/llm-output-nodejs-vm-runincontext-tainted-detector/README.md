# llm-output-nodejs-vm-runincontext-tainted-detector

Stdlib-only Python detector that flags **JavaScript / TypeScript**
source where Node's `vm` module executes a runtime-built code string.
The `vm` module is widely mistaken for a sandbox; the Node docs are
explicit that it is **not a security boundary**. Combining `vm.runIn*`
with a runtime-built code string gives the attacker arbitrary code
execution in the host process — the canonical CWE-94 (Code Injection)
shape in Node.

A LLM under "let users define a custom rule" pressure tends to write:

```js
const vm = require('vm');
function evaluate(userExpr) {
  return vm.runInNewContext(userExpr, {});   // arbitrary RCE
}
```

instead of the safe shapes:

```js
// Parse, don't evaluate.
const result = JSON.parse(userExpr);

// Or constrain to a single allowlisted operation.
const ops = { add: (a, b) => a + b, mul: (a, b) => a * b };
const fn = ops[opName];
if (!fn) throw new Error('unknown op');
return fn(a, b);
```

## What's flagged

The detector keys on the *first positional argument* (`code`) of:

1. **`nodejs-vm-runinnewcontext-tainted`** — `vm.runInNewContext(code, ...)`.
2. **`nodejs-vm-runincontext-tainted`** — `vm.runInContext(code, ...)`.
3. **`nodejs-vm-runinthiscontext-tainted`** — `vm.runInThisContext(code, ...)`.
4. **`nodejs-vm-compilefunction-tainted`** — `vm.compileFunction(code, ...)`.
5. **`nodejs-vm-script-tainted`** — `new vm.Script(code, ...)` (and
   `new Script(code, ...)` when imported by name).

A finding fires when `code` is **not** a plain string literal. Bare
idents, template literals containing `${...}` interpolation, `+`
concatenation, `String(...)`, `.toString()`, function calls, `await`
expressions, etc. are all treated as runtime-built. A template literal
with **no** interpolation is treated as a static string and not
flagged.

For bare-call shapes (e.g. `runInNewContext(code, ...)` without a
`vm.` prefix) the detector requires the file to also contain a
matching named import / destructured require from `'vm'` or
`'node:vm'`, so that user-defined methods that happen to share a name
do not produce false positives.

Suppress with a trailing `// llm-allow:nodejs-vm-tainted` on the
relevant call line, or anywhere within the same statement.

## Why this exact shape

`vm` re-uses the V8 isolate of the parent process. It enforces no
permission boundary, no resource boundary, and (without
`runInNewContext` + a stripped `contextObject`) not even an identity
boundary. Once the attacker controls the code string, they control
the host. The only safe pattern is to keep the code body **static**
and pass user data through `contextObject` properties or
`compileFunction` parameters.

## Safe shapes the detector deliberately leaves alone

* `JSON.parse(input)` — no `vm` involved.
* `vm.runInNewContext("Math.PI", {})` — static literal.
* `vm.runInThisContext(\`Math.SQRT2 + Math.LN2\`)` — template literal
  with no `${...}` interpolation.
* User-defined methods named like `runInNewContext` on a non-`vm`
  object (no matching named import from `'vm'` / `'node:vm'`).
* The `vm` API mentioned only inside a comment or string literal.
* Any of the above with an explicit `// llm-allow:nodejs-vm-tainted`
  marker.

## CWE / standards

- **CWE-94**: Improper Control of Generation of Code ('Code
  Injection').
- **OWASP A03:2021** — Injection.
- Node.js docs, `vm` module: "The vm module is not a security
  mechanism. **Do not use it to run untrusted code.**"

## Limits / known false negatives

- We don't follow let-bindings: `const m = vm; m.runInNewContext(x)`
  is **not** flagged. (Most LLM output uses `vm.` directly.)
- We don't follow renamed named imports: `import { runInNewContext as
  rinc } from 'node:vm'; rinc(x)` is **not** flagged.
- We don't model `vm.Script` instances created earlier: `const s =
  new vm.Script(literal); s.runInThisContext()` with a literal is
  correctly *not* flagged at the constructor; we don't try to track
  `s` afterwards.
- We don't flag `eval(x)` or `new Function(x)` — those are different
  shapes covered by other detectors in this catalog.

## Usage

```bash
python3 detect.py path/to/file.js
python3 detect.py path/to/dir/   # walks *.js, *.mjs, *.cjs, *.ts, *.tsx, *.md, *.markdown
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Verify

```
$ bash verify.sh
bad=6/6 good=0/6
PASS
```

### Worked example — `python3 detect.py examples/bad/`

```
$ python3 detect.py examples/bad/
examples/bad/01_runincontext_ident.js:7: nodejs-vm-runincontext-tainted: vm.runInContext with runtime-built code (CWE-94): vm.runInContext(userExpr, sandbox)
examples/bad/02_runinnewcontext_template.js:4: nodejs-vm-runinnewcontext-tainted: vm.runInNewContext with runtime-built code (CWE-94): vm.runInNewContext(`return ${input};`, { input })
examples/bad/03_runinthiscontext_concat.ts:4: nodejs-vm-runinthiscontext-tainted: vm.runInThisContext with runtime-built code (CWE-94): vm.runInThisContext(prefix + body)
examples/bad/04_compilefunction_template.js:4: nodejs-vm-compilefunction-tainted: vm.compileFunction with runtime-built code (CWE-94): vm.compileFunction(`return ${name}.toUpperCase();`, ['name'])
examples/bad/05_new_script_ident.js:4: nodejs-vm-script-tainted: new Script with runtime-built code (CWE-94): new vm.Script(snippet)
examples/bad/06_named_import.ts:5: nodejs-vm-runinnewcontext-tainted: runInNewContext with runtime-built code (CWE-94): runInNewContext(req.code, { Math })
$ echo $?
1
```

### Worked example — `python3 detect.py examples/good/`

```
$ python3 detect.py examples/good/
$ echo $?
0
```

Layout:

```
examples/bad/
  01_runincontext_ident.js          # vm.runInContext(<bare ident>)
  02_runinnewcontext_template.js    # vm.runInNewContext(`...${x}...`)
  03_runinthiscontext_concat.ts     # vm.runInThisContext(a + b)
  04_compilefunction_template.js    # vm.compileFunction(`...${x}...`)
  05_new_script_ident.js            # new vm.Script(<bare ident>)
  06_named_import.ts                # bare named import + runtime arg
examples/good/
  01_static_string.js               # vm.runInNewContext("Math.PI")
  02_static_template.js             # vm.runInThisContext(`Math.SQRT2`)
  03_no_vm.js                       # JSON.parse only — no vm
  04_lookalike_method.js            # user class with same method name
  05_only_comments_and_strings.js   # vm.* mentioned only in comment / string
  06_suppressed.js                  # explicit llm-allow marker
```
