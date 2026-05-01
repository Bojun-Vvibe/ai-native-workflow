# llm-output-nodejs-jwt-no-algorithm-pin-detector

Stdlib-only Python detector that flags **Node.js** code calling
`jsonwebtoken.verify(...)` (commonly aliased to `jwt.verify(...)`)
**without pinning the `algorithms:` allowlist** in the options bag.

Maps to **CWE-327: Use of a Broken or Risky Cryptographic Algorithm**
and the well-known JWT "alg confusion" family
(CVE-2015-9235, CVE-2016-10555, et al.). When the verifier does not
constrain accepted algorithms, an attacker who knows the public RSA
key can sign a token using `HS256` with that public key as the HMAC
secret, and the library will accept it as valid.

The upstream `jsonwebtoken` README explicitly recommends always
passing an `algorithms` allowlist to `verify()`. LLM-generated samples
routinely omit it because the function still "works" with no third
argument.

## Heuristic

For each Node source file (`*.js`, `*.mjs`, `*.cjs`, `*.ts`, `*.tsx`):

1. Bind a set of identifiers to `jsonwebtoken`:
   - `const jwt = require('jsonwebtoken')`
   - `import jwt from 'jsonwebtoken'`
   - `import * as jwt from 'jsonwebtoken'`
   - `import { verify as jwtVerify } from 'jsonwebtoken'`
2. We always also include the conventional names `jwt`, `jsonwebtoken`,
   `JWT` (so cross-file conventional usage is still caught).
3. For each call site `<id>.verify(`, capture the balanced argument list.
4. Accept the call if it contains `algorithms:` (or `algorithms =`) with
   any value other than literal `['none']`.
5. Accept if the second argument is a hoisted options object whose
   declaration we can see and which itself pins `algorithms:`.
6. Otherwise, emit a finding.

Special-case: `algorithms: ['none']` is flagged loudly — that's just
the alg-confusion shortcut.

## CWE / standards

- **CWE-327**: Use of a Broken or Risky Cryptographic Algorithm.
- **CWE-347**: Improper Verification of Cryptographic Signature.
- **OWASP API Security Top 10 (2023) — API2: Broken Authentication.**
- **CVE-2015-9235** (jsonwebtoken alg confusion).
- **`jsonwebtoken` README**: "Always specify the expected algorithms."

## Distinct from sibling detectors

| Sibling | Scope |
|---|---|
| `llm-output-jwt-none-alg-detector` | flags **signing** with `alg=none` |
| `llm-output-python-jwt-no-verify-detector` | Python `verify=False` |
| **this** | Node.js `verify()` missing `algorithms` allowlist |

## What we accept (no false positive)

- `jwt.verify(token, key, { algorithms: ['HS256'] }, cb)`
- `jwt.verify(token, key, { algorithms: ['RS256', 'ES256'] })`
- `const opts = { algorithms: ['HS256'] }; jwt.verify(token, key, opts)`
- `function verify(...) { ... }` — function declaration, not a call.
- Files that never `require`/`import` `jsonwebtoken` *and* never use
  the conventional names `jwt`/`JWT`.

## What we flag

- `jwt.verify(token, key)` — no options at all.
- `jwt.verify(token, key, { ignoreExpiration: true })` — options without `algorithms`.
- `jwt.verify(token, key, { algorithms: ['none'] })` — alg=none allowlist.
- `import { verify as jwtVerify } from 'jsonwebtoken'; jwtVerify(t, k)`.
- TypeScript variants in `.ts` / `.tsx`.
- Multi-line argument lists (we balance parens up to 40 lines).

## Limits / known false negatives

- We don't follow options through complex destructuring or function
  parameters; an opts bag built deep inside another module and passed
  through several functions will not be tracked.
- We don't model the `verifyOptions` TypeScript type to confirm the
  algorithms list is non-empty.
- `jose`, `fast-jwt`, and `passport-jwt` are out of scope — those have
  different APIs and warrant separate detectors.

## Usage

```bash
python3 detect.py path/to/src/
python3 detect.py path/to/auth.js
```

Exit codes: `0` = no findings, `1` = findings (printed to stdout),
`2` = usage error.

## Smoke test

```
$ bash smoke.sh
bad=6/6 good=0/6
PASS
```

Layout:

```
examples/bad/
  01_no_options.js                 # jwt.verify(t, k)
  02_options_without_algorithms.js # opts but no algorithms key
  03_algorithms_none.js            # algorithms: ['none']
  04_named_import_alias.mjs        # import { verify as jwtVerify }
  05_typescript_no_options.ts      # TS file, missing options
  06_callback_no_options.js        # jwt.verify(t, k, cb)
examples/good/
  01_pinned_hs256.js               # algorithms: ['HS256']
  02_pinned_rs256_es256.js         # multi-algo allowlist
  03_hoisted_opts.js               # opts var pins algorithms
  04_function_decl.js              # function verify() {} -- not a call
  05_unrelated_file.js             # no jsonwebtoken at all
  06_typescript_pinned.ts          # TS, options pinned
```
