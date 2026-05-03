# llm-output-node-red-adminauth-disabled-detector

Static lint that flags Node-RED `settings.js` files which export a
runtime configuration with **no active `adminAuth` block** — i.e.
the flow editor and admin HTTP API (`/settings`, `/flows`,
`/admin`) are reachable by any anonymous client on the bind
interface.

Because Node-RED flows can include `function` nodes that execute
arbitrary JavaScript inside the runtime, an unauthenticated editor
is a remote-code-execution surface
(CWE-306: Missing Authentication for Critical Function,
CWE-862: Missing Authorization,
CWE-1188: Insecure Default Initialization of Resource).

LLM-generated quickstart `settings.js` files routinely ship the
`adminAuth` example commented out:

```js
module.exports = {
    uiPort: process.env.PORT || 1880,
    // adminAuth: {
    //     type: "credentials",
    //     users: [{ username: "admin", password: "...", permissions: "*" }]
    // },
    flowFile: 'flows.json',
    functionGlobalContext: { },
};
```

This detector parses such files (after stripping `//` and
`/* ... */` comments) and reports any settings module whose active
source has no `adminAuth:` key.

## What it catches

- `settings.js` / `settings.cjs` / `settings.mjs` that look like a
  Node-RED settings module (contain `module.exports` / `export
  default` and at least one Node-RED hint such as `uiPort`,
  `httpAdminRoot`, `flowFile`, `functionGlobalContext`).
- The active source (post comment-strip) does NOT contain
  `adminAuth:`.

## CWE references

- [CWE-306](https://cwe.mitre.org/data/definitions/306.html):
  Missing Authentication for Critical Function
- [CWE-862](https://cwe.mitre.org/data/definitions/862.html):
  Missing Authorization
- [CWE-1188](https://cwe.mitre.org/data/definitions/1188.html):
  Insecure Default Initialization of Resource

## False-positive surface

- Files containing `// node-red-adminauth-disabled-allowed` are
  skipped wholesale (use for local-only smoke fixtures).
- Files that don't look like a Node-RED settings module are
  skipped (no `module.exports` / `export default` and no
  Node-RED-specific keys).
- Value of `adminAuth:` is NOT validated — presence of the key,
  active (non-commented), is enough.

## Worked example

```sh
$ ./verify.sh
bad=4/4 good=0/3
PASS
```

## Files

- `detector.py` — scanner. Exit code = number of files with at
  least one finding.
- `verify.sh` — runs all `examples/bad/` and `examples/good/` and
  reports `bad=X/X good=0/Y` plus `PASS` / `FAIL`.
- `run.sh` — thin wrapper that execs `verify.sh`.
- `smoke.sh` — alias for `run.sh`, kept for harness symmetry.
- `examples/bad/` — expected to flag.
- `examples/good/` — expected to pass clean.
