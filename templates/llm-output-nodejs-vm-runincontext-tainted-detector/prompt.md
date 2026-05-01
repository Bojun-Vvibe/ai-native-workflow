# prompt — llm-output-nodejs-vm-runincontext-tainted-detector

You are reviewing JavaScript / TypeScript source for **Node.js `vm`
module misuse with a runtime-built code string** (CWE-94). For every
reviewed file, walk the file and flag each occurrence of the
following calls when their **first positional argument** (`code`) is
not a plain string literal:

* `vm.runInNewContext(code, ...)`
* `vm.runInContext(code, ...)`
* `vm.runInThisContext(code, ...)`
* `vm.compileFunction(code, ...)`
* `new vm.Script(code, ...)` (and `new Script(code, ...)` when
  `Script` is pulled in via a named import / destructured `require`
  from `'vm'` / `'node:vm'`)
* The bare-call form of the four `runIn*` / `compileFunction`
  methods, but **only** when the file also contains a matching named
  import / destructured require from `'vm'` / `'node:vm'`.

A "plain string literal" is `"..."`, `'...'`, or a template literal
`\`...\`` with **no** `${...}` interpolation. Anything else — bare
ident, template literal with interpolation, `+` concatenation,
`String(...)`, `.toString()`, function call, `await` expression — is
runtime-built and must be flagged.

Do **not** flag:

* Calls whose `code` argument is a plain string literal.
* User-defined methods named `runInNewContext` / `runInContext` /
  `runInThisContext` / `compileFunction` on objects unrelated to
  `vm` (no matching named import).
* `eval(...)` or `new Function(...)` — different shapes, covered by
  other detectors.
* Mentions inside `//` / `/* */` comments or string / template
  literals.
* Any call whose statement carries a `// llm-allow:nodejs-vm-tainted`
  suppression marker.

For each finding emit a single line of the form

```
<path>:<line>: <code>: <reason>: <snippet>
```

where `<code>` is one of `nodejs-vm-runinnewcontext-tainted`,
`nodejs-vm-runincontext-tainted`, `nodejs-vm-runinthiscontext-tainted`,
`nodejs-vm-compilefunction-tainted`, `nodejs-vm-script-tainted`. Exit
non-zero if any finding is emitted.

The fix is **never** "wrap it in `runInNewContext` with an empty
context"; the `vm` module is not a sandbox. The fix is to parse
(`JSON.parse`) instead of evaluate, or to keep the code body static
and pass user data through `contextObject` properties /
`compileFunction` parameters.
