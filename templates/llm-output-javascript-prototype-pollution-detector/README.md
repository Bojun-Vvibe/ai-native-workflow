# llm-output-javascript-prototype-pollution-detector

Stdlib-only Python detector for **JavaScript / TypeScript prototype
pollution** (CWE-1321). Catches the unguarded `deepMerge`, dotted-path
setter, and direct `__proto__` / `constructor.prototype` write
patterns that LLMs love to emit because every "merge two objects"
snippet on the open web ships the unsafe form.

## Problem statement

Any code that writes to a property whose key was sourced from
attacker-controlled input (JSON body, query string, YAML config) is
vulnerable to prototype pollution if the merge / set-by-path logic
does not block the keys `__proto__`, `constructor`, and `prototype`.

Concretely:

```js
function deepMerge(target, src) {
  for (const key in src) {                 // attacker controls `key`
    if (typeof src[key] === 'object') {
      target[key] = target[key] || {};
      deepMerge(target[key], src[key]);    // recurses into __proto__
    } else {
      target[key] = src[key];
    }
  }
}
deepMerge({}, JSON.parse(req.body));       // payload: {"__proto__":{"isAdmin":true}}
```

After this call, **every** plain object in the process has
`isAdmin === true`. Any later check of the form
`if (!user.isAdmin) deny()` is now bypassed.

## CWE references

- [CWE-1321](https://cwe.mitre.org/data/definitions/1321.html)
  Improperly Controlled Modification of Object Prototype Attributes
- [CWE-915](https://cwe.mitre.org/data/definitions/915.html)
  Improperly Controlled Modification of Dynamically-Determined Object
  Attributes

## What the detector flags

1. **Direct writes** to `__proto__` / `constructor.prototype`:
   - `obj['__proto__'].x = ...`
   - `obj.__proto__[k] = ...`
   - `obj.constructor.prototype.x = ...`

2. **Indirect** unsafe merges / setters: a function body that
   contains a recursive iteration over input
   (`for (... in src)`, `Object.keys(src).forEach`, or
   `path.split('.')`) **and** a computed-key write
   (`current[k] = ...`) **and** does not contain any guard against
   `__proto__` / `constructor` / `prototype`, nor uses
   `Object.create(null)` / `Map` / `Object.hasOwn` /
   `hasOwnProperty.call`.

## What it deliberately does NOT flag

- Code that uses `Map`, `Object.create(null)`, or
  `Object.prototype.hasOwnProperty.call` as a guard.
- Read-only access (`user.profile.name`) — pollution requires a write.
- Recursive merges that explicitly reject the dangerous keys.

## Usage

```bash
python3 detect.py path/to/file.js
python3 detect.py src/                 # recurses *.js *.ts *.mjs *.cjs *.jsx *.tsx
./smoke.sh                             # runs against bundled examples
```

Exit codes:

- `0` — no findings
- `1` — at least one finding (paths printed to stdout)
- `2` — usage error

## Layout

```
detect.py          # the detector
smoke.sh           # runs detect.py against examples/{bad,good}
examples/bad/      # 6 files, each MUST trigger
examples/good/     # 6 files, each MUST stay quiet
```
